"""The five tools. Every write goes through the policy engine before anything is signed."""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import screen
from .audit import Audit
from .chain import Chain, ChainError
from .contacts import Contact
from .money import AmountError, fmt, to_units
from .policy import PolicyState, evaluate_transfer, resolve_recipient
from .requests_store import Requests

TOOLS = [
    {
        "name": "get_portfolio",
        "description": "Wallet balance, the owner's policy (per-transfer cap, 24-hour cap, spent so far, paused), the allowlisted contacts and any pending approval requests. Call this before answering questions about money or limits.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "get_history",
        "description": "Recent payments made from the wallet, newest first, with transaction hashes.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "1 to 50"}},
                         "required": ["limit"], "additionalProperties": False},
    },
    {
        "name": "check_recipient",
        "description": "Resolve a contact name, nickname (English or Chinese) or raw 0x address and report whether it is a known contact, whether it is allowlisted, and any warnings (lookalike address, unknown recipient). Use it when a request names someone and before any payment.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {"recipient": {"type": "string"}}, "required": ["recipient"], "additionalProperties": False},
    },
    {
        "name": "transfer",
        "description": "Pay tUSDC from the wallet. The policy engine decides: within policy it executes on-chain and returns the transaction hash; outside policy it files an approval request for the owner and returns the request id; unsafe requests are refused with reasons. Pass request_id to complete a request the owner has already approved.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {
            "recipient": {"type": "string", "description": "contact name, nickname, or a raw 0x address copied from the user's message"},
            "amount": {"type": "string", "description": "amount in tUSDC, e.g. '20' or '19.5'"},
            "memo": {"type": ["string", "null"]},
            "request_id": {"type": ["string", "null"], "description": "an approved request id such as R1, when completing an approved payment"}},
            "required": ["recipient", "amount", "memo", "request_id"], "additionalProperties": False},
    },
    {
        "name": "request_owner_approval",
        "description": "File an approval request for a payment that the user wants but policy does not allow automatically (new recipient, above a cap). Only the owner can approve it, with their own key, outside this chat.",
        "strict": True,
        "input_schema": {"type": "object", "properties": {
            "recipient": {"type": "string"}, "amount": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["recipient", "amount", "reason"], "additionalProperties": False},
    },
]


@dataclass
class ToolContext:
    chain: Chain
    contacts: list
    audit: Audit
    requests: Requests
    agent_account: object            # eth_account LocalAccount for the agent key
    user_message: str = ""
    risk: list = None


def _contact_name(contacts: list[Contact], addr: str) -> str | None:
    return next((c.name for c in contacts if c.address.lower() == addr.lower()), None)


def _state(ctx: ToolContext, addr: str | None) -> PolicyState:
    s = ctx.chain.wallet_state()
    allow = {}
    if addr:
        allow[addr.lower()] = ctx.chain.is_allowlisted(addr)
    return PolicyState(per_transfer_cap=s["per_transfer_cap"], rolling_cap=s["rolling_cap"], spent_24h=s["spent_24h"],
                       paused=s["paused"], balance=s["balance"], allowlist=allow)


def get_portfolio(ctx: ToolContext) -> dict:
    s = ctx.chain.wallet_state()
    allowlisted = [{"name": c.name, "address": c.address} for c in ctx.contacts if ctx.chain.is_allowlisted(c.address)]
    pending = [{"id": r["id"], "to": r["name"] or r["to"], "amount": fmt(r["amount"]), "status": r["status"], "reasons": r["reasons"]}
               for r in ctx.requests.list() if r["status"] in ("pending", "approved")]
    return {
        "wallet_address": s["wallet"], "balance": fmt(s["balance"]),
        "policy": {"per_transfer_cap": fmt(s["per_transfer_cap"]), "rolling_24h_cap": fmt(s["rolling_cap"]),
                   "spent_last_24h": fmt(s["spent_24h"]), "headroom_24h": fmt(s["headroom"]), "paused": s["paused"],
                   "enforced_by": "PolicyWallet smart contract; only the owner key can change it"},
        "allowlisted_contacts": allowlisted,
        "approval_requests": pending,
        "chain": ctx.chain.name,
    }


def get_history(ctx: ToolContext, limit: int = 10) -> dict:
    items = []
    for p in ctx.chain.payments(limit=limit):
        items.append({"to": _contact_name(ctx.contacts, p["to"]) or p["to"], "amount": fmt(p["amount"]),
                      "via_owner_approval": p["via_approval"], "tx_hash": p["tx_hash"],
                      "explorer": ctx.chain.explorer_tx(p["tx_hash"]), "intent_id": p["intent_id"]})
    return {"payments": items, "count": len(items)}


def check_recipient(ctx: ToolContext, recipient: str) -> dict:
    res = resolve_recipient(recipient, ctx.contacts, ctx.user_message)
    out = {"query": recipient, "resolved_name": res.name, "address": res.address, "candidates": res.candidates,
           "is_contact": bool(res.name), "provenance_ok": res.provenance_ok, "note": res.note, "warnings": []}
    if res.address:
        out["allowlisted"] = ctx.chain.is_allowlisted(res.address)
    if res.lookalike_of:
        out["warnings"].append(f"ADDRESS POISONING: looks like {res.lookalike_of}'s address but differs in the middle")
    if res.first_time:
        out["warnings"].append("first-time recipient, not a contact; a payment will need the owner's approval")
    if res.address and not res.provenance_ok:
        out["warnings"].append("this address did not come from the user's message or the contacts and cannot be paid")
    return out


