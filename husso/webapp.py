"""Basit yerel web arayüzü (yalnızca standart kütüphane).

Çalıştırma:
    python -m husso.webapp        # http://127.0.0.1:8765

Teknisyen tarayıcıdan cihazları listeleyip teşhis raporunu görebilir.
Sunucu yalnızca localhost'a bağlanır; dışarıya açılmaz.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .adb import Adb, AdbError, SubprocessRunner
from .diagnostics import DiagnosticsCollector

_INDEX_HTML = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HUSSO — Cihaz Teşhis</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 0; background:#0f172a; color:#e2e8f0; }
  header { padding:16px 24px; background:#1e293b; border-bottom:1px solid #334155; }
  header h1 { margin:0; font-size:18px; }
  main { padding:24px; max-width:900px; margin:0 auto; }
  button { background:#2563eb; color:#fff; border:0; padding:8px 16px; border-radius:8px; cursor:pointer; font-size:14px; }
  button:hover { background:#1d4ed8; }
  .row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:16px; }
  select { padding:8px; border-radius:8px; background:#1e293b; color:#e2e8f0; border:1px solid #334155; }
  .card { background:#1e293b; border:1px solid #334155; border-radius:12px; padding:16px; margin-bottom:16px; }
  .card h2 { margin:0 0 12px; font-size:15px; color:#93c5fd; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  td { padding:6px 8px; border-bottom:1px solid #334155; }
  td:first-child { color:#94a3b8; width:45%; }
  .muted { color:#94a3b8; font-size:13px; }
  .note { color:#fbbf24; font-size:13px; }
  .err { color:#f87171; }
</style>
</head>
<body>
<header><h1>HUSSO — Cihaz Teşhis (yalnızca okuma)</h1></header>
<main>
  <div class="row">
    <button id="refresh">Cihazları Yenile</button>
    <select id="devices"></select>
    <button id="scan">Teşhis Et</button>
  </div>
  <div id="status" class="muted">Başlamak için cihazı USB ile bağlayın ve "Cihazları Yenile"ye basın.</div>
  <div id="output"></div>
</main>
<script>
async function loadDevices() {
  const st = document.getElementById('status');
  st.textContent = 'Cihazlar taranıyor...';
  try {
    const r = await fetch('/api/devices');
    const data = await r.json();
    const sel = document.getElementById('devices');
    sel.innerHTML = '';
    if (!data.devices || data.devices.length === 0) {
      st.textContent = 'Cihaz bulunamadı. USB hata ayıklamanın açık olduğundan emin olun.';
      return;
    }
    for (const d of data.devices) {
      const opt = document.createElement('option');
      opt.value = d.serial;
      opt.textContent = d.serial + ' (' + d.state + (d.model ? ', ' + d.model : '') + ')';
      sel.appendChild(opt);
    }
    st.textContent = data.devices.length + ' cihaz bulundu.';
  } catch (e) {
    st.innerHTML = '<span class="err">Hata: ' + e + '</span>';
  }
}
function tbl(title, rows) {
  let h = '<div class="card"><h2>' + title + '</h2><table>';
  for (const [k, v] of rows) {
    h += '<tr><td>' + k + '</td><td>' + (v === null || v === undefined || v === '' ? '-' : v) + '</td></tr>';
  }
  return h + '</table></div>';
}
async function scan() {
  const sel = document.getElementById('devices');
  const st = document.getElementById('status');
  const out = document.getElementById('output');
  if (!sel.value) { st.textContent = 'Önce bir cihaz seçin.'; return; }
  st.textContent = 'Teşhis yapılıyor...';
  out.innerHTML = '';
  try {
    const r = await fetch('/api/info?serial=' + encodeURIComponent(sel.value));
    const d = await r.json();
    if (d.error) { st.innerHTML = '<span class="err">Hata: ' + d.error + '</span>'; return; }
    st.textContent = 'Rapor hazır.';
    let html = tbl('Genel', [
      ['Seri No', d.serial], ['Durum', d.state], ['Üretici', d.manufacturer],
      ['Marka', d.brand], ['Model', d.model], ['Kod Adı', d.device_codename],
      ['Android', (d.android_release||'-') + ' (SDK ' + (d.sdk||'-') + ')'],
      ['Güvenlik Yaması', d.security_patch], ['Yapı', d.build_id],
      ['IMEI', d.imei || (d.imei_note || '-')],
    ]);
    const b = d.battery || {};
    html += tbl('Pil', [
      ['Şarj', b.level_percent != null ? b.level_percent + '%' : '-'],
      ['Durum', b.status], ['Sağlık', b.health],
      ['Sıcaklık', b.temperature_c != null ? b.temperature_c + ' °C' : '-'],
      ['Voltaj', b.voltage_mv != null ? b.voltage_mv + ' mV' : '-'],
      ['Teknoloji', b.technology],
    ]);
    const s = d.storage || {};
    html += tbl('Depolama (/data)', [
      ['Toplam', s.total_gb != null ? s.total_gb + ' GB' : '-'],
      ['Kullanılan', s.used_gb != null ? s.used_gb + ' GB (' + (s.used_percent||'-') + '%)' : '-'],
      ['Boş', s.available_gb != null ? s.available_gb + ' GB' : '-'],
    ]);
    const sec = d.security || {};
    const tr = (x) => x == null ? '-' : (x ? 'Evet' : 'Hayır');
    html += tbl('Güvenlik / Kilit (yalnızca bilgi)', [
      ['Verified Boot', sec.verified_boot_state],
      ['Bootloader Kilit', tr(sec.bootloader_locked)],
      ['Ekran Kilidi', tr(sec.secure_lock_set)],
      ['Google Hesabı', tr(sec.google_accounts_present)],
    ]);
    if (sec.notes && sec.notes.length) {
      html += '<div class="card"><h2>Notlar</h2>' +
        sec.notes.map(n => '<div class="note">• ' + n + '</div>').join('') + '</div>';
    }
    out.innerHTML = html;
  } catch (e) {
    st.innerHTML = '<span class="err">Hata: ' + e + '</span>';
  }
}
document.getElementById('refresh').addEventListener('click', loadDevices);
document.getElementById('scan').addEventListener('click', scan);
loadDevices();
</script>
</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    adb: Adb  # sınıf düzeyinde enjekte edilir

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def log_message(self, *args) -> None:  # pragma: no cover - gürültüyü azalt
        pass

    def do_GET(self) -> None:  # noqa: N802 (stdlib arayüzü)
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._send(200, _INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/devices":
            try:
                devices = self.adb.list_devices()
                self._send_json(
                    {"devices": [{"serial": d.serial, "state": d.state, "model": d.model} for d in devices]}
                )
            except AdbError as exc:
                self._send_json({"error": str(exc)}, code=500)
            return
        if parsed.path == "/api/info":
            qs = parse_qs(parsed.query)
            serial = (qs.get("serial") or [None])[0]
            try:
                collector = DiagnosticsCollector(self.adb)
                report = collector.collect(serial)
                self._send_json(report.to_dict())
            except AdbError as exc:
                self._send_json({"error": str(exc)}, code=500)
            return
        self._send(404, b"Not Found", "text/plain; charset=utf-8")


def make_server(host: str = "127.0.0.1", port: int = 8765, adb: Adb | None = None) -> ThreadingHTTPServer:
    resolved_adb = adb or Adb(SubprocessRunner())
    handler = type("_BoundHandler", (_Handler,), {"adb": resolved_adb})
    return ThreadingHTTPServer((host, port), handler)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="HUSSO yerel web arayüzü.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    server = make_server(args.host, args.port)
    url = f"http://{args.host}:{args.port}"
    print(f"HUSSO web arayüzü çalışıyor: {url}  (durdurmak için Ctrl+C)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        print("\nKapatılıyor...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
