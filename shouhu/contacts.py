"""Owner-managed contacts. Addresses are deterministic test recipients; the agent can read but never edit them.

The built-in family lives in contacts.json; contacts the owner registers in the owner console are kept apart in
data/contacts_registered.json and added on load."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from eth_account import Account
from eth_utils import is_address, keccak, to_checksum_address

from . import config

DEFAULT_CONTACTS = [
    # name, aliases (lower-case), Chinese-themed family scenario
    ("Mama", ["mama", "mom", "mother", "妈妈", "妈", "ma"]),
    ("Ge", ["ge", "gege", "哥", "哥哥", "older brother", "brother"]),
    ("Landlord Zhang", ["landlord", "landlord zhang", "zhang", "房东", "rent"]),
    ("University Bursar", ["bursar", "university", "tuition", "学费", "school"]),
    ("Xiao Wang", ["xiao wang", "wang", "小王", "friend"]),
]


def registered_path() -> Path:
    return config.DATA_DIR / "contacts_registered.json"


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


def load(path=None, registered_path=None) -> list[Contact]:
    path = path or config.CONTACTS_PATH
    if not path.exists():
        cs = default_contacts()
        save(cs, path)
    else:
        cs = [Contact(d["name"], tuple(d["aliases"]), d["address"]) for d in json.loads(path.read_text())]
    known = {c.address.lower() for c in cs}
    return cs + [c for c in load_registered(registered_path) if c.address.lower() not in known]


def load_registered(path=None) -> list[Contact]:
    path = Path(path or registered_path())
    if not path.exists():
        return []
    return [Contact(d["name"], tuple(d["aliases"]), d["address"]) for d in json.loads(path.read_text() or "[]")]


def test_address(name: str) -> str:
    """A fresh test recipient for a newly registered contact (nobody holds a key worth anything)."""
    return _derive(name.strip().lower())


def register(existing: list[Contact], name: str, alias: str = "", address: str = "", path=None) -> Contact:
    """Check and save one new contact. Raises ValueError with a sentence the owner can act on."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    alias = re.sub(r"\s+", " ", str(alias or "")).strip()
    if not 2 <= len(name) <= 32 or not re.fullmatch(r"[\w .'-]+", name):
        raise ValueError("enter a contact name of 2 to 32 letters, digits, spaces, dots or hyphens")
    if len(alias) > 16:
        raise ValueError("keep the Chinese name or nickname under 16 characters")
    address = str(address or "").strip() or test_address(name)
    if not is_address(address):
        raise ValueError("that is not a valid address (0x followed by 40 hexadecimal characters)")
    address = to_checksum_address(address)
    words = {name.lower(), *(w for w in name.lower().split() if len(w) > 2), *([alias.lower()] if alias else [])}
    for c in existing:
        if c.address.lower() == address.lower():
            raise ValueError(f"that address is already the contact {c.name}")
        taken = {c.name.lower(), *c.aliases}
        if words & taken:
            raise ValueError(f"the name overlaps the contact {c.name}; pick a name Shouhu cannot confuse")
    contact = Contact(name, tuple(sorted(words)), address)
    path = Path(path or registered_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = [{"name": c.name, "aliases": list(c.aliases), "address": c.address} for c in load_registered(path)]
    saved.append({"name": contact.name, "aliases": list(contact.aliases), "address": contact.address})
    path.write_text(json.dumps(saved, indent=1, ensure_ascii=False))
    return contact


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
