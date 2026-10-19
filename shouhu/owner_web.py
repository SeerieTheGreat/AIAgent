"""Owner console in the browser. Its own process with the owner key; the student's app never sees the key.

Same powers as the shouhu-owner command for the demo path: read status, approve one request exactly as filed,
deny it, pause or unpause the wallet."""
from __future__ import annotations

import argparse
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import config, contacts as contacts_mod
from .chain import Chain, ChainError, account_from
from .money import fmt
from .requests_store import Requests
from .webapp import wallet_state_parallel
from .webserver import App, serve


def build_app(chain: Chain, owner, requests: Requests | None = None, contacts=None) -> App:
    app = App("owner.html", "Shouhu owner console")
    contacts = contacts if contacts is not None else contacts_mod.load()
    reqs = requests or Requests()
    app.page_vars = {"chain": chain.name, "read_only": owner is None}

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
            "contacts": [{"name": c.name, "address": c.address, "allowlisted": ok} for c, ok in zip(contacts, reads["allowed"])],
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
        cache.clear()
        return 200, {"ok": True, "tx": rc.tx_hash, "explorer": chain.explorer_tx(rc.tx_hash)}

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-owner-web", description="Owner console in the browser (owner key, separate process)")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--port", type=int, default=8788)
    ap.add_argument("--rpc", default=None, help="RPC endpoint to use (shouhu-web passes its own)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    chain = Chain(a.chain, rpc_url=a.rpc)
    key = config.owner_key()
    owner = account_from(key) if key else None
    httpd = serve(build_app(chain, owner), a.port, open_browser=not a.no_browser)
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
