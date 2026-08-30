"""Web arayüzü güvenlik ve davranış testleri (gerçek adb gerektirmez)."""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from typing import Sequence

import pytest

from husso.adb import Adb, AdbResult
from husso.webapp import _host_is_loopback, make_server


class FakeRunner:
    def __init__(self, responses: dict[str, tuple[int, str]]):
        self.responses = responses

    def __call__(self, args: Sequence[str], timeout: float) -> AdbResult:
        args = list(args)
        lookup = args[2:] if len(args) >= 2 and args[0] == "-s" else args
        code, out = self.responses.get(" ".join(lookup), (1, ""))
        return AdbResult(args=args, returncode=code, stdout=out, stderr="")


def _devices_output() -> str:
    return "List of devices attached\nSER1 device model:Pixel\n"


@pytest.fixture()
def server():
    # FakeRunner "-s <serial>" ön ekini yok saydığı için anahtarlar ön eksizdir.
    runner = FakeRunner(
        {
            "devices -l": (0, _devices_output()),
            "shell getprop": (0, "[ro.product.model]: [Pixel]\n"),
            "shell dumpsys battery": (0, "  level: 50\n"),
            "shell df -h /data": (0, "F S U A Use% M\n/x 10G 5G 5G 50% /data\n"),
            "shell locksettings get-disabled": (0, "true\n"),
            "shell settings get secure lockscreen.password_type": (1, ""),
            "shell dumpsys account": (0, "Accounts: 0\n"),
            "shell service call iphonesubinfo 1": (1, ""),
        }
    )
    srv = make_server(host="127.0.0.1", port=0, adb=Adb(runner), token="testtoken")
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield port
    srv.shutdown()
    srv.server_close()


def _get(port: int, path: str, *, token: str | None = None, host: str | None = None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    if token is not None:
        req.add_header("X-HUSSO-Token", token)
    if host is not None:
        req.add_header("Host", host)
    return urllib.request.urlopen(req, timeout=5)


def test_index_served_with_token(server):
    resp = _get(server, "/")
    body = resp.read().decode("utf-8")
    assert resp.status == 200
    assert "testtoken" in body  # jeton sayfaya gömülür
    assert "__HUSSO_TOKEN__" not in body


def test_api_requires_token(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/devices")
    assert exc.value.code == 401


def test_api_devices_with_token(server):
    resp = _get(server, "/api/devices", token="testtoken")
    assert resp.status == 200
    assert b"SER1" in resp.read()


def test_api_rejects_non_loopback_host(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/devices", token="testtoken", host="evil.example.com")
    assert exc.value.code == 403


def test_api_info_missing_serial(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/info", token="testtoken")
    assert exc.value.code == 400


def test_api_info_unknown_serial(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/api/info?serial=NOPE", token="testtoken")
    assert exc.value.code == 404


def test_api_info_includes_state(server):
    import json

    resp = _get(server, "/api/info?serial=SER1", token="testtoken")
    data = json.loads(resp.read())
    assert data["serial"] == "SER1"
    assert data["state"] == "device"  # bağlantı durumu artık dolu


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1:8765", True),
        ("localhost:8765", True),
        ("localhost", True),
        ("[::1]:8765", True),
        ("0.0.0.0", False),
        ("evil.example.com", False),
        ("192.168.1.5:8765", False),
        (None, False),
    ],
)
def test_host_is_loopback(host, expected):
    assert _host_is_loopback(host) is expected


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
