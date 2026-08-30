"""Bağlı cihazdan yalnızca okuma amaçlı teşhis bilgisi toplar.

Toplanan hiçbir bilgi kilit atlatma amacıyla kullanılmaz; amaç servis
kaydı, arıza teşhisi ve müşteri bilgilendirmesidir.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from .adb import Adb, AdbError, AdbResult


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


def _failed_note(command: str, result: AdbResult) -> str:
    """Sıfırdan farklı çıkışlı bir `adb shell` sonucundan açıklayıcı not üretir."""

    detail = result.stderr.strip() or result.stdout.strip()
    detail = f": {detail}" if detail else ""
    return f"'{command}' sorgusu başarısız (çıkış {result.returncode}){detail}."


# --- Ayrıştırıcılar (saf fonksiyonlar, kolay test edilir) ---

_BATTERY_STATUS = {
    "1": "Bilinmiyor",
    "2": "Şarj oluyor",
    "3": "Boşalıyor",
    "4": "Şarj olmuyor",
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


def interpret_secure_lock(
    disabled_out: Optional[str], password_type_out: Optional[str]
) -> tuple[Optional[bool], Optional[str]]:
    """Güvenli ekran kilidi (PIN/desen/parola) var mı, en iyi çabayla belirler.

    `locksettings get-disabled` yalnızca kilit ekranının tamamen kapalı olup
    olmadığını söyler; kaydırma (swipe) ile güvenli kimlik arasındaki farkı
    ayırt etmez. Bu yüzden `lockscreen.password_type` (DevicePolicyManager
    parola kalitesi sabiti) birincil sinyal olarak kullanılır. Güvenilir bir
    cevap üretilemezse `None` ve açıklayıcı bir not döndürülür.
    """

    disabled = (disabled_out or "").strip().lower()
    ptype = (password_type_out or "").strip().lower()

    # Birincil sinyal: parola kalitesi (>0 => PIN/desen/parola gibi güvenli kimlik)
    if ptype and ptype != "null":
        try:
            return int(ptype, 0) > 0, None
        except ValueError:
            pass

    if disabled == "true":
        # Kilit ekranı tamamen kapalı => güvenli kimlik yok
        return False, None
    if disabled == "false":
        return None, (
            "Kilit ekranı etkin; güvenli kimlik türü (PIN/desen/parola) "
            "ADB ile ayırt edilemedi."
        )
    return None, "Ekran kilidi durumu okunamadı (yetki/sürüm sınırı)."


def interpret_google_accounts(dumpsys_account_out: str) -> tuple[Optional[bool], Optional[str]]:
    """`dumpsys account` çıktısından yapılandırılmış Google hesabı olup olmadığını çıkarır.

    Dikkat: çıktı, kayıtlı authenticator servislerini (ör. `com.google`) de
    listeler; bunlar gerçek bir hesap anlamına gelmez. Bu yüzden yalnızca
    `Account {...}` girdileri incelenir. `Accounts:` bloğu ayrıştırılamazsa
    `None` döndürülür.
    """

    account_lines = [
        line for line in dumpsys_account_out.splitlines() if "Account {" in line
    ]
    if account_lines:
        for line in account_lines:
            if "type=com.google" in line:
                return True, None
        return False, None

    # "Accounts: N" göstergesini yedek sinyal olarak kullan
    for line in dumpsys_account_out.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("accounts:"):
            value = stripped.split(":", 1)[1].strip()
            if value == "0":
                return False, None
            break
    return None, (
        "Hesap listesi ayrıştırılamadı; Google hesabı durumu belirsiz "
        "(FRP durumu ADB ile güvenilir şekilde okunamaz)."
    )


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

        # Her isteğe bağlı sorgu kendi içinde izole edilir: birinde zaman aşımı
        # (AdbError) olması diğer toplanmış alanları düşürmez.
        battery, battery_note = self._collect_battery(serial)
        report.battery = battery
        report.storage, storage_note = self._collect_storage(serial)
        report.security = self._collect_security(serial, props)
        report.imei, report.imei_note = self._collect_imei(serial)
        for note in (battery_note, storage_note):
            if note:
                report.security.notes.append(note)
        return report

    def _try_shell(self, serial: str | None, command: str) -> tuple[Optional[AdbResult], Optional[str]]:
        """`adb shell` çalıştırır; zaman aşımı/ADB hatasını sessizce yakalar.

        Böylece tek bir takılan sorgu tüm raporu iptal etmez. Hata durumunda
        `(None, açıklayıcı not)` döner. Sıfırdan farklı çıkış kodları da
        `_failed_note` ile ayrı bir not olarak çağırana bildirilir.
        """

        try:
            return self._adb.shell(serial, command), None
        except AdbError as exc:
            return None, f"'{command}' sorgusu tamamlanamadı ({exc})."

    def _collect_battery(self, serial: str | None) -> tuple[BatteryInfo, Optional[str]]:
        result, note = self._try_shell(serial, "dumpsys battery")
        if result is None:
            return BatteryInfo(), note
        if not result.ok:
            return BatteryInfo(), _failed_note("dumpsys battery", result)
        return parse_battery(result.stdout), None

    def _collect_storage(self, serial: str | None) -> tuple[StorageInfo, Optional[str]]:
        result, note = self._try_shell(serial, "df -h /data")
        if result is None:
            return StorageInfo(), note
        if not result.ok:
            return StorageInfo(), _failed_note("df -h /data", result)
        if not result.stdout.strip():
            return StorageInfo(), None
        return parse_df(result.stdout), None

    def _collect_security(self, serial: str | None, props: dict[str, str]) -> SecurityInfo:
        info = SecurityInfo()
        info.verified_boot_state = props.get("ro.boot.verifiedbootstate")
        flash_locked = props.get("ro.boot.flash.locked")
        if flash_locked in {"0", "1"}:
            info.bootloader_locked = flash_locked == "1"

        # Güvenli ekran kilidi ayarlı mı? (yalnızca gösterge; doğrulama gerektirmez)
        disabled, disabled_note = self._try_shell(serial, "locksettings get-disabled")
        ptype, ptype_note = self._try_shell(serial, "settings get secure lockscreen.password_type")
        info.secure_lock_set, lock_note = interpret_secure_lock(
            disabled.stdout if disabled and disabled.ok else None,
            ptype.stdout if ptype and ptype.ok else None,
        )
        for note in (lock_note, disabled_note, ptype_note):
            if note:
                info.notes.append(note)

        accounts, acc_query_note = self._try_shell(serial, "dumpsys account")
        if accounts is not None and accounts.ok and accounts.stdout.strip():
            info.google_accounts_present, acc_note = interpret_google_accounts(accounts.stdout)
            if acc_note:
                info.notes.append(acc_note)
        else:
            info.notes.append(
                acc_query_note
                or "Hesap bilgisi okunamadı; FRP durumu ADB ile güvenilir şekilde okunamaz."
            )
        return info

    def _collect_imei(self, serial: str | None) -> tuple[Optional[str], Optional[str]]:
        """IMEI okumayı en iyi çabayla dener.

        Modern Android sürümlerinde IMEI yalnızca ayrıcalıklı erişimle
        okunabilir; okunamazsa `*#06#` ile ekrandan alınması önerilir.
        """

        result, _ = self._try_shell(serial, "service call iphonesubinfo 1")
        if result is not None and result.ok and result.stdout.strip():
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
