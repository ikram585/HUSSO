"""`DeviceReport` nesnelerini insan tarafından okunabilir metne çevirir."""

from __future__ import annotations

from .diagnostics import DeviceReport


def _fmt(value, suffix: str = "") -> str:
    if value is None or value == "":
        return "-"
    return f"{value}{suffix}"


def format_report(report: DeviceReport) -> str:
    lines: list[str] = []
    lines.append("=" * 48)
    lines.append("  CİHAZ TEŞHİS RAPORU")
    lines.append("=" * 48)
    lines.append(f"Seri No           : {_fmt(report.serial)}")
    lines.append(f"Bağlantı Durumu   : {_fmt(report.state)}")
    lines.append(f"Üretici           : {_fmt(report.manufacturer)}")
    lines.append(f"Marka             : {_fmt(report.brand)}")
    lines.append(f"Model             : {_fmt(report.model)}")
    lines.append(f"Kod Adı           : {_fmt(report.device_codename)}")
    lines.append(f"Android Sürümü    : {_fmt(report.android_release)} (SDK {_fmt(report.sdk)})")
    lines.append(f"Güvenlik Yaması   : {_fmt(report.security_patch)}")
    lines.append(f"Yapı (Build)      : {_fmt(report.build_id)}")
    lines.append(f"IMEI              : {_fmt(report.imei)}")
    if report.imei_note:
        lines.append(f"  ↳ {report.imei_note}")

    b = report.battery
    lines.append("-" * 48)
    lines.append("PİL")
    lines.append(f"  Şarj            : {_fmt(b.level_percent, '%')}")
    lines.append(f"  Durum           : {_fmt(b.status)}")
    lines.append(f"  Sağlık          : {_fmt(b.health)}")
    lines.append(f"  Sıcaklık        : {_fmt(b.temperature_c, ' °C')}")
    lines.append(f"  Voltaj          : {_fmt(b.voltage_mv, ' mV')}")
    lines.append(f"  Teknoloji       : {_fmt(b.technology)}")

    s = report.storage
    lines.append("-" * 48)
    lines.append("DEPOLAMA (/data)")
    lines.append(f"  Toplam          : {_fmt(s.total_gb, ' GB')}")
    lines.append(f"  Kullanılan      : {_fmt(s.used_gb, ' GB')} ({_fmt(s.used_percent, '%')})")
    lines.append(f"  Boş             : {_fmt(s.available_gb, ' GB')}")

    sec = report.security
    lines.append("-" * 48)
    lines.append("GÜVENLİK / KİLİT DURUMU (yalnızca bilgi)")
    lines.append(f"  Verified Boot   : {_fmt(sec.verified_boot_state)}")
    lines.append(f"  Bootloader Kilit: {_fmt(_bool_tr(sec.bootloader_locked))}")
    lines.append(f"  Ekran Kilidi    : {_fmt(_bool_tr(sec.secure_lock_set))}")
    lines.append(f"  Google Hesabı   : {_fmt(_bool_tr(sec.google_accounts_present))}")
    for note in sec.notes:
        lines.append(f"  ↳ {note}")
    lines.append("=" * 48)
    return "\n".join(lines)


def _bool_tr(value) -> str | None:
    if value is None:
        return None
    return "Evet" if value else "Hayır"
