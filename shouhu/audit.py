"""Append-only audit log. Every intent id written on-chain is the hash of a log entry."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from eth_utils import keccak

from . import config


class Audit:
    def __init__(self, path: Path | None = None, session: str | None = None):
        self.path = Path(path) if path else config.AUDIT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session = session or uuid.uuid4().hex[:12]
        self.seq = 0

    def log(self, event: str, **data) -> dict:
        self.seq += 1
        entry = {"ts": time.time(), "session": self.session, "seq": self.seq, "event": event, **data}
        with self.path.open("a", encoding="utf8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        return entry

    @staticmethod
    def intent_id(entry: dict) -> bytes:
        canonical = json.dumps({k: entry[k] for k in ("session", "seq", "event", "ts")}, sort_keys=True)
        return keccak(text=canonical)

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf8").splitlines() if line.strip()]
