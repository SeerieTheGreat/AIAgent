"""The policy engine: a pure function. No model is involved in any decision here."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .contacts import Contact, find
from .money import fmt

ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")


@dataclass(frozen=True)
class PolicyState:
    per_transfer_cap: int
    rolling_cap: int
    spent_24h: int
    paused: bool
    balance: int
    allowlist: dict  # lower-case address -> True


@dataclass
class Resolution:
    query: str
    address: str | None = None
    name: str | None = None
    candidates: list = field(default_factory=list)   # contact names when ambiguous
    provenance_ok: bool = False
    lookalike_of: str | None = None
    first_time: bool = False
    note: str = ""


@dataclass
class Decision:
    action: str            # allow | request | refuse
    tier: int              # 1 allow, 2 request, 0 refuse (nothing happens)
    reasons: list
    warnings: list


def _lookalike(addr: str, contacts: list[Contact]) -> str | None:
    a = addr.lower()
    for c in contacts:
        b = c.address.lower()
        if a != b and a[:6] == b[:6] and a[-4:] == b[-4:]:
            return c.name
    return None


def resolve_recipient(query: str, contacts: list[Contact], user_message: str) -> Resolution:
    """Turn a nickname or raw address into an address, with the provenance rule applied.

    A raw address is accepted only if it appears verbatim in the user's own message or is a contact.
    """
    r = Resolution(query=query)
    q = (query or "").strip()
    m = ADDRESS_RE.fullmatch(q)
    if m:
        addr = q
        known = [c for c in contacts if c.address.lower() == addr.lower()]
        in_message = addr.lower() in (user_message or "").lower()
        r.address = addr
        r.provenance_ok = bool(known) or in_message
        r.lookalike_of = _lookalike(addr, contacts)
        if known:
            r.name = known[0].name
        else:
            r.first_time = True
            r.note = "raw address, not a contact"
        if not r.provenance_ok:
            r.note = "address does not appear in the user's message or in the contacts"
        return r
    hits = find(contacts, q)
    if len(hits) == 1:
        c = hits[0]
        r.address, r.name, r.provenance_ok = c.address, c.name, True
    elif len(hits) > 1:
        r.candidates = [c.name for c in hits]
        r.note = "ambiguous nickname"
    else:
        r.note = "no contact matches"
    return r


def evaluate_transfer(amount: int, res: Resolution, state: PolicyState, risk: list[str]) -> Decision:
    reasons: list[str] = []
    warnings: list[str] = []
    if amount <= 0:
        return Decision("refuse", 0, ["amount must be positive"], warnings)
    if res.address is None:
        why = "ambiguous recipient: " + ", ".join(res.candidates) if res.candidates else "unknown recipient"
        return Decision("refuse", 0, [why], warnings)
    if not res.provenance_ok:
        return Decision("refuse", 0, ["address provenance: the address is neither a contact nor present in your message, so it cannot be used"], warnings)
    if res.lookalike_of:
        return Decision("refuse", 0, [f"address poisoning warning: this address looks like {res.lookalike_of}'s but differs in the middle; verify it out of band"], warnings)
    if state.paused:
        return Decision("refuse", 0, ["the wallet is paused by the owner"], warnings)
    if amount > state.balance:
        return Decision("refuse", 0, [f"insufficient balance: wallet holds {fmt(state.balance)}"], warnings)
    allowlisted = state.allowlist.get(res.address.lower(), False)
    if not allowlisted:
        reasons.append(f"{res.name or res.address} is not on the owner's allowlist")
    if amount > state.per_transfer_cap:
        reasons.append(f"{fmt(amount)} exceeds the per-transfer cap of {fmt(state.per_transfer_cap)}")
    if state.spent_24h + amount > state.rolling_cap:
        reasons.append(f"it would exceed the 24-hour cap of {fmt(state.rolling_cap)} (spent {fmt(state.spent_24h)} so far)")
    for flag in risk:
        warnings.append({"urgency": "the request uses urgency language", "secrecy": "the request asks for secrecy",
                         "send_everything": "the request asks to send everything", "pressure": "the request contains pressure or threats",
                         "authority_claim": "the request claims owner authority, which the agent cannot verify"}[flag])
    if reasons:
        return Decision("request", 2, reasons, warnings)
    if risk and ("send_everything" in risk or "pressure" in risk):
        return Decision("request", 2, ["risk signals in the request require the owner's approval"], warnings)
    return Decision("allow", 1, ["allowlisted recipient within the per-transfer and 24-hour caps"], warnings)
