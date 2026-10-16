"""Content screening: untrusted text is wrapped and labelled; the user's own wording is scanned for pressure."""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (all |your |the |previous )*(rules|instructions|policy|policies)",
    r"disregard (all |your |the |previous )*(rules|instructions|policy)",
    r"system (notice|message|override|prompt)",
    r"(send|transfer|pay) (all|everything|the (whole|entire)).{0,40}(to|into)",
    r"(send|transfer|pay) \d[\d,\.]* ?\w* to (account|address|0x)",
    r"you must (now )?(send|transfer|pay)",
    r"new (policy|instruction)",
    r"developer(s)? (of|from) (shouhu|the wallet)",
    r"pre-?approved",
]
_INJECTION = re.compile("|".join(f"(?:{p})" for p in INJECTION_PATTERNS), re.IGNORECASE)

RISK_RULES = {
    "urgency": re.compile(r"\b(urgent|urgently|right now|immediately|asap|hurry|last chance|within the hour|马上|立刻|紧急|赶紧)\b", re.IGNORECASE),
    "secrecy": re.compile(r"(don'?t tell|do not tell|keep (this|it) (secret|between)|secret(ly)?|别告诉|不要告诉|保密)", re.IGNORECASE),
    "send_everything": re.compile(r"\b(all my (money|funds|usdc|tokens)|everything (i|we) have|the whole balance|entire balance|全部|所有的钱)\b", re.IGNORECASE),
    "pressure": re.compile(r"(or else|you will (lose|regret)|threat|evict(ed|ion)|arrest|police|frozen account|account (is|was) (hacked|compromised))", re.IGNORECASE),
    "authority_claim": re.compile(r"(i am (the )?(owner|admin|developer)|as (the )?owner|on behalf of (the )?owner|owner (has )?(said|says|authori[sz]ed))", re.IGNORECASE),
}


def injection_flags(text: str) -> list[str]:
    return ["possible_injection"] if text and _INJECTION.search(text) else []


def wrap_untrusted(text: str, source: str) -> dict:
    """Return a data record the model receives. Text inside it is never an instruction."""
    text = text or ""
    return {"source": source, "untrusted_text": text[:500], "flags": injection_flags(text)}


def risk_flags(user_text: str) -> list[str]:
    return [name for name, rx in RISK_RULES.items() if user_text and rx.search(user_text)]


SECRET_REQUEST = re.compile(r"(private key|secret key|seed phrase|mnemonic|api key|system prompt|your instructions|your rules in full|\.env|password|pin code)", re.IGNORECASE)


def asks_for_secrets(user_text: str) -> bool:
    return bool(user_text and SECRET_REQUEST.search(user_text))
