"""Ayrıştırıcı ve toplayıcı testleri (gerçek adb gerektirmez)."""

from __future__ import annotations

from typing import Sequence

import pytest

from husso.adb import Adb, AdbError, AdbResult, parse_devices, parse_getprop
from husso.diagnostics import (
    DiagnosticsCollector,
    interpret_google_accounts,
    interpret_secure_lock,
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
        "shell settings get secure lockscreen.password_type": (0, "131072\n"),
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


def test_battery_status_discharging_vs_not_charging():
    # Android BatteryManager: 3 = DISCHARGING, 4 = NOT_CHARGING
    assert parse_battery("  status: 3\n").status == "Boşalıyor"
    assert parse_battery("  status: 4\n").status == "Şarj olmuyor"


def test_interpret_secure_lock_disabled():
    # Kilit ekranı tamamen kapalı => güvenli kimlik yok
    assert interpret_secure_lock("true", None) == (False, None)


def test_interpret_secure_lock_swipe_only():
    # Kilit etkin ama parola tipi 0 (swipe) => güvenli değil
    assert interpret_secure_lock("false", "0") == (False, None)


def test_interpret_secure_lock_credentialed():
    # Parola tipi > 0 (ör. PIN=131072) => güvenli kimlik var
    assert interpret_secure_lock("false", "131072") == (True, None)


def test_interpret_secure_lock_unknown_without_password_type():
    # Kilit etkin ama tür okunamıyor => belirsiz + not
    value, note = interpret_secure_lock("false", None)
    assert value is None
    assert note


def test_interpret_secure_lock_unreadable():
    value, note = interpret_secure_lock(None, None)
    assert value is None
    assert note


def test_interpret_google_accounts_authenticator_only():
    # GMS cihazı: com.google authenticator servisi var AMA hesap yok
    dump = (
        "Accounts: 0\n"
        "RegisteredServicesCache: \n"
        "  ServiceInfo: AuthenticatorDescription {type=com.google}\n"
    )
    assert interpret_google_accounts(dump) == (False, None)


def test_interpret_google_accounts_present():
    dump = "Accounts: 1\n  Account {name=x@gmail.com, type=com.google}\n"
    assert interpret_google_accounts(dump) == (True, None)


def test_interpret_google_accounts_non_google_only():
    dump = "Accounts: 1\n  Account {name=x, type=com.whatsapp}\n"
    assert interpret_google_accounts(dump) == (False, None)


def test_interpret_google_accounts_unparseable():
    value, note = interpret_google_accounts("garbage output with no accounts block")
    assert value is None
    assert note


def test_collector_swipe_only_not_secure():
    resp = _full_responses()
    resp["shell settings get secure lockscreen.password_type"] = (0, "0\n")
    report = DiagnosticsCollector(Adb(FakeRunner(resp))).collect("SM123")
    assert report.security.secure_lock_set is False


class TimeoutRunner:
    """getprop dışındaki her isteğe bağlı sorguda AdbError (zaman aşımı) fırlatır."""

    def __init__(self, getprop_out: str):
        self.getprop_out = getprop_out

    def __call__(self, args: Sequence[str], timeout: float) -> AdbResult:
        args = list(args)
        lookup = args[2:] if len(args) >= 2 and args[0] == "-s" else args
        if lookup[:2] == ["shell", "getprop"]:
            return AdbResult(args=args, returncode=0, stdout=self.getprop_out, stderr="")
        raise AdbError("zaman aşımı")


def test_collector_survives_per_query_timeout():
    # getprop başarılı; tüm isteğe bağlı sorgular zaman aşımına uğruyor.
    getprop = "[ro.product.model]: [SM-G991B]\n[ro.product.manufacturer]: [samsung]\n"
    report = DiagnosticsCollector(Adb(TimeoutRunner(getprop))).collect("SM123", state="device")
    # Zaman aşımına rağmen getprop'tan gelen alanlar korunur.
    assert report.model == "SM-G991B"
    assert report.manufacturer == "samsung"
    # İsteğe bağlı alanlar boş kalır, çökme olmaz.
    assert report.battery.level_percent is None
    assert report.storage.total_gb is None
    assert report.security.secure_lock_set is None
    assert report.imei is None
    # Başarısız sorgular için açıklayıcı notlar eklenir.
    assert any("tamamlanamadı" in n for n in report.security.notes)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
