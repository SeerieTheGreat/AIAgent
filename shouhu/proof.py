"""Proof of transaction: re-read one transaction from the chain and check it against the wallet rules and our records.

Nothing here trusts the chat or the model. Every field comes from the node (transaction, receipt, block, contract
state) or from the local records the agent cannot edit after the fact (audit log entries hash to the intent id)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from web3.exceptions import TransactionNotFound
from web3.logs import DISCARD

from . import config
from .audit import Audit
from .chain import Chain, hx
from .money import fmt

TX_RE = re.compile(r"0x[0-9a-fA-F]{64}")
WALLET_EVENTS = ("Payment", "ApprovalGranted", "AllowlistUpdated", "PolicyUpdated", "PausedSet", "AgentUpdated")


def find_decision(intent_id: str, audit_path: Path | None = None) -> dict | None:
    """The policy decision whose log entry hashes to this intent id, if it is in the local audit log."""
    path = Path(audit_path) if audit_path else config.AUDIT_PATH
    if not path.exists():
        return None
    want = intent_id.lower()
    with path.open(encoding="utf8") as f:
        for line in f:
            if '"decision"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") == "decision" and "0x" + Audit.intent_id(e).hex() == want:
                return e
    return None


def _label(addr: str, chain: Chain, names: dict) -> str:
    a = (addr or "").lower()
    d = chain.deployment
    return {d["wallet"].lower(): "Shouhu policy wallet (contract)", d["token"].lower(): "tUSDC token (contract)",
            d["owner"].lower(): "owner key (parent)", d["agent"].lower(): "agent key (Shouhu)"}.get(a) or names.get(a) or ""


def verify_tx(chain: Chain, tx_hash: str, contacts=(), requests=None, audit_path=None, owner_log=None) -> dict:
    tx_hash = (tx_hash or "").strip()
    if not TX_RE.fullmatch(tx_hash):
        return {"found": False, "error": "a transaction hash is 0x followed by 64 hexadecimal characters"}
    w3, d = chain.w3, chain.deployment
    try:
        tx = w3.eth.get_transaction(tx_hash)
        rc = w3.eth.get_transaction_receipt(tx_hash)
    except TransactionNotFound:
        return {"found": False, "tx_hash": tx_hash, "chain": chain.name,
                "error": f"no confirmed transaction with this hash on {chain.name}"}
    block = w3.eth.get_block(rc["blockNumber"])
    latest = w3.eth.block_number
    names = {c.address.lower(): c.name for c in contacts}
    label = lambda a: _label(a, chain, names)

    events = []
    for name in WALLET_EVENTS:
        for ev in chain.wallet.events[name]().process_receipt(rc, errors=DISCARD):
            if ev["address"].lower() == d["wallet"].lower():
                events.append((name, dict(ev["args"]), ev["logIndex"]))
    transfers = [dict(ev["args"]) for ev in chain.token.events.Transfer().process_receipt(rc, errors=DISCARD)
                 if ev["address"].lower() == d["token"].lower()]
    events.sort(key=lambda e: e[2])

    def show(name, a):
        if name == "Payment":
            return {"intent id": hx(a["intentId"]), "to": f"{a['to']} {label(a['to'])}".strip(), "amount": fmt(a["amount"]),
                    "signed by": f"{a['by']} {label(a['by'])}".strip(), "via owner approval": bool(a["viaApproval"])}
        if name == "ApprovalGranted":
            return {"intent id": hx(a["intentId"]), "to": f"{a['to']} {label(a['to'])}".strip(), "amount": fmt(a["amount"])}
        if name == "AllowlistUpdated":
            return {"address": f"{a['to']} {label(a['to'])}".strip(), "allowed": bool(a["allowed"])}
        if name == "PolicyUpdated":
            return {"per-transfer cap": fmt(a["perTransferCap"]), "24-hour cap": fmt(a["rollingCap"])}
        if name == "PausedSet":
            return {"paused": bool(a["paused"])}
        return {k: str(v) for k, v in a.items()}

    sender, target = tx["from"], tx.get("to") or ""
    ok = rc["status"] == 1
    checks = [
        (ok, f"Included in block {rc['blockNumber']} with status success" if ok else f"Included in block {rc['blockNumber']} but it reverted"),
        (latest - rc["blockNumber"] + 1 >= 1, f"{latest - rc['blockNumber'] + 1} confirmation(s) on {chain.name} (chain id {chain.cfg['chain_id']})"),
        (target.lower() == d["wallet"].lower(), "Sent to the Shouhu policy wallet contract" if target.lower() == d["wallet"].lower()
         else f"Sent to {target or 'a new contract'}, not to the Shouhu policy wallet"),
    ]
    role = label(sender)
    checks.append((sender.lower() in (d["owner"].lower(), d["agent"].lower()),
                   f"Signed by the {role}" if role in ("owner key (parent)", "agent key (Shouhu)") else f"Signed by {sender}, an outside key"))

    kind, title, intent, decision, request = "other", "Transaction", None, None, None
    reqs = requests.list() if requests else []
    pay = next((a for n, a, _ in events if n == "Payment"), None)
    grant = next((a for n, a, _ in events if n == "ApprovalGranted"), None)
    if pay:
        kind = "payment"
        intent = hx(pay["intentId"])
        to_name = label(pay["to"]) or pay["to"]
        title = f"Payment of {fmt(pay['amount'])} to {to_name}"
        moved = any(t["from"].lower() == d["wallet"].lower() and t["to"].lower() == pay["to"].lower() and t["value"] == pay["amount"]
                    for t in transfers)
        checks.append((moved, f"The token contract moved {fmt(pay['amount'])} from the wallet to {to_name}" if moved
                       else "No matching token transfer in this transaction"))
        if pay["by"].lower() == d["agent"].lower():
            if pay["viaApproval"]:
                appr = chain.approval(bytes(pay["intentId"]))
                good = appr["used"] and appr["to"].lower() == pay["to"].lower() and appr["amount"] == pay["amount"]
                checks.append((good, "Tier 2: the contract holds the owner's one-time approval for exactly this recipient and amount, now used"
                               if good else "Tier 2 payment, but the stored approval does not match"))
            else:
                checks.append((True, "Tier 1: inside the per-transfer cap, the 24-hour cap and the allowlist, or the contract would have reverted"))
    elif grant:
        kind = "approval"
        intent = hx(grant["intentId"])
        title = f"Owner approval: {fmt(grant['amount'])} to {label(grant['to']) or grant['to']}, once"
        checks.append((sender.lower() == d["owner"].lower(), "Only the owner key can grant an approval; this one was signed by it"
                       if sender.lower() == d["owner"].lower() else "Approval not signed by the owner key"))
    elif events:
        name, a, _ = events[0]
        kind = {"AllowlistUpdated": "allowlist", "PolicyUpdated": "policy", "PausedSet": "pause"}.get(name, "other")
        title = {"AllowlistUpdated": lambda: f"Allowlist: {label(a['to']) or a['to']} {'added' if a['allowed'] else 'removed'}",
                 "PolicyUpdated": lambda: f"Spending limits set: {fmt(a['perTransferCap'])} per transfer, {fmt(a['rollingCap'])} per 24 h",
                 "PausedSet": lambda: "Agent paused by the owner" if a["paused"] else "Agent resumed by the owner"}.get(name, lambda: name)()

    if intent:
        decision = find_decision(intent, audit_path)
        if decision:
            checks.append((True, f"The intent id is the hash of policy decision #{decision['seq']} in session {decision['session']} "
                                 f"(action {decision['action']}, tier {decision['tier']})"))
        request = next((r for r in reqs if r["intent_id"].lower() == intent.lower()), None)
        if request:
            checks.append((True, f"Matches approval request {request['id']} ({request['status']})"))
    if not request:
        request = next((r for r in reqs if tx_hash.lower() in ((r.get("approve_tx") or "").lower(), (r.get("exec_tx") or "").lower())), None)
    owner_action = next((x for x in (owner_log or []) if x.get("tx", "").lower() == tx_hash.lower()), None)

    fee = rc["gasUsed"] * rc.get("effectiveGasPrice", tx.get("gasPrice", 0) or 0)
    return {
        "found": True, "tx_hash": hx(tx["hash"]), "chain": chain.name, "chain_id": chain.cfg["chain_id"],
        "explorer": chain.explorer_tx(hx(tx["hash"])), "kind": kind, "title": title, "success": ok,
        "block": rc["blockNumber"], "block_hash": hx(block["hash"]), "block_time": block["timestamp"],
        "confirmations": latest - rc["blockNumber"] + 1, "from": sender, "from_label": role, "to": target,
        "to_label": label(target), "nonce": tx["nonce"], "gas_used": rc["gasUsed"], "fee_eth": f"{fee / 1e18:.8f}",
        "events": [{"name": n, "args": show(n, a)} for n, a, _ in events],
        "checks": [{"ok": bool(c), "text": t} for c, t in checks],
        "all_ok": all(c for c, _ in checks),
        "intent_id": intent,
        "decision": {k: decision.get(k) for k in ("session", "seq", "ts", "action", "tier", "reasons", "warnings", "user_message", "name")}
        if decision else None,
        "request": {**request, "amount": fmt(request["amount"])} if request else None,
        "owner_action": owner_action,
        "verified_at": time.time(),
    }
