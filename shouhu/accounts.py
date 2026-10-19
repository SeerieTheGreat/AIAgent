"""Local sign-up and sign-in for the two people in the family: the student (agent side) and the parent (owner side).

One account per role, kept in data/accounts.json. Passwords are stored only as salted scrypt hashes. The parent's
account also keeps a message signed with the wallet's owner key, which proves the person who registered controls it."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from pathlib import Path

from . import config

ROLES = ("student", "owner")
_LOCK = threading.Lock()


class AccountError(ValueError):
    pass


def _hash(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode("utf8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32).hex()


def check_fields(name: str, password: str) -> tuple[str, str]:
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    password = str(password or "")
    if not 2 <= len(name) <= 40:
        raise AccountError("enter a name of 2 to 40 characters")
    if len(password) < 8:
        raise AccountError("use a password of at least 8 characters")
    if len(password) > 200:
        raise AccountError("that password is too long")
    return name, password


class Accounts:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.DATA_DIR / "accounts.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text() or "{}")

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False))

    def exists(self, role: str) -> bool:
        return role in self._read()

    def register(self, role: str, name: str, password: str, **profile) -> dict:
        if role not in ROLES:
            raise AccountError(f"unknown role {role}")
        name, password = check_fields(name, password)
        with _LOCK:
            data = self._read()
            if role in data:
                raise AccountError(f"a {role} account is already registered on this computer; sign in instead")
            salt = secrets.token_bytes(16)
            data[role] = {"name": name, "salt": salt.hex(), "hash": _hash(password, salt), "created": time.time(), **profile}
            self._write(data)
            return self.public(role)

    def check(self, role: str, password: str) -> dict | None:
        acct = self._read().get(role)
        if not acct:
            return None
        ok = hmac.compare_digest(_hash(str(password or ""), bytes.fromhex(acct["salt"])), acct["hash"])
        return self.public(role) if ok else None

    def public(self, role: str) -> dict | None:
        acct = self._read().get(role)
        return {k: v for k, v in acct.items() if k not in ("salt", "hash")} if acct else None

    def update(self, role: str, **fields) -> dict:
        with _LOCK:
            data = self._read()
            data[role].update(fields)
            self._write(data)
        return self.public(role)

    def remove(self, role: str) -> None:
        with _LOCK:
            data = self._read()
            data.pop(role, None)
            self._write(data)


def add_routes(app, accounts: Accounts, role: str, prepare=None) -> None:
    """Sign-up, sign-in and sign-out routes for one app. prepare(name, body) runs after the fields are checked and
    before the account is saved; it returns extra profile fields, or raises AccountError to stop the registration."""
    app.role = role

    @app.get("/api/me", public=True)
    def _me(q):
        return 200, {"role": role, "registered": accounts.exists(role), "signed_in": app.signed_in(getattr(app.req, "sid", None)),
                     "account": accounts.public(role) if app.signed_in(getattr(app.req, "sid", None)) else None}

    @app.post("/api/register", public=True)
    def _register(body):
        if accounts.exists(role):
            return 409, {"error": f"a {role} account is already registered on this computer; sign in instead"}
        try:
            name, password = check_fields(body.get("name"), body.get("password"))
            if str(body.get("password2", password)) != password:
                raise AccountError("the two passwords do not match")
            profile = prepare(name, body) if prepare else {}
            acct = accounts.register(role, name, password, **profile)
        except AccountError as e:
            return 400, {"error": str(e)}
        return 200, {"ok": True, "account": acct}, app.start_session()

    @app.post("/api/login", public=True)
    def _login(body):
        wait = app.sign_in_wait()
        if wait:
            return 429, {"error": f"too many wrong passwords; try again in {wait} seconds"}
        acct = accounts.check(role, body.get("password"))
        if not acct:
            app.failures.append(time.time())
            return 401, {"error": "wrong password" if accounts.exists(role) else "no account yet; register first"}
        return 200, {"ok": True, "account": acct}, app.start_session()

    @app.post("/api/logout", public=True)
    def _logout(body):
        return 200, {"ok": True}, app.end_session()
