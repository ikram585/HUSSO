"""ADB komutlarını çalıştırmak için ince bir sarmalayıcı katmanı.

`AdbRunner` bağımlılık enjeksiyonu için soyutlanmıştır; testlerde gerçek
`adb` yerine sahte (fake) bir çalıştırıcı geçilebilir.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence


class AdbError(RuntimeError):
    """ADB ile ilgili hatalar için temel istisna."""


class AdbNotFoundError(AdbError):
    """Sistemde `adb` çalıştırılabilir dosyası bulunamadığında."""


@dataclass(frozen=True)
class AdbResult:
    """Bir ADB komutunun sonucu."""

    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CommandRunner(Protocol):
    """`adb` argümanlarını çalıştıran herhangi bir nesne."""

    def __call__(self, args: Sequence[str], timeout: float) -> AdbResult:  # pragma: no cover - protokol
        ...


class SubprocessRunner:
    """Gerçek `adb` çalıştırılabilir dosyasını `subprocess` ile çağırır."""

    def __init__(self, adb_path: str | None = None) -> None:
        resolved = adb_path or shutil.which("adb")
        if not resolved:
            raise AdbNotFoundError(
                "`adb` bulunamadı. Android platform-tools kurun ve PATH'e ekleyin."
            )
        self._adb_path = resolved

    @property
    def adb_path(self) -> str:
        return self._adb_path

    def __call__(self, args: Sequence[str], timeout: float) -> AdbResult:
        cmd = [self._adb_path, *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - zamanlama
            raise AdbError(f"ADB komutu zaman aşımına uğradı: {' '.join(args)}") from exc
        return AdbResult(
            args=list(args),
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


class Adb:
    """Yüksek seviyeli ADB yardımcıları (yalnızca okuma amaçlı)."""

    def __init__(self, runner: CommandRunner, *, default_timeout: float = 20.0) -> None:
        self._runner = runner
        self._default_timeout = default_timeout

    def run(self, args: Sequence[str], *, timeout: float | None = None) -> AdbResult:
        return self._runner(list(args), timeout if timeout is not None else self._default_timeout)

    def _targeted(self, serial: str | None, args: Sequence[str]) -> list[str]:
        if serial:
            return ["-s", serial, *args]
        return list(args)

    def list_devices(self) -> list["DeviceListEntry"]:
        """`adb devices -l` çıktısını ayrıştırır."""

        result = self.run(["devices", "-l"])
        if not result.ok:
            raise AdbError(f"`adb devices` başarısız: {result.stderr.strip()}")
        return parse_devices(result.stdout)

    def shell(self, serial: str | None, command: str, *, timeout: float | None = None) -> AdbResult:
        return self.run(self._targeted(serial, ["shell", command]), timeout=timeout)

    def getprops(self, serial: str | None) -> dict[str, str]:
        """`getprop` çıktısının tamamını ayrıştırıp sözlük döndürür."""

        result = self.shell(serial, "getprop")
        if not result.ok:
            return {}
        return parse_getprop(result.stdout)


@dataclass(frozen=True)
class DeviceListEntry:
    serial: str
    state: str
    info: dict[str, str]

    @property
    def model(self) -> str | None:
        return self.info.get("model")


def parse_devices(output: str) -> list[DeviceListEntry]:
    """`adb devices -l` çıktısını yapılandırılmış girdilere çevirir."""

    entries: list[DeviceListEntry] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial = parts[0]
        state = parts[1]
        info: dict[str, str] = {}
        for token in parts[2:]:
            if ":" in token:
                key, _, value = token.partition(":")
                info[key] = value
        entries.append(DeviceListEntry(serial=serial, state=state, info=info))
    return entries


def parse_getprop(output: str) -> dict[str, str]:
    """`[anahtar]: [değer]` biçimindeki getprop çıktısını ayrıştırır."""

    props: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("[") or "]: [" not in line:
            continue
        try:
            key_part, value_part = line.split("]: [", 1)
        except ValueError:  # pragma: no cover - savunmacı
            continue
        key = key_part[1:]
        value = value_part.rsplit("]", 1)[0]
        props[key] = value
    return props