def _execute(ctx: ToolContext, res, amount: int, intent_id: bytes, memo: str, via_approval: bool) -> dict:
    try:
        if via_approval:
            rcpt = ctx.chain.agent_transfer_with_approval(ctx.agent_account, res.address, amount, intent_id)
        else:
            rcpt = ctx.chain.agent_transfer(ctx.agent_account, res.address, amount, intent_id)
    except ChainError as e:
        ctx.audit.log("chain_rejected", to=res.address, amount=amount, intent_id="0x" + intent_id.hex(), error=str(e))
        return {"status": "rejected_by_contract", "detail": str(e),
                "note": "the smart contract refused the transaction; the policy engine and the chain enforce the same limits"}
    ctx.audit.log("executed", to=res.address, name=res.name, amount=amount, intent_id="0x" + intent_id.hex(),
                  tx_hash=rcpt.tx_hash, block=rcpt.block, via_approval=via_approval, memo=memo)
    return {"status": "executed", "to": res.name or res.address, "address": res.address, "amount": fmt(amount),
            "tx_hash": rcpt.tx_hash, "block": rcpt.block, "explorer": ctx.chain.explorer_tx(rcpt.tx_hash),
            "intent_id": "0x" + intent_id.hex(), "via_owner_approval": via_approval}


def transfer(ctx: ToolContext, recipient: str, amount: str, memo: str | None = None, request_id: str | None = None,
             force_request: bool = False, reason: str = "") -> dict:
    memo = memo or ""
    try:
        units = to_units(amount)
    except AmountError as e:
        return {"status": "refused", "reasons": [str(e)]}
    # completing an approved request
    if request_id:
        req = ctx.requests.get(request_id)
        if not req:
            return {"status": "refused", "reasons": [f"no request {request_id}"]}
        if req["status"] != "approved":
            return {"status": "refused", "reasons": [f"request {req['id']} is {req['status']}, not approved by the owner"]}
        intent = bytes.fromhex(req["intent_id"][2:])
        appr = ctx.chain.approval(intent)
        if appr["used"] or appr["to"].lower() != req["to"].lower() or appr["amount"] != req["amount"]:
            return {"status": "refused", "reasons": ["the on-chain approval does not match the request or was already used"]}
        res = resolve_recipient(req["to"], ctx.contacts, req["to"])
        out = _execute(ctx, res, req["amount"], intent, memo, via_approval=True)
        if out["status"] == "executed":
            ctx.requests.update(req["id"], status="executed", exec_tx=out["tx_hash"])
            out["request_id"] = req["id"]
        return out
    res = resolve_recipient(recipient, ctx.contacts, ctx.user_message)
    state = _state(ctx, res.address)
    decision = evaluate_transfer(units, res, state, ctx.risk or [])
    entry = ctx.audit.log("decision", recipient=recipient, resolved=res.address, name=res.name, amount=units,
                          action=decision.action, tier=decision.tier, reasons=decision.reasons, warnings=decision.warnings,
                          risk=ctx.risk or [], user_message=ctx.user_message[:300])
    intent_id = Audit.intent_id(entry)
    base = {"decision": decision.action, "tier": decision.tier, "reasons": decision.reasons, "warnings": decision.warnings}
    if decision.action == "refuse":
        return {"status": "refused", **base}
    if decision.action == "request" or force_request:
        req = ctx.requests.create("0x" + intent_id.hex(), res.address, res.name, units, decision.reasons + ([reason] if reason else []), memo)
        ctx.audit.log("request_filed", request_id=req["id"], intent_id=req["intent_id"], to=res.address, amount=units)
        return {"status": "needs_owner_approval", "request_id": req["id"], "to": res.name or res.address, "amount": fmt(units), **base,
                "how_to_approve": f"the owner runs: shouhu-owner approve {req['id']}  (with the owner key, outside this chat); then ask me to complete {req['id']}"}
    return {**_execute(ctx, res, units, intent_id, memo, via_approval=False), **base}


def request_owner_approval(ctx: ToolContext, recipient: str, amount: str, reason: str) -> dict:
    return transfer(ctx, recipient, amount, memo=reason, request_id=None, force_request=True, reason=reason)


def run_tool(ctx: ToolContext, name: str, args: dict) -> str:
    """Dispatch a tool call; all results are JSON text. Untrusted strings are wrapped before they reach the model."""
    try:
        if name == "get_portfolio":
            out = get_portfolio(ctx)
        elif name == "get_history":
            out = get_history(ctx, max(1, min(50, int(args.get("limit", 10) or 10))))
        elif name == "check_recipient":
            out = check_recipient(ctx, str(args.get("recipient", "")))
        elif name == "transfer":
            out = transfer(ctx, str(args.get("recipient", "")), str(args.get("amount", "")), args.get("memo"), args.get("request_id"))
        elif name == "request_owner_approval":
            out = request_owner_approval(ctx, str(args.get("recipient", "")), str(args.get("amount", "")), str(args.get("reason", "")))
        else:
            return json.dumps({"error": f"unknown tool {name}"})
    except ChainError as e:
        out = {"status": "chain_error", "detail": str(e)}
    out = _quarantine(out)
    return json.dumps(out, ensure_ascii=False, default=str)


def _quarantine(obj):
    """Any free text that came from outside (memos, names from data) is wrapped as untrusted data."""
    if isinstance(obj, dict):
        return {k: (screen.wrap_untrusted(v, k) if k in ("memo", "token_name", "note_from_chain") and isinstance(v, str) else _quarantine(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_quarantine(x) for x in obj]
    return obj
