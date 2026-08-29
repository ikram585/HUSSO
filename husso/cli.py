"""HUSSO komut satırı arayüzü.

Kullanım:
    python -m husso list                 # bağlı cihazları listele
    python -m husso info [--serial SN]   # teşhis raporu (metin)
    python -m husso info --json          # JSON çıktı
"""

from __future__ import annotations

import argparse
import json
import sys

from .adb import Adb, AdbError, AdbNotFoundError, SubprocessRunner
from .diagnostics import DiagnosticsCollector
from .report import format_report


def _build_adb(adb_path: str | None) -> Adb:
    runner = SubprocessRunner(adb_path=adb_path)
    return Adb(runner)


def _cmd_list(adb: Adb) -> int:
    devices = adb.list_devices()
    if not devices:
        print("Bağlı cihaz bulunamadı. USB hata ayıklamanın açık olduğundan emin olun.")
        return 1
    print(f"{len(devices)} cihaz bulundu:")
    for d in devices:
        model = d.model or "-"
        print(f"  {d.serial}\t{d.state}\t{model}")
    return 0


def _resolve_target(adb: Adb, serial: str | None) -> tuple[str | None, str | None]:
    devices = adb.list_devices()
    usable = [d for d in devices if d.state == "device"]
    if serial:
        for d in devices:
            if d.serial == serial:
                return d.serial, d.state
        raise AdbError(f"'{serial}' seri numaralı cihaz bulunamadı.")
    if not usable:
        if devices:
            d = devices[0]
            return d.serial, d.state
        raise AdbError("Kullanılabilir cihaz yok. Cihazı bağlayıp yetkilendirin.")
    if len(usable) > 1:
        raise AdbError(
            "Birden fazla cihaz bağlı. --serial ile birini seçin (list ile görebilirsiniz)."
        )
    return usable[0].serial, usable[0].state


def _cmd_info(adb: Adb, serial: str | None, as_json: bool) -> int:
    target_serial, state = _resolve_target(adb, serial)
    if state != "device":
        print(
            f"Uyarı: cihaz durumu '{state}'. Tam bilgi için cihaz 'device' durumunda olmalı "
            "(kilit açık ve USB hata ayıklama yetkili).",
            file=sys.stderr,
        )
    collector = DiagnosticsCollector(adb)
    report = collector.collect(target_serial, state=state)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="husso",
        description="Teknik servis için ADB tabanlı cihaz teşhis aracı (yalnızca okuma).",
    )
    parser.add_argument("--adb-path", default=None, help="adb çalıştırılabilir yolu (opsiyonel).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Bağlı cihazları listele.")

    info = sub.add_parser("info", help="Cihaz teşhis raporu.")
    info.add_argument("--serial", default=None, help="Hedef cihaz seri numarası.")
    info.add_argument("--json", action="store_true", help="JSON biçiminde çıktı.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        adb = _build_adb(args.adb_path)
        if args.command == "list":
            return _cmd_list(adb)
        if args.command == "info":
            return _cmd_info(adb, args.serial, args.json)
    except AdbNotFoundError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    except AdbError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    parser.error("Bilinmeyen komut")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
