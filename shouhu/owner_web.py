"""Owner console in the browser. Its own process with the owner key; the student's app never sees the key.

Same powers as the shouhu-owner command for the demo path: read status, approve one request exactly as filed,
deny it, pause or unpause the wallet. On top of that: the parent's own sign-up (proved with an owner-key signature) and
the student's one-time invite code, registering contacts (an on-chain allowlist transaction), changing the spending
limits and adding test money (both on-chain), revoking the student's access, the wallet's ledger and a proof page for
any transaction."""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from eth_account import Account
from eth_account.messages import encode_defunct

from . import accounts as accounts_mod, config, contacts as contacts_mod
from .accounts import AccountError, Accounts, make_invite
from .chain import Chain, ChainError, account_from
from .config import UNIT
from .money import AmountError, fmt, to_units
from .proof import verify_tx
from .requests_store import Requests
from .webapp import wallet_ledger, wallet_state_parallel
from .webserver import App, serve

MAX_LIMIT = 1_000_000 * UNIT      # sanity bounds for what the console will sign
MAX_TOPUP = 100_000 * UNIT

class OwnerLog:
    """The owner's on-chain actions from this console (registration, contacts, approvals, pauses), newest last."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.DATA_DIR / "owner_actions.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def list(self) -> list:
        return json.loads(self.path.read_text() or "[]") if self.path.exists() else []

    def add(self, kind: str, text: str, tx: str, chain: str) -> dict:
        with self.lock:
            items = self.list()
            items.append({"kind": kind, "text": text, "tx": tx, "chain": chain, "ts": time.time()})
            self.path.write_text(json.dumps(items, indent=1, ensure_ascii=False))
        return items[-1]


def registration_message(name: str, chain: Chain) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (f"Shouhu owner registration\nParent: {name}\nWallet: {chain.deployment['wallet']}\n"
            f"Chain: {chain.name} ({chain.cfg['chain_id']})\nTime: {stamp}")


def build_app(chain: Chain, owner, requests: Requests | None = None, contacts=None, accounts: Accounts | None = None,
              registered_path=None, owner_log: OwnerLog | None = None, audit_path=None, student_url: str | None = None) -> App:
    app = App("owner.html", "Shouhu owner console")
    app.pages["/proof"] = "proof.html"
    app.pages["/transactions"] = "transactions.html"
    contacts = contacts if contacts is not None else contacts_mod.load(registered_path=registered_path)
    reqs = requests or Requests()
    accounts = accounts or Accounts()
    log = owner_log or OwnerLog()
    app.page_vars = {"chain": chain.name, "read_only": owner is None, "home": "/", "side": "owner",
                     "wallet": chain.deployment["wallet"], "student_url": student_url or "http://127.0.0.1:8787/"}

    def need_owner():
        if owner is None:
            return 403, {"error": "no owner key on this computer (.owner.env); the console is read-only"}
        return None

    pool = ThreadPoolExecutor(max_workers=8)
    lock, cache = threading.Lock(), {}

    def chain_reads() -> dict:
        with lock:                       # polls share one read every few seconds
            if cache and time.time() - cache["ts"] < 3:
                return cache["val"]
            allowed = [pool.submit(chain.is_allowlisted, c.address) for c in contacts]
            s = wallet_state_parallel(chain, pool)
            gas = {a: pool.submit(chain.eth_balance, a) for a in (s["owner"], s["agent"])}
            val = {"s": s, "allowed": [f.result() for f in allowed], "gas": {a: f.result() for a, f in gas.items()}}
            cache.update(ts=time.time(), val=val)
            return val

    def prepare(name: str, body: dict) -> dict:
        """The parent proves control of the wallet: the console signs a statement with the owner key and checks
        that it recovers to the owner stored in the contract. Optional new limits go on-chain in the same step."""
        if owner is None:
            raise AccountError("no owner key on this computer (.owner.env); the parent cannot register here")
        onchain_owner = chain.wallet.functions.owner().call()
        msg = registration_message(name, chain)
        sig = owner.sign_message(encode_defunct(text=msg)).signature
        signer = Account.recover_message(encode_defunct(text=msg), signature=sig)
        if signer.lower() != onchain_owner.lower():
            raise AccountError("the owner key on this computer is not the owner of this wallet")
        profile = {"owner": onchain_owner, "wallet": chain.deployment["wallet"], "chain": chain.name,
                   "statement": msg, "signature": "0x" + bytes(sig).hex(), "policy_tx": None,
                   "invite": None if accounts.exists("student") else make_invite()}
        per, roll = str(body.get("per_transfer_cap") or "").strip(), str(body.get("rolling_cap") or "").strip()
        if per or roll:
            s = chain.wallet_state()
            try:                  # an empty field keeps that limit as it is
                per_u = to_units(per) if per else s["per_transfer_cap"]
                roll_u = to_units(roll) if roll else s["rolling_cap"]
            except AmountError as e:
                raise AccountError(f"limits: {e}") from e
            if per_u > roll_u:
                raise AccountError("the per-transfer cap cannot be larger than the 24-hour cap")
            if (per_u, roll_u) != (s["per_transfer_cap"], s["rolling_cap"]):
                try:
                    rc = chain.set_policy(owner, per_u, roll_u)
                except ChainError as e:
                    raise AccountError(f"chain error while setting the limits: {e}") from e
                profile["policy_tx"] = rc.tx_hash
                log.add("policy", f"Limits set at registration: {fmt(per_u)} per transfer, {fmt(roll_u)} per 24 h", rc.tx_hash, chain.name)
                cache.clear()
        return profile

    accounts_mod.add_routes(app, accounts, "owner", prepare)

    @app.get("/api/state")
    def _state(q):
        reads = chain_reads()
        s, gas = reads["s"], reads["gas"]
        return 200, {
            "chain": chain.name, "wallet": s["wallet"], "wallet_explorer": chain.explorer_address(s["wallet"]),
            "balance": fmt(s["balance"]), "per_transfer_cap": fmt(s["per_transfer_cap"]), "rolling_cap": fmt(s["rolling_cap"]),
            "spent_24h": fmt(s["spent_24h"]), "headroom": fmt(s["headroom"]), "paused": s["paused"],
            "owner": s["owner"], "owner_key_loaded": owner is not None,
            "owner_matches": owner is not None and owner.address.lower() == s["owner"].lower(),
            "owner_gas_eth": round(gas[s["owner"]] / 1e18, 5),
            "agent": s["agent"], "agent_gas_eth": round(gas[s["agent"]] / 1e18, 5),
            "contacts": [{"name": c.name, "alias": next((a for a in c.aliases if not a.isascii()), ""), "address": c.address,
                          "allowlisted": ok, "explorer": chain.explorer_address(c.address)} for c, ok in zip(contacts, reads["allowed"])],
            "account": accounts.public("owner"), "student": _student(), "activity": list(reversed(log.list()))[:20],
            "requests": [{**r, "amount_text": fmt(r["amount"]),
                          "approve_explorer": chain.explorer_tx(r["approve_tx"]) if r.get("approve_tx") else None,
                          "exec_explorer": chain.explorer_tx(r["exec_tx"]) if r.get("exec_tx") else None}
                         for r in reversed(reqs.list())],
        }

    @app.post("/api/approve")
    def _approve(body):
        if (e := need_owner()):
            return e
        r = reqs.get(str(body.get("id", "")))
        if not r:
            return 404, {"error": "no such request"}
        if r["status"] != "pending":
            return 409, {"error": f"request {r['id']} is {r['status']}"}
        # the console sends back exactly what it showed; any drift means the owner did not see this payment
        if body.get("confirm") != "yes" or body.get("intent_id") != r["intent_id"] or int(body.get("amount", -1)) != r["amount"] \
                or str(body.get("to", "")).lower() != r["to"].lower():
            return 400, {"error": "confirmation does not match the request; reload and check the details"}
        try:
            rc = chain.approve_once(owner, bytes.fromhex(r["intent_id"][2:]), r["to"], r["amount"])
        except ChainError as err:
            return 502, {"error": f"chain error: {err}"}
        reqs.update(r["id"], status="approved", approve_tx=rc.tx_hash)
        ledger_cache.clear()
        log.add("approval", f"Approved {r['id']} once: {fmt(r['amount'])} to {r['name'] or r['to']}", rc.tx_hash, chain.name)
        cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash), "id": r["id"]}

    @app.post("/api/deny")
    def _deny(body):
        if (e := need_owner()):
            return e
        r = reqs.get(str(body.get("id", "")))
        if not r or r["status"] != "pending":
            return 409, {"error": "only a pending request can be denied"}
        reqs.update(r["id"], status="denied")
        return 200, {"ok": True}

    @app.post("/api/pause")
    def _pause(body):
        if (e := need_owner()):
            return e
        try:
            rc = chain.set_paused(owner, bool(body.get("paused")))
        except ChainError as err:
            return 502, {"error": f"chain error: {err}"}
        log.add("pause", "Agent paused" if body.get("paused") else "Agent resumed", rc.tx_hash, chain.name)
        ledger_cache.clear()
        cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash)}

    def _student():
        st = accounts.public("student")
        return {"name": st["name"], "chinese_name": st.get("chinese_name", ""), "created": st["created"],
                "invited_by": st.get("invited_by")} if st else None

    @app.post("/api/invite")
    def _invite(body):
        """A fresh one-time code for the student; the old one stops working."""
        if accounts.exists("student"):
            return 409, {"error": "a student is already registered; revoke their access first to invite someone new"}
        code = make_invite()
        accounts.update("owner", invite=code)
        return 200, {"ok": True, "invite": code}

    @app.post("/api/student/revoke")
    def _revoke(body):
        """Remove the student's account; their open sessions end on their next request."""
        st = accounts.public("student")
        if not st:
            return 404, {"error": "no student is registered"}
        if str(body.get("confirm", "")).strip().lower() != st["name"].strip().lower():
            return 400, {"error": "type the student's name to confirm"}
        accounts.remove("student")
        code = make_invite()
        accounts.update("owner", invite=code)
        return 200, {"ok": True, "invite": code}

    @app.post("/api/policy")
    def _policy(body):
        """New spending limits, written on-chain with setPolicy."""
        if (e := need_owner()):
            return e
        try:
            per, roll = to_units(body.get("per_transfer_cap")), to_units(body.get("rolling_cap"))
        except AmountError as err:
            return 400, {"error": f"limits: {err}"}
        if per > roll:
            return 400, {"error": "the per-transfer cap cannot be larger than the 24-hour cap"}
        if roll > MAX_LIMIT:
            return 400, {"error": "keep the limits under 1,000,000 tUSDC"}
        s = chain.wallet_state()
        if (per, roll) == (s["per_transfer_cap"], s["rolling_cap"]):
            return 400, {"error": "those are already the limits"}
        try:
            rc = chain.set_policy(owner, per, roll)
        except ChainError as err:
            return 502, {"error": f"chain error: {err}"}
        log.add("policy", f"Limits changed to {fmt(per)} per payment and {fmt(roll)} per 24 h", rc.tx_hash, chain.name)
        ledger_cache.clear()
        cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash)}

    @app.post("/api/topup")
    def _topup(body):
        """Add test money to the wallet (tUSDC has a public mint; it has no value)."""
        if (e := need_owner()):
            return e
        try:
            units = to_units(body.get("amount") or "1000")
        except AmountError as err:
            return 400, {"error": str(err)}
        if units > MAX_TOPUP:
            return 400, {"error": "add at most 100,000 tUSDC at a time"}
        try:
            rc = chain.mint(owner, chain.deployment["wallet"], units)
        except ChainError as err:
            return 502, {"error": f"chain error: {err}"}
        log.add("deposit", f"Added {fmt(units)} of test money to the wallet", rc.tx_hash, chain.name)
        cache.clear()
        ledger_cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash)}

    ledger_cache: dict = {}

    @app.get("/api/ledger")
    def _ledger(q):
        hit = ledger_cache.get("v")
        if hit and time.time() - hit[0] < 30 and not q.get("fresh"):
            return 200, hit[1]
        try:
            val = wallet_ledger(chain, contacts)
        except Exception as err:
            return 200, {"entries": [], "stats": None, "error": str(err), "chain": chain.name}
        ledger_cache["v"] = (time.time(), val)
        return 200, val

    @app.post("/api/contacts")
    def _add_contact(body):
        """Register a contact for the student; with allowlist on, the contract learns it in the same step."""
        if (e := need_owner()):
            return e
        d = chain.deployment
        addr = str(body.get("address") or "").strip()
        if addr and addr.lower() in {d["wallet"].lower(), d["token"].lower(), d["owner"].lower(), d["agent"].lower()}:
            return 400, {"error": "that is one of Shouhu's own addresses, not a contact"}
        try:
            c = contacts_mod.register(contacts, body.get("name"), body.get("alias"), addr, path=registered_path)
        except ValueError as err:
            return 400, {"error": str(err)}
        contacts.append(c)
        out = {"ok": True, "contact": {"name": c.name, "address": c.address, "aliases": list(c.aliases)}, "tx": None}
        if body.get("allowlist", True):
            try:
                rc = chain.set_allowlist(owner, c.address, True)
            except ChainError as err:
                return 502, {**out, "error": f"saved, but the allowlist transaction failed: {err}"}
            log.add("contact", f"Registered contact {c.name} and added it to the allowlist", rc.tx_hash, chain.name)
            ledger_cache.clear()
            out.update(tx=rc.tx_hash, explorer=chain.explorer_tx(rc.tx_hash))
        cache.clear()
        return 200, out

    @app.post("/api/allowlist")
    def _allowlist(body):
        if (e := need_owner()):
            return e
        c = next((x for x in contacts if x.address.lower() == str(body.get("address", "")).lower()), None)
        if not c:
            return 404, {"error": "only a registered contact can be put on the allowlist here"}
        allowed = bool(body.get("allowed"))
        try:
            rc = chain.set_allowlist(owner, c.address, allowed)
        except ChainError as err:
            return 502, {"error": f"chain error: {err}"}
        log.add("allowlist", f"{c.name} {'added to' if allowed else 'removed from'} the allowlist", rc.tx_hash, chain.name)
        ledger_cache.clear()
        cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash)}

    @app.get("/api/proof")
    def _proof(q):
        return 200, verify_tx(chain, q.get("tx", ""), contacts, reqs, audit_path, log.list())

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-owner-web", description="Owner console in the browser (owner key, separate process)")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--rpc", default=None, help="RPC endpoint to use (shouhu-web passes its own)")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--parent-pid", type=int, default=None, help="exit when this process (shouhu-web) is gone")
    ap.add_argument("--student-url", default=None, help="the student app's address, for the invite link")
    a = ap.parse_args(argv)
    if a.parent_pid:
        def watch():                     # never outlive the app that started us, however it was stopped
            while os.getppid() == a.parent_pid:
                time.sleep(2)
            os._exit(0)
        threading.Thread(target=watch, daemon=True).start()
    chain = Chain(a.chain, rpc_url=a.rpc)
    key = config.owner_key()
    owner = account_from(key) if key else None
    httpd = serve(build_app(chain, owner, student_url=a.student_url), a.port, open_browser=not a.no_browser)
    if not a.no_browser:  # when shouhu-web starts it, shouhu-web prints the address
        print(f"owner console  http://127.0.0.1:{a.port}/  on {a.chain}{'' if owner else '  (read-only: no owner key)'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
