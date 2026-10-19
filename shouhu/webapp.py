"""Browser interface for the student's chat with Shouhu. The process holds only the agent key.

The owner console (approvals, pause) is a different process started next to it, see owner_web.py."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext

from . import config, contacts as contacts_mod
from .agent import ModelClient, ShouhuAgent
from .audit import Audit
from .chain import Chain, ChainError, account_from
from .localchain import Anvil
from .money import fmt
from .requests_store import Requests
from .scenarios import scripted_tasks
from .tools import ToolContext
from .webserver import App, serve

# Sepolia endpoints that still serve old logs (publicnode prunes after ~20,000 blocks); used for history only.
SEPOLIA_HISTORY_RPCS = ("https://0xrpc.io/sep", "https://gateway.tenderly.co/public/sepolia",
                        "https://eth-sepolia.api.onfinality.io/public")


class WebChain(Chain):
    """Default endpoints for reads and sends; payment history falls back to endpoints that keep old logs."""

    def payments(self, limit: int = 50) -> list[dict]:
        try:
            return super().payments(limit)
        except Exception as first:
            if self.name != "sepolia":
                raise ChainError(f"payment history unavailable: {first}") from first
            for url in SEPOLIA_HISTORY_RPCS:
                try:
                    return Chain(self.name, deployment=self.deployment, rpc_url=url).payments(limit)
                except Exception:
                    continue
            raise ChainError(f"payment history unavailable on every endpoint: {first}") from first


class Session:
    """One conversation at a time, like the terminal chat; the lock serializes turns."""

    def __init__(self, chain: Chain, model: str, effort: str, offline_reason: str | None, *, model_client=None,
                 contacts=None, requests: Requests | None = None, agent_account=None, audit_path=None):
        self.chain = chain
        self.model, self.effort = model, effort
        self.offline_reason = offline_reason
        self.model_client = model_client
        self.contacts = contacts if contacts is not None else contacts_mod.load()
        self.requests = requests or Requests()
        self.agent_account = agent_account or account_from(config.agent_key())
        self.audit_path = audit_path
        self.lock = threading.Lock()
        self.progress: list = []          # tool calls of the turn in flight
        self.busy = False
        self._cache: dict = {}
        self._cache_locks: dict = {}
        self._pool = ThreadPoolExecutor(max_workers=8)
        self.new()

    def new(self):
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.audit = Audit(self.audit_path, session=f"web-{stamp}")
        self.ctx = ToolContext(chain=self.chain, contacts=self.contacts, audit=self.audit, requests=self.requests,
                               agent_account=self.agent_account)
        self.agent = None if self.offline_reason else ShouhuAgent(self.model_client or ModelClient(self.model, self.effort), self.ctx)
        if self.agent:
            self.agent.on_tool = lambda name, args, res: self.progress.append(_card(name, args, res, self.chain))
        self.log: list = []

    # --------------------------------------------------------------- reads, cached so polling stays cheap
    def _cached(self, key: str, ttl: float, fn):
        with self._cache_locks.setdefault(key, threading.Lock()):   # concurrent polls share one read
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
            val = fn()
            self._cache[key] = (time.time(), val)
            return val

    def invalidate(self):
        self._cache.clear()

    def state(self) -> dict:
        def read():
            # public endpoints answer one call at a time slowly; issue the independent reads together
            allowed = [self._pool.submit(self.chain.is_allowlisted, c.address) for c in self.contacts]
            gas = self._pool.submit(lambda: self.chain.eth_balance(self.chain.deployment["agent"]))
            s = wallet_state_parallel(self.chain, self._pool)
            contacts = [{"name": c.name, "alias": next((a for a in c.aliases if not a.isascii()), ""), "address": c.address,
                         "allowlisted": f.result(), "explorer": self.chain.explorer_address(c.address)}
                        for c, f in zip(self.contacts, allowed)]
            return {
                "chain": self.chain.name, "rpc": self.chain.rpc_url, "tx_explorer": self.chain.cfg["explorer_tx"],
                "wallet": s["wallet"], "wallet_explorer": self.chain.explorer_address(s["wallet"]),
                "token": s["token"], "balance": fmt(s["balance"]), "balance_units": s["balance"],
                "per_transfer_cap": fmt(s["per_transfer_cap"]), "rolling_cap": fmt(s["rolling_cap"]),
                "rolling_cap_units": s["rolling_cap"], "spent_24h": fmt(s["spent_24h"]), "spent_24h_units": s["spent_24h"],
                "headroom": fmt(s["headroom"]), "paused": s["paused"],
                "owner": s["owner"], "agent": s["agent"], "agent_explorer": self.chain.explorer_address(s["agent"]),
                "agent_gas_eth": round(gas.result() / 1e18, 5),
                "contacts": contacts,
            }
        out = dict(self._cached("state", 6, read))
        out["requests"] = [{**r, "amount": fmt(r["amount"]),
                            "approve_explorer": self.chain.explorer_tx(r["approve_tx"]) if r.get("approve_tx") else None,
                            "exec_explorer": self.chain.explorer_tx(r["exec_tx"]) if r.get("exec_tx") else None}
                           for r in reversed(self.requests.list())]
        return out

    def history(self) -> list:
        return self._cached("history", 45, lambda: named_payments(self.chain, self.contacts))

    # --------------------------------------------------------------- chat
    def chat(self, text: str) -> dict:
        if self.offline_reason:
            return {"error": self.offline_reason}
        if not self.lock.acquire(blocking=False):
            return {"error": "Shouhu is still answering the previous message."}
        try:
            self.busy, self.progress = True, []
            started = time.time()
            try:
                reply = self.agent.chat(text)
                err = None
            except Exception as e:      # keep the session alive and show the error, as the terminal chat does
                reply, err = "", f"{type(e).__name__}: {e}"
            entry = {"user": text, "reply": reply, "error": err, "cards": list(self.progress),
                     "seconds": round(time.time() - started, 1), "ts": time.time()}
            self.log.append(entry)
            if any(c["kind"] in ("paid", "request") for c in self.progress):
                self.invalidate()
            return entry
        finally:
            self.busy = False
            self.lock.release()


def wallet_state_parallel(chain: Chain, pool: ThreadPoolExecutor) -> dict:
    """Same fields as Chain.wallet_state, read concurrently."""
    w, t = chain.wallet, chain.token
    calls = {"balance": t.functions.balanceOf(w.address), "per_transfer_cap": w.functions.perTransferCap(),
             "rolling_cap": w.functions.rollingCap(), "spent_24h": w.functions.spentLast24h(),
             "headroom": w.functions.agentHeadroom(), "paused": w.functions.paused(),
             "owner": w.functions.owner(), "agent": w.functions.agent()}
    futures = {k: pool.submit(fn.call) for k, fn in calls.items()}
    return {"wallet": w.address, "token": t.address, **{k: f.result() for k, f in futures.items()}}


def named_payments(chain: Chain, contacts) -> list:
    names = {c.address.lower(): c.name for c in contacts}
    return [{**p, "name": names.get(p["to"].lower()), "amount": fmt(p["amount"]), "explorer": chain.explorer_tx(p["tx_hash"])}
            for p in chain.payments(limit=25)]


def _card(name: str, args: dict, result_text: str, chain: Chain) -> dict:
    """Turn one tool call into a receipt card. Built from the tool result, never from the model's wording."""
    try:
        r = json.loads(result_text)
    except ValueError:
        r = {}
    card = {"tool": name, "args": args, "result": r}
    status = r.get("status")
    if name == "transfer" or name == "request_owner_approval":
        if status == "executed":
            card.update(kind="paid", title=f"Paid {r.get('amount')} to {r.get('to')}",
                        tier=2 if r.get("via_owner_approval") else 1, tx=r.get("tx_hash"), explorer=r.get("explorer"),
                        intent=r.get("intent_id"), lines=r.get("reasons") or [])
        elif status == "needs_owner_approval":
            card.update(kind="request", title=f"Request {r.get('request_id')}: {r.get('amount')} to {r.get('to')} needs the owner",
                        tier=2, request_id=r.get("request_id"), lines=r.get("reasons") or [])
        elif status == "rejected_by_contract":
            card.update(kind="refused", title="The smart contract rejected the transaction", tier=0, lines=[r.get("detail", "")])
        else:
            card.update(kind="refused", title="Refused by the policy engine; nothing was sent", tier=0,
                        lines=r.get("reasons") or [r.get("detail", "")])
        card["warnings"] = [w for w in (r.get("warnings") or []) if isinstance(w, str)]
    elif name == "check_recipient":
        warn = r.get("warnings") or []
        who = r.get("resolved_name") or r.get("address") or r.get("query")
        card.update(kind="warn" if warn else "read", title=f"Checked recipient: {who}",
                    lines=warn or [("allowlisted contact" if r.get("allowlisted") else r.get("note") or "")])
    elif name == "get_portfolio":
        card.update(kind="read", title=f"Read the wallet: {r.get('balance')}", lines=[])
    elif name == "get_history":
        card.update(kind="read", title=f"Read the payment history ({r.get('count', 0)} payments)", lines=[])
    else:
        card.update(kind="read", title=name, lines=[])
    return card


