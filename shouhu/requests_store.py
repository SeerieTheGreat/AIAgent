"""Approval requests the agent files and only the owner can settle. Plain JSON, one file."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import config

_LOCK = threading.Lock()


class Requests:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.REQUESTS_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text() or "[]")

    def _write(self, items: list[dict]) -> None:
        self.path.write_text(json.dumps(items, indent=1, ensure_ascii=False))

    def create(self, intent_id: str, to: str, name: str | None, amount: int, reasons: list[str], memo: str = "") -> dict:
        with _LOCK:
            items = self._read()
            req = {"id": f"R{len(items) + 1}", "intent_id": intent_id, "to": to, "name": name, "amount": amount,
                   "memo": memo, "reasons": reasons, "status": "pending", "created": time.time(),
                   "approve_tx": None, "exec_tx": None}
            items.append(req)
            self._write(items)
            return req

    def get(self, req_id: str) -> dict | None:
        return next((r for r in self._read() if r["id"].lower() == req_id.lower()), None)

    def update(self, req_id: str, **fields) -> dict:
        with _LOCK:
            items = self._read()
            for r in items:
                if r["id"].lower() == req_id.lower():
                    r.update(fields)
                    self._write(items)
                    return r
        raise KeyError(req_id)

    def list(self, status: str | None = None) -> list[dict]:
        items = self._read()
        return [r for r in items if status is None or r["status"] == status]

    def clear(self) -> None:
        with _LOCK:
            self._write([])
