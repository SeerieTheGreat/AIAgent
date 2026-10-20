"""The wallet's ledger: every event the PolicyWallet emitted plus every token transfer into it, read from the chain.

Payments, the owner's one-time approvals, allowlist and limit changes, pauses and money added to the wallet, newest
first, each with its transaction hash so the proof page can re-check it."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from eth_utils import keccak

from .chain import Chain, hx
from .money import fmt

WALLET_EVENTS = ("Payment", "ApprovalGranted", "AllowlistUpdated", "PolicyUpdated", "PausedSet", "AgentUpdated")
ZERO = "0x" + "0" * 40
CHUNK = 4000                      # block range public endpoints accept for eth_getLogs
_BLOCK_TIME: dict = {}            # (chain id, block) -> unix time; blocks never change, so this cache never expires


def _signature(abi: list, name: str) -> str:
    item = next(i for i in abi if i.get("type") == "event" and i["name"] == name)
    return "0x" + keccak(text=f"{name}({','.join(i['type'] for i in item['inputs'])})").hex()


def _block_times(chain: Chain, blocks: set) -> dict:
    cid = chain.cfg["chain_id"]
    missing = [b for b in blocks if (cid, b) not in _BLOCK_TIME]
    if missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for b, ts in zip(missing, pool.map(lambda n: chain.w3.eth.get_block(n)["timestamp"], missing)):
                _BLOCK_TIME[(cid, b)] = ts
    return {b: _BLOCK_TIME[(cid, b)] for b in blocks}


def read_ledger(chain: Chain, limit: int = 300) -> list[dict]:
    """Raw entries, newest first: kind, block, log index, tx hash, time and the decoded fields."""
    w3, wallet, token = chain.w3, chain.wallet, chain.token
    topics = {_signature(chain.wallet_abi, n): n for n in WALLET_EVENTS}
    transfer_topic = _signature(chain.token_abi, "Transfer")
    to_wallet = "0x" + "0" * 24 + wallet.address[2:].lower()
    start, latest = int(chain.deployment.get("deploy_block", 0)), w3.eth.block_number
    logs = []
    for frm in range(start, latest + 1, CHUNK):
        to = min(frm + CHUNK - 1, latest)
        logs += w3.eth.get_logs({"address": wallet.address, "fromBlock": frm, "toBlock": to})
        logs += w3.eth.get_logs({"address": token.address, "fromBlock": frm, "toBlock": to, "topics": [transfer_topic, None, to_wallet]})
    entries = []
    for lg in logs:
        base = {"block": lg["blockNumber"], "log_index": lg["logIndex"], "tx_hash": hx(lg["transactionHash"])}
        t0 = hx(lg["topics"][0]) if lg["topics"] else ""
        if lg["address"].lower() == wallet.address.lower() and t0 in topics:
            name = topics[t0]
            a = wallet.events[name]().process_log(lg)["args"]
            if name == "Payment":
                entries.append({**base, "kind": "payment", "party": a["to"], "amount_units": int(a["amount"]),
                                "by": a["by"], "via_approval": bool(a["viaApproval"]), "intent_id": hx(a["intentId"])})
            elif name == "ApprovalGranted":
                entries.append({**base, "kind": "approval", "party": a["to"], "amount_units": int(a["amount"]), "intent_id": hx(a["intentId"])})
            elif name == "AllowlistUpdated":
                entries.append({**base, "kind": "allowlist", "party": a["to"], "allowed": bool(a["allowed"])})
            elif name == "PolicyUpdated":
                entries.append({**base, "kind": "policy", "per_transfer_cap": int(a["perTransferCap"]), "rolling_cap": int(a["rollingCap"])})
            elif name == "PausedSet":
                entries.append({**base, "kind": "pause", "paused": bool(a["paused"])})
            else:
                entries.append({**base, "kind": "agent", "party": a["agent"]})
        elif lg["address"].lower() == token.address.lower():
            a = token.events.Transfer().process_log(lg)["args"]
            entries.append({**base, "kind": "deposit", "party": a["from"], "amount_units": int(a["value"]), "minted": a["from"] == ZERO})
    entries.sort(key=lambda e: (e["block"], e["log_index"]), reverse=True)
    entries = entries[:limit]
    times = _block_times(chain, {e["block"] for e in entries})
    for e in entries:
        e["time"] = times.get(e["block"])
    return entries


def describe(entries: list[dict], chain: Chain, contacts) -> tuple[list[dict], dict]:
    """Add names, titles and explorer links for the page, and the summary numbers at the top of it."""
    names = {c.address.lower(): c.name for c in contacts}
    d = chain.deployment
    agent, owner = d["agent"].lower(), d["owner"].lower()
    stats = {"payments": 0, "paid_units": 0, "tier1": 0, "tier2": 0, "approvals": 0, "deposits_units": 0, "deposits": 0,
             "rule_changes": 0}
    out = []
    for e in entries:
        party = e.get("party")
        who = names.get((party or "").lower()) if party else None
        label = who or (party and party[:6] + "…" + party[-4:])
        row = {**e, "party_name": who, "explorer": chain.explorer_tx(e["tx_hash"])}
        if "amount_units" in e:
            row["amount"] = fmt(e["amount_units"])
            shown = fmt(e["amount_units"], group=True)
        k = e["kind"]
        if k == "payment":
            by = (e.get("by") or "").lower()
            row["signer"] = "agent" if by == agent else "owner" if by == owner else "other"
            row["group"] = "payments"
            if row["signer"] == "agent":
                row["tier"] = 2 if e["via_approval"] else 1
                row["title"] = f"Paid {shown} to {label}"
                row["detail"] = "Tier 2 · with the parent's one-time approval" if e["via_approval"] else "Tier 1 · inside the limits"
                stats["tier2" if e["via_approval"] else "tier1"] += 1
            else:
                row["title"] = f"Owner sent {shown} to {label}"
                row["detail"] = "owner transfer"
            stats["payments"] += 1
            stats["paid_units"] += e["amount_units"]
        elif k == "approval":
            row.update(signer="owner", group="approvals", title=f"Parent approved {shown} to {label}, once",
                       detail="one-time approval for this recipient and amount")
            stats["approvals"] += 1
        elif k == "allowlist":
            row.update(signer="owner", group="rules", title=f"{label} {'added to' if e['allowed'] else 'removed from'} the allowlist",
                       detail="contact registration" if e["allowed"] else "contact removed")
            stats["rule_changes"] += 1
        elif k == "policy":
            row.update(signer="owner", group="rules", title=f"Limits set: {fmt(e['per_transfer_cap'], group=True)} per payment, {fmt(e['rolling_cap'], group=True)} per 24 h",
                       detail="spending limits")
            stats["rule_changes"] += 1
        elif k == "pause":
            row.update(signer="owner", group="rules", title="Agent paused" if e["paused"] else "Agent resumed", detail="pause switch")
            stats["rule_changes"] += 1
        elif k == "agent":
            current = (party or "").lower() == agent
            row.update(signer="owner", group="rules", title="Agent key set" if current else f"Agent key set to {label}",
                       detail="the key Shouhu signs payments with")
            if current:
                row["party_name"] = "Shouhu (agent key)"
            stats["rule_changes"] += 1
        else:
            row.update(signer="other", group="deposits", title=f"Added {shown} to the wallet",
                       detail="test money minted" if e["minted"] else f"from {label}")
            if e["minted"]:
                row["party_name"] = "tUSDC mint (test money)"
            stats["deposits"] += 1
            stats["deposits_units"] += e["amount_units"]
        out.append(row)
    stats["paid"] = fmt(stats["paid_units"])
    stats["deposited"] = fmt(stats["deposits_units"])
    return out, stats
