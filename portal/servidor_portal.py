from __future__ import annotations

import html
import mimetypes
import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket


RAIZ_RISKO = Path(__file__).resolve().parents[1]
CARPETA_PUBLICADOS = Path(
    os.environ.get(
        "PORTAL_RISKO_PUBLICADOS",
        RAIZ_RISKO / "datos" / "position_monitor" / "publicados",
    )
).resolve()
HOST = os.environ.get("PORTAL_RISKO_HOST", "0.0.0.0")
PUERTO = int(os.environ.get("PORTAL_RISKO_PORT", "8088"))


def _esta_dentro(ruta: Path, carpeta: Path) -> bool:
    try:
        ruta.resolve().relative_to(carpeta)
        return True
    except ValueError:
        return False


def _urls_locales(puerto: int) -> list[str]:
    urls = [f"http://localhost:{puerto}/"]
    hostname = socket.gethostname()
    urls.append(f"http://{hostname}:{puerto}/")
    try:
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                urls.append(f"http://{ip}:{puerto}/")
    except OSError:
        pass
    return list(dict.fromkeys(urls))


class PortalRiskoHandler(BaseHTTPRequestHandler):
    server_version = "PortalRisko/0.1"

    def do_GET(self) -> None:
        ruta_url = unquote(urlparse(self.path).path)
        if ruta_url in ("/", "/index.html"):
            self._responder_indice()
            return

        if ruta_url.startswith("/publicados/"):
            relativo = ruta_url.removeprefix("/publicados/")
            self._responder_archivo(CARPETA_PUBLICADOS / relativo)
            return

        self.send_error(404, "Ruta no encontrada")

    def log_message(self, formato: str, *args: object) -> None:
        print(f"{self.address_string()} - {formato % args}")

    def _responder_indice(self) -> None:
        CARPETA_PUBLICADOS.mkdir(parents=True, exist_ok=True)
        archivos_html = sorted(CARPETA_PUBLICADOS.rglob("*.html"))

        filas = []
        for archivo in archivos_html:
            relativo = archivo.relative_to(CARPETA_PUBLICADOS).as_posix()
            nombre = html.escape(relativo)
            href = "/publicados/" + html.escape(relativo, quote=True)
            modificado = archivo.stat().st_mtime
            filas.append(
                f"<tr><td><a href=\"{href}\">{nombre}</a></td>"
                f"<td>{modificado:.0f}</td></tr>"
            )

        if filas:
            contenido = (
                "<table><thead><tr><th>Archivo</th><th>Timestamp</th></tr></thead>"
                f"<tbody>{''.join(filas)}</tbody></table>"
            )
        else:
            contenido = (
                "<p>No hay archivos HTML publicados todavia.</p>"
                f"<p>Carpeta: <code>{html.escape(str(CARPETA_PUBLICADOS))}</code></p>"
            )

        cuerpo = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Portal Risko</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; color: #1f2933; }}
    main {{ max-width: 960px; margin: 0 auto; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    p {{ color: #52606d; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 24px; }}
    th, td {{ border-bottom: 1px solid #d9e2ec; padding: 10px 8px; text-align: left; }}
    th {{ color: #334e68; font-size: 13px; text-transform: uppercase; }}
    a {{ color: #0b5cab; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{ background: #f0f4f8; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
  <main>
    <h1>Portal Risko</h1>
    <p>HTML publicados en <code>datos/position_monitor/publicados</code>.</p>
    {contenido}
  </main>
</body>
</html>"""
        data = cuerpo.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _responder_archivo(self, ruta: Path) -> None:
        ruta = ruta.resolve()
        if not _esta_dentro(ruta, CARPETA_PUBLICADOS) or not ruta.is_file():
            self.send_error(404, "Archivo no encontrado")
            return

        tipo, _ = mimetypes.guess_type(str(ruta))
        data = ruta.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", tipo or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    if not CARPETA_PUBLICADOS.exists():
        CARPETA_PUBLICADOS.mkdir(parents=True, exist_ok=True)

    servidor = ThreadingHTTPServer((HOST, PUERTO), PortalRiskoHandler)
    print("Portal Risko iniciado.")
    print(f"Carpeta publicada: {CARPETA_PUBLICADOS}")
    print("Links posibles:")
    for url in _urls_locales(PUERTO):
        print(f"  {url}")
    print("Detener con Ctrl+C.")
    servidor.serve_forever()


if __name__ == "__main__":
    main()
