from __future__ import annotations

import argparse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from source.job_actions import perform_ui_action
from source.job_similarity_eval import record_similarity_decision, render_similarity_eval_page
from source.present_dashboard import render_present_dashboard


class PresentHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path in {"/", "/index.html"}:
            html = render_present_dashboard(interactive=True)
            self._send_html(html)
            return

        if path == "/embedding-eval":
            page = int((query.get("page") or ["1"])[0] or 1)
            batch_size = int((query.get("batch_size") or ["8"])[0] or 8)
            html = render_similarity_eval_page(page=page, batch_size=batch_size)
            self._send_html(html)
            return

        if path == "/embedding-eval/index.html":
            html = render_similarity_eval_page()
            self._send_html(html)
            return

        else:
            self.send_error(404)
            return

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/embedding-eval/action":
            length = int(self.headers.get("Content-Length", "0") or 0)
            payload = self.rfile.read(length).decode("utf-8")
            params = parse_qs(payload)
            left_id = (params.get("left_id") or [""])[0].strip()
            right_id = (params.get("right_id") or [""])[0].strip()
            decision = (params.get("decision") or [""])[0].strip()
            page = int((params.get("page") or ["1"])[0] or 1)
            batch_size = int((params.get("batch_size") or ["8"])[0] or 8)

            if not left_id or not right_id or not decision:
                html = render_similarity_eval_page(
                    page=page,
                    batch_size=batch_size,
                    action_message="Embedding-Eval fehlgeschlagen: IDs oder Entscheidung fehlen.",
                )
                self._send_html(html, status=400)
                return

            try:
                record_similarity_decision(left_id, right_id, decision)
                messages = {
                    "merge_ok": "Paar als gleicher Job markiert.",
                    "not_same_job": "Paar als unterschiedliche Jobs markiert.",
                    "unclear": "Paar als unsicher markiert.",
                }
                html = render_similarity_eval_page(
                    page=page,
                    batch_size=batch_size,
                    action_message=messages.get(decision, "Entscheidung gespeichert."),
                )
                self._send_html(html)
            except Exception as exc:
                html = render_similarity_eval_page(
                    page=page,
                    batch_size=batch_size,
                    action_message=f"Embedding-Eval fehlgeschlagen: {exc}",
                )
                self._send_html(html, status=500)
            return

        if path != "/action":
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
