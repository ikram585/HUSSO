"""Ayrıştırıcı ve toplayıcı testleri (gerçek adb gerektirmez)."""

from __future__ import annotations

from typing import Sequence

import pytest

from husso.adb import Adb, AdbResult, parse_devices, parse_getprop
from husso.diagnostics import (
    DiagnosticsCollector,
    parse_battery,
    parse_df,
)
from husso.report import format_report


class FakeRunner:
    """Komut -> (returncode, stdout) eşlemesi ile sahte adb."""

    def __init__(self, responses: dict[str, tuple[int, str]]):
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], timeout: float) -> AdbResult:
        args = list(args)
        self.calls.append(args)
        # "-s <serial>" hedef ön ekini yok say, böylece cevap anahtarları sabit kalır.
        lookup = args[2:] if len(args) >= 2 and args[0] == "-s" else args
        key = " ".join(lookup)
        code, out = self.responses.get(key, (1, ""))
        return AdbResult(args=args, returncode=code, stdout=out, stderr="")


def test_parse_devices():
    out = (
        "List of devices attached\n"
        "ABC123   device product:foo model:Pixel_7 device:panther\n"
        "XYZ789   unauthorized\n"
    )
    devices = parse_devices(out)
    assert len(devices) == 2
    assert devices[0].serial == "ABC123"
    assert devices[0].state == "device"
    assert devices[0].model == "Pixel_7"
    assert devices[1].state == "unauthorized"
    assert devices[1].model is None


def test_parse_getprop():
    out = "[ro.product.model]: [SM-G991B]\n[ro.build.version.release]: [13]\n[junk line]\n"
    props = parse_getprop(out)
    assert props["ro.product.model"] == "SM-G991B"
    assert props["ro.build.version.release"] == "13"
    assert "junk line" not in props


def test_parse_battery():
    out = (
        "Current Battery Service state:\n"
        "  level: 87\n"
        "  status: 2\n"
        "  health: 2\n"
        "  temperature: 305\n"
        "  voltage: 4123\n"
        "  technology: Li-ion\n"
    )
    b = parse_battery(out)
    assert b.level_percent == 87
    assert b.status == "Şarj oluyor"
    assert b.health == "İyi"
    assert b.temperature_c == 30.5
    assert b.voltage_mv == 4123
    assert b.technology == "Li-ion"


def test_parse_df_human_readable():
    out = (
        "Filesystem      Size  Used Avail Use% Mounted on\n"
        "/dev/block/dm-5  110G   80G   30G  73% /data\n"
    )
    s = parse_df(out)
    assert s.total_gb == 110.0
    assert s.used_gb == 80.0
    assert s.available_gb == 30.0
    assert s.used_percent == 73


def _full_responses() -> dict[str, tuple[int, str]]:
    getprop = (
        "[ro.product.manufacturer]: [samsung]\n"
        "[ro.product.brand]: [samsung]\n"
        "[ro.product.model]: [SM-G991B]\n"
        "[ro.product.device]: [o1s]\n"
        "[ro.build.version.release]: [13]\n"
        "[ro.build.version.sdk]: [33]\n"
        "[ro.build.version.security_patch]: [2023-05-01]\n"
        "[ro.build.display.id]: [TP1A.220624.014]\n"
        "[ro.boot.verifiedbootstate]: [green]\n"
        "[ro.boot.flash.locked]: [1]\n"
    )
    battery = "  level: 55\n  status: 3\n  health: 2\n  temperature: 280\n  voltage: 3900\n  technology: Li-ion\n"
    df = "Filesystem Size Used Avail Use% Mounted\n/dev/x 110G 40G 70G 37% /data\n"
    return {
        "shell getprop": (0, getprop),
        "shell dumpsys battery": (0, battery),
        "shell df -h /data": (0, df),
        "shell locksettings get-disabled": (0, "false\n"),
        "shell dumpsys account": (0, "Accounts: 1\n  Account {name=x, type=com.google}\n"),
        "shell service call iphonesubinfo 1": (1, ""),
    }


def test_collector_full_report():
    runner = FakeRunner(_full_responses())
    adb = Adb(runner)
    report = DiagnosticsCollector(adb).collect("SM123", state="device")
    assert report.model == "SM-G991B"
    assert report.manufacturer == "samsung"
    assert report.android_release == "13"
    assert report.battery.level_percent == 55
    assert report.storage.total_gb == 110.0
    assert report.security.bootloader_locked is True
    assert report.security.secure_lock_set is True
    assert report.security.google_accounts_present is True
    assert report.imei is None
    assert report.imei_note  # okunamadı notu var
    # rapor metni istisna atmadan üretilebilmeli
    text = format_report(report)
    assert "CİHAZ TEŞHİS RAPORU" in text
    assert "SM-G991B" in text


def test_collector_handles_missing_data():
    runner = FakeRunner({"shell getprop": (0, "")})
    adb = Adb(runner)
    report = DiagnosticsCollector(adb).collect(None)
    assert report.model is None
    assert report.battery.level_percent is None
    assert report.storage.total_gb is None
    # notlar okunamayan bilgileri işaretlemeli
    assert report.security.notes


def test_imei_parsed_from_service_call():
    resp = _full_responses()
    # service call parcel çıktısı: rakamlar tek tırnak içi ASCII segmentlerde
    # Hedef IMEI: 353865769810234 (15 hane)
    parcel = (
        "Result: Parcel(\n"
        "  0x00000000: 0000000f xxxx xxxx xxxx '3.5.3.8.6.5.7.6.'\n"
        "  0x00000010: xxxx xxxx xxxx xxxx '9.8.1.0.2.3.4...'\n"
        ")\n"
    )
    resp["shell service call iphonesubinfo 1"] = (0, parcel)
    runner = FakeRunner(resp)
    adb = Adb(runner)
    report = DiagnosticsCollector(adb).collect("SM123")
    assert report.imei == "353865769810234"
    assert report.imei_note is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
