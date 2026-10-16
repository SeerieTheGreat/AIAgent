"""Owner-managed contacts. Addresses are deterministic test recipients; the agent can read but never edit them."""
from __future__ import annotations

import json
from dataclasses import dataclass

from eth_account import Account
from eth_utils import keccak

from . import config

DEFAULT_CONTACTS = [
    # name, aliases (lower-case), Chinese-themed family scenario
    ("Mama", ["mama", "mom", "mother", "妈妈", "妈", "ma"]),
    ("Ge", ["ge", "gege", "哥", "哥哥", "older brother", "brother"]),
    ("Landlord Zhang", ["landlord", "landlord zhang", "zhang", "房东", "rent"]),
    ("University Bursar", ["bursar", "university", "tuition", "学费", "school"]),
    ("Xiao Wang", ["xiao wang", "wang", "小王", "friend"]),
]


@dataclass(frozen=True)
class Contact:
    name: str
    aliases: tuple[str, ...]
    address: str


def _derive(name: str) -> str:
    priv = keccak(text=f"shouhu-contact:{name}")
    return Account.from_key(priv).address


def default_contacts() -> list[Contact]:
    return [Contact(n, tuple(a), _derive(n)) for n, a in DEFAULT_CONTACTS]


def save(contacts: list[Contact], path=None) -> None:
    path = path or config.CONTACTS_PATH
    data = [{"name": c.name, "aliases": list(c.aliases), "address": c.address} for c in contacts]
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False))


def load(path=None) -> list[Contact]:
    path = path or config.CONTACTS_PATH
    if not path.exists():
        cs = default_contacts()
        save(cs, path)
        return cs
    data = json.loads(path.read_text())
    return [Contact(d["name"], tuple(d["aliases"]), d["address"]) for d in data]


def find(contacts: list[Contact], query: str) -> list[Contact]:
    """All contacts whose name or alias matches the query (case-insensitive, substring on the query)."""
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for c in contacts:
        names = [c.name.lower(), *c.aliases]
        if q in names or any(q == n or q in n.split() for n in names):
            hits.append(c)
        elif c.address.lower() == q:
            hits.append(c)
    return hits
