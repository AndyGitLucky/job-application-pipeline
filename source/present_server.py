from __future__ import annotations

import argparse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.job_actions import perform_ui_action
from source.present_dashboard import render_present_dashboard


class PresentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in {"/", "/index.html"}:
            self.send_error(404)
            return
        html = render_present_dashboard(interactive=True)
        self._send_html(html)

    def do_POST(self) -> None:
        if self.path != "/action":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        payload = self.rfile.read(length).decode("utf-8")
        params = parse_qs(payload)
        job_id = (params.get("job_id") or [""])[0].strip()
        action = (params.get("action") or [""])[0].strip()
        note = (params.get("note") or [""])[0].strip()[:255]

        if not job_id or not action:
            html = render_present_dashboard(
                interactive=True,
                action_message="Aktion fehlgeschlagen: job_id oder action fehlt.",
            )
            self._send_html(html, status=400)
            return

        try:
            message = perform_ui_action(job_id, action, note=note)
            html = render_present_dashboard(interactive=True, action_message=message)
            self._send_html(html)
        except Exception as exc:
            html = render_present_dashboard(
                interactive=True,
                action_message=f"Aktion fehlgeschlagen: {exc}",
            )
            self._send_html(html, status=500)

    def log_message(self, format: str, *args) -> None:
        return

    def _send_html(self, body: str, status: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lokaler Present-Server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    serve_present_ui(args.host, args.port, open_browser=not args.no_browser)


def serve_present_ui(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = False) -> None:
    server = ThreadingHTTPServer((host, port), PresentHandler)
    url = f"http://{host}:{port}"
    print(f"Present UI: {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
