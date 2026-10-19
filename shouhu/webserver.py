"""Tiny local web server shared by the student's app and the owner console. Standard library only.

Both servers bind to 127.0.0.1, reject foreign Host headers (DNS rebinding) and require a per-launch token
on every POST, so another web page open in the same browser cannot drive the wallet. When an app has an
account role, every API route except the ones marked public also needs a signed-in session cookie."""
from __future__ import annotations

import json
import secrets
import threading
import time
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

STATIC = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


SESSION_SECONDS = 12 * 3600


class App:
    """Routes: get/post handlers return (status, payload) or (status, payload, headers); payload is a dict (JSON)."""

    def __init__(self, page: str, title: str, role: str | None = None):
        self.page = page
        self.title = title
        self.role = role                  # account role that must be signed in for the API, or None
        self.token = secrets.token_urlsafe(24)
        self.gets: dict = {}
        self.posts: dict = {}
        self.public: set = set()
        self.pages: dict = {"/": page, "/index.html": page}
        self.page_vars: dict = {}
        self.sessions: dict = {}          # session id -> expiry
        self.failures: list = []          # times of recent failed sign-ins
        self.req = threading.local()      # the session id of the request being handled

    def get(self, path, public=False):
        def deco(fn):
            self.gets[path] = fn
            if public:
                self.public.add(("GET", path))
            return fn
        return deco

    def post(self, path, public=False):
        def deco(fn):
            self.posts[path] = fn
            if public:
                self.public.add(("POST", path))
            return fn
        return deco

    # ------------------------------------------------------------------ sessions
    @property
    def cookie_name(self) -> str:
        return f"shouhu_{self.role}"      # cookies ignore the port, so each app needs its own name

    def signed_in(self, sid: str | None) -> bool:
        exp = self.sessions.get(sid or "")
        if exp and exp > time.time():
            return True
        self.sessions.pop(sid or "", None)
        return False

    def start_session(self) -> list:
        sid = secrets.token_urlsafe(24)
        self.sessions[sid] = time.time() + SESSION_SECONDS
        self.failures.clear()
        return [("Set-Cookie", f"{self.cookie_name}={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS}")]

    def end_session(self) -> list:
        self.sessions.pop(getattr(self.req, "sid", None) or "", None)
        return [("Set-Cookie", f"{self.cookie_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")]

    def end_all_sessions(self) -> None:
        self.sessions.clear()

    def sign_in_wait(self) -> int:
        """Seconds to wait before another password try: five misses in a row lock sign-in for 30 seconds."""
        now = time.time()
        self.failures[:] = [t for t in self.failures if now - t < 30]
        return int(30 - (now - self.failures[0])) + 1 if len(self.failures) >= 5 else 0

    def render_page(self, name: str | None = None) -> bytes:
        html = (STATIC / (name or self.page)).read_text(encoding="utf8")
        boot = json.dumps({"token": self.token, **self.page_vars}, ensure_ascii=False).replace("</", "<\\/")
        return html.replace("/*BOOT*/null", boot).encode("utf8")


def _handler(app: App, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        server_version = "Shouhu"

        def log_message(self, fmt, *args):  # keep the terminal quiet; the audit log is the record
            pass

        def _send(self, status: int, body: bytes, ctype: str, headers=()):
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj, headers=()):
            self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf8"), "application/json; charset=utf-8", headers)

        def _authorized(self, method: str, path: str) -> bool:
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie", ""))
            except Exception:
                pass
            app.req.sid = jar[app.cookie_name].value if app.role and app.cookie_name in jar else None
            if not app.role or (method, path) in app.public or app.signed_in(app.req.sid):
                return True
            self._json(401, {"error": "sign in first", "signed_in": False})
            return False

        def _run(self, fn, arg):
            try:
                out = fn(arg)
            except Exception as e:
                out = 500, {"error": f"{type(e).__name__}: {e}"}
            self._json(*out)

        def _host_ok(self) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                self._json(403, {"error": "unexpected host"})
                return False
            return True

        def do_GET(self):
            if not self._host_ok():
                return
            url = urlparse(self.path)
            if url.path in app.pages:
                return self._send(200, app.render_page(app.pages[url.path]), TYPES[".html"])
            if url.path.startswith("/static/"):
                f = (STATIC / url.path[len("/static/"):]).resolve()
                if STATIC in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), TYPES.get(f.suffix, "application/octet-stream"))
                return self._json(404, {"error": "not found"})
            fn = app.gets.get(url.path)
            if not fn:
                return self._json(404, {"error": "not found"})
            if self._authorized("GET", url.path):
                self._run(fn, {k: v[0] for k, v in parse_qs(url.query).items()})

        def do_POST(self):
            if not self._host_ok():
                return
            if not secrets.compare_digest(self.headers.get("X-Shouhu-Token", ""), app.token):
                return self._json(403, {"error": "missing or wrong page token; reload the page"})
            path = urlparse(self.path).path
            fn = app.posts.get(path)
            if not fn:
                return self._json(404, {"error": "not found"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            except ValueError:
                return self._json(400, {"error": "the request body is not JSON"})
            if self._authorized("POST", path):
                self._run(fn, body if isinstance(body, dict) else {})

    return H


def serve(app: App, port: int, open_browser: bool = False) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), _handler(app, port))
    httpd.daemon_threads = True
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    return httpd
