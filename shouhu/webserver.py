"""Tiny local web server shared by the student's app and the owner console. Standard library only.

Both servers bind to 127.0.0.1, reject foreign Host headers (DNS rebinding) and require a per-launch token
on every POST, so another web page open in the same browser cannot drive the wallet."""
from __future__ import annotations

import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


class App:
    """Routes: get/post handlers return (status, payload); payload is a dict (JSON) or bytes."""

    def __init__(self, page: str, title: str):
        self.page = page
        self.title = title
        self.token = secrets.token_urlsafe(24)
        self.gets: dict = {}
        self.posts: dict = {}
        self.page_vars: dict = {}

    def get(self, path):
        def deco(fn):
            self.gets[path] = fn
            return fn
        return deco

    def post(self, path):
        def deco(fn):
            self.posts[path] = fn
            return fn
        return deco

    def render_page(self) -> bytes:
        html = (STATIC / self.page).read_text(encoding="utf8")
        boot = json.dumps({"token": self.token, **self.page_vars}, ensure_ascii=False).replace("</", "<\\/")
        return html.replace("/*BOOT*/null", boot).encode("utf8")


def _handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "Shouhu"

        def log_message(self, fmt, *args):  # keep the terminal quiet; the audit log is the record
            pass

        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                self._json(403, {"error": "unexpected host"})
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                return self._send(200, app.render_page(), TYPES[".html"])
            if url.path.startswith("/static/"):
                f = (STATIC / url.path[len("/static/"):]).resolve()
                if STATIC in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
                return self._json(404, {"error": "not found"})
            fn = app.gets.get(url.path)
            if not fn:
                return self._json(404, {"error": "not found"})
            try:
                status, out = fn({k: v[0] for k, v in parse_qs(url.query).items()})
            except Exception as e:
                status, out = 500, {"error": f"{type(e).__name__}: {e}"}
            self._json(status, out)

        def do_POST(self):
            if not self._host_ok():
                return
            if not secrets.compare_digest(self.headers.get("X-Shouhu-Token", ""), app.token):
                return self._json(403, {"error": "missing or wrong page token; reload the page"})
            fn = app.posts.get(urlparse(self.path).path)
            if not fn:
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                status, out = fn(body if isinstance(body, dict) else {})
            except Exception as e:
                status, out = 500, {"error": f"{type(e).__name__}: {e}"}
            self._json(status, out)

    return H


def serve(app: App, port: int, open_browser: bool = False) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(app, port))
    httpd.daemon_threads = True
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    return httpd
