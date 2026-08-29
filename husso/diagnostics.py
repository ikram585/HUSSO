"""Bağlı cihazdan yalnızca okuma amaçlı teşhis bilgisi toplar.

Toplanan hiçbir bilgi kilit atlatma amacıyla kullanılmaz; amaç servis
kaydı, arıza teşhisi ve müşteri bilgilendirmesidir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .adb import Adb


@dataclass
class BatteryInfo:
    level_percent: Optional[int] = None
    status: Optional[str] = None
    health: Optional[str] = None
    temperature_c: Optional[float] = None
    voltage_mv: Optional[int] = None
    technology: Optional[str] = None


@dataclass
class StorageInfo:
    total_gb: Optional[float] = None
    used_gb: Optional[float] = None
    available_gb: Optional[float] = None
    used_percent: Optional[int] = None


@dataclass
class SecurityInfo:
    verified_boot_state: Optional[str] = None
    bootloader_locked: Optional[bool] = None
    secure_lock_set: Optional[bool] = None
    google_accounts_present: Optional[bool] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class DeviceReport:
    serial: Optional[str] = None
    state: Optional[str] = None
    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    device_codename: Optional[str] = None
    android_release: Optional[str] = None
    sdk: Optional[str] = None
    security_patch: Optional[str] = None
    build_id: Optional[str] = None
    imei: Optional[str] = None
    imei_note: Optional[str] = None
    battery: BatteryInfo = field(default_factory=BatteryInfo)
    storage: StorageInfo = field(default_factory=StorageInfo)
    security: SecurityInfo = field(default_factory=SecurityInfo)

    def to_dict(self) -> dict:
        return asdict(self)


# --- Ayrıştırıcılar (saf fonksiyonlar, kolay test edilir) ---

_BATTERY_STATUS = {
    "1": "Bilinmiyor",
    "2": "Şarj oluyor",
    "3": "Şarj olmuyor",
    "4": "Boşalıyor",
    "5": "Dolu",
}

_BATTERY_HEALTH = {
    "1": "Bilinmiyor",
    "2": "İyi",
    "3": "Aşırı ısınmış",
    "4": "Ölü",
    "5": "Aşırı voltaj",
    "6": "Belirsiz arıza",
    "7": "Soğuk",
}


def parse_battery(dumpsys_output: str) -> BatteryInfo:
    info = BatteryInfo()
    for raw in dumpsys_output.splitlines():
        line = raw.strip()
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        try:
            if key == "level":
                info.level_percent = int(value)
            elif key == "status":
                info.status = _BATTERY_STATUS.get(value, value)
            elif key == "health":
                info.health = _BATTERY_HEALTH.get(value, value)
            elif key == "temperature":
                info.temperature_c = round(int(value) / 10.0, 1)
            elif key == "voltage":
                info.voltage_mv = int(value)
            elif key == "technology":
                info.technology = value
        except ValueError:
            continue
    return info


def _to_gb(token: str) -> Optional[float]:
    token = token.strip()
    if not token:
        return None
    try:
        if token.endswith("G"):
            return round(float(token[:-1]), 2)
        if token.endswith("M"):
            return round(float(token[:-1]) / 1024.0, 2)
        if token.endswith("K"):
            return round(float(token[:-1]) / (1024.0 * 1024.0), 2)
        if token.endswith("T"):
            return round(float(token[:-1]) * 1024.0, 2)
        # birimsiz -> KB varsay (df -k)
        return round(float(token) / (1024.0 * 1024.0), 2)
    except ValueError:
        return None


def parse_df(df_output: str) -> StorageInfo:
    """`df -h /data` çıktısının veri satırını ayrıştırır."""

    info = StorageInfo()
    lines = [ln for ln in df_output.splitlines() if ln.strip()]
    if len(lines) < 2:
        return info
    # Son satır genellikle mount noktasına ait veri satırıdır.
    parts = lines[-1].split()
    # Beklenen: Filesystem Size Used Avail Use% Mounted
    if len(parts) >= 5:
        info.total_gb = _to_gb(parts[1])
        info.used_gb = _to_gb(parts[2])
        info.available_gb = _to_gb(parts[3])
        pct = parts[4].rstrip("%")
        try:
            info.used_percent = int(pct)
        except ValueError:
            info.used_percent = None
    return info


class DiagnosticsCollector:
    """Bir cihaz için `DeviceReport` üretir."""

    def __init__(self, adb: Adb) -> None:
        self._adb = adb

    def collect(self, serial: str | None = None, *, state: str | None = None) -> DeviceReport:
        report = DeviceReport(serial=serial, state=state)
        props = self._adb.getprops(serial)
        report.manufacturer = props.get("ro.product.manufacturer")
        report.brand = props.get("ro.product.brand")
        report.model = props.get("ro.product.model")
        report.device_codename = props.get("ro.product.device")
        report.android_release = props.get("ro.build.version.release")
        report.sdk = props.get("ro.build.version.sdk")
        report.security_patch = props.get("ro.build.version.security_patch")
        report.build_id = props.get("ro.build.display.id") or props.get("ro.build.id")

        report.battery = self._collect_battery(serial)
        report.storage = self._collect_storage(serial)
        report.security = self._collect_security(serial, props)
        report.imei, report.imei_note = self._collect_imei(serial)
        return report

    def _collect_battery(self, serial: str | None) -> BatteryInfo:
        result = self._adb.shell(serial, "dumpsys battery")
        if not result.ok:
            return BatteryInfo()
        return parse_battery(result.stdout)

    def _collect_storage(self, serial: str | None) -> StorageInfo:
        result = self._adb.shell(serial, "df -h /data")
        if not result.ok or not result.stdout.strip():
            return StorageInfo()
        return parse_df(result.stdout)

    def _collect_security(self, serial: str | None, props: dict[str, str]) -> SecurityInfo:
        info = SecurityInfo()
        info.verified_boot_state = props.get("ro.boot.verifiedbootstate")
        flash_locked = props.get("ro.boot.flash.locked")
        if flash_locked in {"0", "1"}:
            info.bootloader_locked = flash_locked == "1"

        # Güvenli ekran kilidi ayarlı mı? (yalnızca gösterge; doğrulama gerektirmez)
        lock = self._adb.shell(serial, "locksettings get-disabled")
        if lock.ok and lock.stdout.strip():
            val = lock.stdout.strip().lower()
            if val in {"true", "false"}:
                # get-disabled true => kilit YOK
                info.secure_lock_set = val == "false"
            else:
                info.notes.append("Ekran kilidi durumu okunamadı (yetki gerekebilir).")
        else:
            info.notes.append("Ekran kilidi durumu okunamadı (cihaz kilitliyken sınırlı).")

        accounts = self._adb.shell(serial, "dumpsys account")
        if accounts.ok and accounts.stdout.strip():
            has_google = "com.google" in accounts.stdout
            info.google_accounts_present = has_google
        else:
            info.notes.append(
                "Hesap bilgisi okunamadı; FRP durumu ADB ile güvenilir şekilde okunamaz."
            )
        return info

    def _collect_imei(self, serial: str | None) -> tuple[Optional[str], Optional[str]]:
        """IMEI okumayı en iyi çabayla dener.

        Modern Android sürümlerinde IMEI yalnızca ayrıcalıklı erişimle
        okunabilir; okunamazsa `*#06#` ile ekrandan alınması önerilir.
        """

        result = self._adb.shell(serial, "service call iphonesubinfo 1")
        if result.ok and result.stdout.strip():
            imei = _parse_service_call_string(result.stdout)
            if imei and imei.isdigit() and len(imei) >= 14:
                return imei, None
        return None, "IMEI ADB ile okunamadı. Cihazda *#06# ile görüntüleyin."


def _parse_service_call_string(output: str) -> Optional[str]:
    """`service call` parcel çıktısındaki ASCII karakterleri çıkarır."""

    chars: list[str] = []
    for line in output.splitlines():
        if "'" not in line:
            continue
        # Örn: 0x00000000: 00350033 ... '.5.3.8...'
        _, _, tail = line.partition("'")
        segment = tail.rsplit("'", 1)[0]
        for ch in segment:
            if ch.isdigit():
                chars.append(ch)
    value = "".join(chars)
    return value or None
