"""Owner command. Runs in its own process with the owner key; the agent never sees it."""
from __future__ import annotations

import argparse
import sys

from eth_utils import to_checksum_address

from . import config, contacts as contacts_mod
from .chain import Chain, ChainError, account_from
from .money import fmt, to_units
from .requests_store import Requests


def _resolve(contacts, query: str) -> str:
    hits = contacts_mod.find(contacts, query)
    if len(hits) == 1:
        return hits[0].address
    if query.startswith("0x") and len(query) == 42:
        return to_checksum_address(query)
    raise SystemExit(f"could not resolve '{query}' to one contact or address")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-owner", description="Owner-only governance of the policy wallet")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("requests")
    p = sub.add_parser("approve"); p.add_argument("request_id"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("deny"); p.add_argument("request_id")
    p = sub.add_parser("policy"); p.add_argument("--per-transfer", type=float, required=True); p.add_argument("--rolling", type=float, required=True)
    p = sub.add_parser("allow"); p.add_argument("who")
    p = sub.add_parser("disallow"); p.add_argument("who")
    sub.add_parser("pause"); sub.add_parser("unpause")
    p = sub.add_parser("mint"); p.add_argument("amount")
    p = sub.add_parser("fund-agent"); p.add_argument("eth", type=float)
    p = sub.add_parser("pay"); p.add_argument("who"); p.add_argument("amount")
    a = ap.parse_args(argv)

    chain = Chain(a.chain)
    if not chain.deployment:
        sys.exit(f"no deployment for {a.chain}; run shouhu-deploy first")
    contacts = contacts_mod.load()
    owner = None if a.cmd in ("status", "requests") else account_from(config.owner_key())
    reqs = Requests()
    try:
        if a.cmd == "status":
            s = chain.wallet_state()
            print(f"wallet {s['wallet']} on {a.chain}\nbalance {fmt(s['balance'])}\nper-transfer cap {fmt(s['per_transfer_cap'])}  24h cap {fmt(s['rolling_cap'])}  spent 24h {fmt(s['spent_24h'])}  paused {s['paused']}")
            print(f"owner {s['owner']}  agent {s['agent']}  agent gas {chain.eth_balance(s['agent']) / 1e18:.4f} ETH")
            for c in contacts:
                print(f"  {'allow' if chain.is_allowlisted(c.address) else '  -  '}  {c.name:18s} {c.address}")
        elif a.cmd == "requests":
            for r in reqs.list():
                print(f"{r['id']:4s} {r['status']:9s} {fmt(r['amount']):>14s} -> {r['name'] or r['to']}  reasons: {'; '.join(r['reasons'])}")
        elif a.cmd == "approve":
            r = reqs.get(a.request_id)
            if not r:
                sys.exit(f"no request {a.request_id}")
            if r["status"] != "pending":
                sys.exit(f"request {r['id']} is {r['status']}")
            print("Approve this exact payment once?")
            print(f"  request   {r['id']}\n  to        {r['name'] or '(not a contact)'}  {r['to']}\n  amount    {fmt(r['amount'])}\n  reasons   {'; '.join(r['reasons'])}\n  intent id {r['intent_id']}")
            if not a.yes and input("type yes to approve: ").strip().lower() != "yes":
                print("not approved")
                return
            rc = chain.approve_once(owner, bytes.fromhex(r["intent_id"][2:]), r["to"], r["amount"])
            reqs.update(r["id"], status="approved", approve_tx=rc.tx_hash)
            print(f"approved on-chain  tx {rc.tx_hash}  {chain.explorer_tx(rc.tx_hash) or ''}\nnow tell the agent: complete {r['id']}")
        elif a.cmd == "deny":
            reqs.update(a.request_id, status="denied")
            print("denied")
        elif a.cmd == "policy":
            rc = chain.set_policy(owner, to_units(a.per_transfer), to_units(a.rolling))
            print(f"policy updated  tx {rc.tx_hash}")
        elif a.cmd in ("allow", "disallow"):
            addr = _resolve(contacts, a.who)
            rc = chain.set_allowlist(owner, addr, a.cmd == "allow")
            print(f"{a.cmd} {addr}  tx {rc.tx_hash}")
        elif a.cmd in ("pause", "unpause"):
            rc = chain.set_paused(owner, a.cmd == "pause")
            print(f"{a.cmd}d  tx {rc.tx_hash}")
        elif a.cmd == "mint":
            rc = chain.mint(owner, chain.deployment["wallet"], to_units(a.amount))
            print(f"minted  tx {rc.tx_hash}")
        elif a.cmd == "fund-agent":
            rc = chain.send_eth(owner, chain.deployment["agent"], int(a.eth * 1e18))
            print(f"funded agent  tx {rc.tx_hash}")
        elif a.cmd == "pay":
            addr = _resolve(contacts, a.who)
            rc = chain.owner_transfer(owner, addr, to_units(a.amount), b"\x00" * 32)
            print(f"owner payment sent  tx {rc.tx_hash}")
    except ChainError as e:
        sys.exit(f"chain error: {e}")


if __name__ == "__main__":
    main()
