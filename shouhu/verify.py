"""Judge's verifier: from a transaction hash to the decoded on-chain events and the agent's audit entry.

    uv run shouhu-verify --chain sepolia 0x<tx hash>     one transaction
    uv run shouhu-verify --chain sepolia --all           every payment of the wallet, newest first

No keys are needed; this only reads the chain and the audit logs shipped in evidence/.
"""
from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path

from web3.logs import DISCARD

from . import config, contacts as cm
from .audit import Audit
from .chain import Chain, hx
from .money import fmt


def audit_index() -> dict:
    """intent id -> (decision entry, file) from the live log and every exported bundle."""
    paths = [config.AUDIT_PATH] + [Path(p) for p in glob.glob(str(config.EVIDENCE_DIR / "runs" / "*" / "audit_log.jsonl"))]
    index = {}
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf8").splitlines():
            if not line.strip():
                continue
            e = json.loads(line)
            if e.get("event") == "decision":
                iid = "0x" + Audit.intent_id(e).hex()
                index.setdefault(iid, (e, p))
    return index


def describe_tx(chain: Chain, tx_hash: str, names: dict, index: dict) -> None:
    # public endpoints prune old receipts; with_history tries the endpoints that keep them
    chain, r, tx = chain.with_history(lambda c: (c, c.w3.eth.get_transaction_receipt(tx_hash), c.w3.eth.get_transaction(tx_hash)),
                                      "the transaction")
    who = {chain.deployment["agent"].lower(): "the AGENT key", chain.deployment["owner"].lower(): "the OWNER key"}
    print(f"transaction {tx_hash}")
    print(f"  block {r['blockNumber']}   status {'SUCCESS' if r['status'] == 1 else 'FAILED'}   from {tx['from']} ({who.get(tx['from'].lower(), 'other')})")
    print(f"  to    {r['to'] or 'contract creation'}" + ("   (the PolicyWallet contract)" if r["to"] and r["to"].lower() == chain.wallet.address.lower() else ""))
    if chain.explorer_tx(tx_hash):
        print(f"  explorer {chain.explorer_tx(tx_hash)}")
    found = False
    for ev in chain.wallet.events.Payment().process_receipt(r, errors=DISCARD):
        a = ev["args"]; iid = hx(bytes(a["intentId"])); found = True
        print(f"  event Payment: {fmt(a['amount'])} to {names.get(a['to'].lower(), a['to'])} ({a['to']}), via owner approval = {a['viaApproval']}")
        print(f"    intent id {iid}")
        _print_audit(iid, index)
    for ev in chain.wallet.events.ApprovalGranted().process_receipt(r, errors=DISCARD):
        a = ev["args"]; iid = hx(bytes(a["intentId"])); found = True
        print(f"  event ApprovalGranted: owner approved {fmt(a['amount'])} to {names.get(a['to'].lower(), a['to'])} ({a['to']}) once")
        print(f"    intent id {iid}")
        _print_audit(iid, index)
    for ev in chain.wallet.events.AllowlistUpdated().process_receipt(r, errors=DISCARD):
        a = ev["args"]; found = True
        print(f"  event AllowlistUpdated: {names.get(a['to'].lower(), a['to'])} ({a['to']}) {'added to' if a['allowed'] else 'removed from'} the allowlist")
    for ev in chain.wallet.events.PolicyUpdated().process_receipt(r, errors=DISCARD):
        a = ev["args"]; found = True
        print(f"  event PolicyUpdated: per-transfer cap {fmt(a['perTransferCap'])}, 24-hour cap {fmt(a['rollingCap'])}")
    for ev in chain.wallet.events.PausedSet().process_receipt(r, errors=DISCARD):
        found = True
        print(f"  event PausedSet: agent {'paused' if ev['args']['paused'] else 'resumed'}")
    for ev in chain.token.events.Transfer().process_receipt(r, errors=DISCARD):
        a = ev["args"]
        print(f"  event tUSDC Transfer: {fmt(a['value'])} from {names.get(a['from'].lower(), a['from'])} to {names.get(a['to'].lower(), a['to'])}")
    if r.get("contractAddress"):
        print(f"  created contract {r['contractAddress']}")
    if not found and not r.get("contractAddress"):
        print("  no PolicyWallet event in this transaction (a tUSDC transfer above means money moved into or out of the wallet)")


def _print_audit(iid: str, index: dict) -> None:
    hit = index.get(iid)
    if not hit:
        print("    audit entry: not found in the local evidence (the log of that run is not in this checkout)")
        return
    e, p = hit
    when = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(e["ts"]))
    print(f"    audit entry ({p.relative_to(config.ROOT)}, {when}):")
    print(f"      user said   : {e.get('user_message', '')!r}")
    print(f"      decision    : {e.get('action')} (tier {e.get('tier')}) for {fmt(int(e.get('amount', 0)))} to {e.get('name') or e.get('resolved')}")
    print(f"      reasons     : {'; '.join(e.get('reasons', []))}")
    if e.get("warnings"):
        print(f"      warnings    : {'; '.join(e.get('warnings', []))}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-verify", description="Verify a transaction hash against the chain and the audit log")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("tx_hash", nargs="?")
    ap.add_argument("--all", action="store_true", help="list every payment of the wallet with its audit entry")
    a = ap.parse_args(argv)
    chain = Chain(a.chain)
    if not chain.deployment:
        raise SystemExit(f"no deployment file for {a.chain}")
    names = {c.address.lower(): c.name for c in cm.load()}
    names[chain.wallet.address.lower()] = "the PolicyWallet"
    index = audit_index()
    print(f"PolicyWallet {chain.wallet.address} on {a.chain}; audit entries indexed: {len(index)}")
    if a.all:
        for p in chain.payments(limit=200):
            print()
            describe_tx(chain, p["tx_hash"], names, index)
    elif a.tx_hash:
        print()
        describe_tx(chain, a.tx_hash, names, index)
    else:
        ap.error("give a transaction hash or --all")


if __name__ == "__main__":
    main()