def build_app(session: Session, owner_port: int | None) -> App:
    app = App("index.html", "Shouhu")
    tasks = scripted_tasks(session.contacts)
    app.page_vars = {"owner_url": f"http://127.0.0.1:{owner_port}/" if owner_port else None,
                     "examples": [{"n": t["n"], "text": t["user"], "label": t["criterion"]} for t in tasks],
                     "offline": session.offline_reason}

    @app.get("/api/state")
    def _state(q):
        return 200, session.state()

    @app.get("/api/history")
    def _history(q):
        try:
            return 200, {"payments": session.history()}
        except Exception as e:
            return 200, {"payments": [], "error": str(e)}

    @app.get("/api/progress")
    def _progress(q):
        return 200, {"busy": session.busy, "cards": list(session.progress)}

    @app.get("/api/log")
    def _log(q):
        return 200, {"turns": session.log}

    @app.post("/api/chat")
    def _chat(body):
        text = str(body.get("text", "")).strip()[:2000]
        if not text:
            return 400, {"error": "empty message"}
        return 200, session.chat(text)

    @app.post("/api/new")
    def _new(body):
        if session.busy:
            return 409, {"error": "wait for the current reply"}
        session.new()
        return 200, {"ok": True}

    @app.post("/api/refresh")
    def _refresh(body):
        session.invalidate()
        return 200, {"ok": True}

    return app


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-web", description="Browser interface: the student's chat plus the owner console")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--owner-port", type=int, default=8788)
    ap.add_argument("--no-owner", action="store_true", help="do not start the owner console")
    ap.add_argument("--fresh", action="store_true", help="clear old approval requests first")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--model", default=config.MODEL)
    ap.add_argument("--effort", default=config.EFFORT)
    a = ap.parse_args(argv)

    if not config.agent_key():
        from .keys import ensure_keys
        ensure_keys()
    offline = None if os.environ.get("ANTHROPIC_API_KEY") else \
        "No model key: add ANTHROPIC_API_KEY to .env and restart shouhu-web. The wallet panels still work."

    def stop(*_):                         # a plain kill should also stop the local chain and the owner console
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)

    local = Anvil(port=8545) if a.chain == "anvil" else nullcontext()
    with local:
        if a.chain == "anvil":
            from .deploy import deploy
            print("starting a fresh local chain and deploying the contracts ...")
            deploy("anvil", 1.0, config.INITIAL_WALLET_FUNDING, config.DEFAULT_PER_TRANSFER_CAP, config.DEFAULT_ROLLING_CAP, quiet=True)
        chain = WebChain(a.chain)
        if not chain.deployment:
            sys.exit(f"no deployment for {a.chain}; run: uv run shouhu-deploy --chain {a.chain}")
        if a.fresh or a.chain == "anvil":
            Requests().clear()
        session = Session(chain, a.model, a.effort, offline)
        owner_proc = None
        if not a.no_owner:
            # a separate process: the owner key is read there and never enters this one
            owner_proc = subprocess.Popen([sys.executable, "-m", "shouhu.owner_web", "--chain", a.chain,
                                           "--port", str(a.owner_port), "--rpc", chain.rpc_url, "--no-browser"],
                                          cwd=config.ROOT)
        httpd = serve(build_app(session, None if a.no_owner else a.owner_port), a.port, open_browser=not a.no_browser)
        print(f"Shouhu 守护 on {a.chain} via {chain.rpc_url}")
        print(f"  student app    http://127.0.0.1:{a.port}/")
        if owner_proc:
            print(f"  owner console  http://127.0.0.1:{a.owner_port}/   (separate process, owner key)")
        if offline:
            print(f"  note: {offline}")
        print("press Ctrl+C to stop", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            httpd.server_close()
            if owner_proc:
                owner_proc.terminate()
                try:
                    owner_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    owner_proc.kill()


if __name__ == "__main__":
    main()
