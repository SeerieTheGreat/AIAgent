"""Judge mode and demo runner: run the scripted tasks on a local chain (or Sepolia) and write the transcript."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import config, contacts as contacts_mod
from .agent import ModelClient, ShouhuAgent
from .audit import Audit
from .chain import Chain, account_from
from .deploy import deploy
from .evidence import export
from .localchain import Anvil
from .money import fmt
from .requests_store import Requests
from .scenarios import scripted_tasks
from .tools import ToolContext, get_portfolio, transfer


def owner_approve(req_id: str, chain_name: str) -> str:
    """Run the owner command in a separate process, exactly as the parent would."""
    cmd = [sys.executable, "-m", "shouhu.owner", "--chain", chain_name, "approve", req_id, "--yes"]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=config.ROOT)
    return (out.stdout + out.stderr).strip()


def run_tasks(chain_name: str, offline: bool, model: str, effort: str, verbose: bool) -> Path:
    if chain_name == "anvil":
        config.set_data_dir(config.ROOT / "data" / "anvil")   # the live chain's requests in data/ stay untouched
    chain = Chain(chain_name)
    # a fresh local chain allowlists only the default contacts, not ones registered for another chain
    contacts = contacts_mod.default_contacts() if chain_name == "anvil" else contacts_mod.load()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    reqs = Requests()
    reqs.clear()
    audit = Audit(session=f"demo-{stamp}")
    ctx = ToolContext(chain=chain, contacts=contacts, audit=audit, requests=reqs, agent_account=account_from(config.agent_key()))
    lines = [f"# Shouhu scripted tasks on {chain_name} ({stamp})", ""]
    tasks = scripted_tasks(contacts)
    agent = None
    if not offline:
        agent = ShouhuAgent(ModelClient(model, effort), ctx)
        if verbose:
            agent.on_tool = lambda name, args, res: print(f"    tool {name}({json.dumps(args, ensure_ascii=False)}) -> {res[:200]}")

    def say(s=""):
        print(s)
        lines.append(s)

    for t in tasks:
        say(f"## Task {t['n']}: {t['criterion']}")
        say(f"**user:** {t['user']}")
        if offline:
            # tool-level run: shows the policy engine and the chain without a model
            ctx.user_message = t["user"]; ctx.risk = []
            if t["expect"] == "portfolio":
                say("**tools:** get_portfolio -> " + json.dumps(get_portfolio(ctx), ensure_ascii=False)[:600])
            elif t["n"] in (2, 8):
                who, amt = ("mama", "20") if t["n"] == 2 else ("哥", "10")
                say("**tools:** transfer -> " + json.dumps(transfer(ctx, who, amt, None, None), ensure_ascii=False))
            elif t["n"] == 3:
                say("**tools:** transfer -> " + json.dumps(transfer(ctx, "landlord", "800", "deposit", None), ensure_ascii=False))
            elif t["n"] == 4:
                say("**tools:** transfer -> " + json.dumps(transfer(ctx, t["user"].split()[4], "50", None, None), ensure_ascii=False))
            elif t["n"] == 5:
                say("**tools:** transfer -> " + json.dumps(transfer(ctx, t["user"].split()[4].rstrip(","), "15", None, None), ensure_ascii=False))
            else:
                say("**tools:** (no tool is available for this request; the agent explains)")
        else:
            reply = agent.chat(t["user"])
            say(f"**shouhu:** {reply}")
        if t.get("then_owner_approves"):
            pending = reqs.list("pending")
            if pending:
                rid = pending[0]["id"]
                say(f"**owner (separate process):** `shouhu-owner approve {rid}`")
                say("```\n" + owner_approve(rid, chain_name) + "\n```")
                if offline:
                    say("**tools:** transfer(request_id) -> " + json.dumps(transfer(ctx, "landlord", "800", None, rid), ensure_ascii=False))
                else:
                    say(f"**user:** {t['follow_up'].replace('R1', rid)}")
                    say(f"**shouhu:** {agent.chat(t['follow_up'].replace('R1', rid))}")
        say()
    s = chain.wallet_state()
    say(f"Final wallet balance: {fmt(s['balance'])}; spent in last 24h (routine cap): {fmt(s['spent_24h'])}")
    out_dir = config.EVIDENCE_DIR / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    transcript = out_dir / f"transcript-{chain_name}-{stamp}.md"
    transcript.write_text("\n".join(lines) + "\n")
    bundle = export(chain_name, extra_files=[transcript], label="tasks")
    print(f"\nevidence bundle: {bundle}")
    return bundle


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-demo", description="Judge mode: reproduce the scripted tasks")
    ap.add_argument("--chain", default="anvil", choices=list(config.CHAINS))
    ap.add_argument("--offline", action="store_true", help="no model: exercise the policy engine and chain directly")
    ap.add_argument("--no-deploy", action="store_true", help="reuse the existing deployment")
    ap.add_argument("--model", default=config.MODEL)
    ap.add_argument("--effort", default=config.EFFORT)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.chain == "anvil":
        with Anvil(port=8545):
            deploy("anvil", 1.0, config.INITIAL_WALLET_FUNDING, config.DEFAULT_PER_TRANSFER_CAP, config.DEFAULT_ROLLING_CAP, quiet=not a.verbose)
            run_tasks("anvil", a.offline, a.model, a.effort, a.verbose)
    else:
        if not a.no_deploy:
            deploy(a.chain, 0.01, config.INITIAL_WALLET_FUNDING, config.DEFAULT_PER_TRANSFER_CAP, config.DEFAULT_ROLLING_CAP)
        run_tasks(a.chain, a.offline, a.model, a.effort, a.verbose)


if __name__ == "__main__":
    main()
