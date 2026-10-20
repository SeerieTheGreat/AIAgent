"""Terminal chat with Shouhu. The agent process holds only the agent key."""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from rich.console import Console
from rich.panel import Panel

from . import config, contacts as contacts_mod
from .agent import ModelClient, ShouhuAgent
from .audit import Audit
from .chain import Chain, account_from
from .money import fmt
from .requests_store import Requests
from .rules import RulesModel
from .tools import ToolContext, get_portfolio

console = Console()


def ensure_api_key() -> None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    console.print("[yellow]No Anthropic API key found. Paste it now; it is stored only in .env on this Mac.[/yellow]")
    key = getpass.getpass("ANTHROPIC_API_KEY: ").strip()
    if not key:
        sys.exit("an API key is required to talk to the model")
    lines = config.ENV_PATH.read_text().splitlines() if config.ENV_PATH.exists() else []
    lines = [l for l in lines if not l.startswith("ANTHROPIC_API_KEY=")]
    lines.append(f"ANTHROPIC_API_KEY={key}")
    config.ENV_PATH.write_text("\n".join(lines) + "\n")
    os.environ["ANTHROPIC_API_KEY"] = key


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-chat")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--model", default=config.MODEL)
    ap.add_argument("--effort", default=config.EFFORT)
    ap.add_argument("--verbose", action="store_true", help="show tool calls")
    ap.add_argument("--rules", action="store_true", help="rules only: no model and no API key; the same tools and checks decide")
    a = ap.parse_args(argv)
    if not a.rules:
        ensure_api_key()
    chain = Chain(a.chain)
    if not chain.deployment:
        sys.exit(f"no deployment for {a.chain}; run: uv run shouhu-deploy --chain {a.chain}")
    ctx = ToolContext(chain=chain, contacts=contacts_mod.load(), audit=Audit(), requests=Requests(),
                      agent_account=account_from(config.agent_key()))
    agent = ShouhuAgent(RulesModel(ctx) if a.rules else ModelClient(a.model, a.effort), ctx)
    if a.verbose:
        agent.on_tool = lambda name, args, res: console.print(f"[dim]  tool {name}({args}) -> {res[:160]}[/dim]")
    s = chain.wallet_state()
    console.print(Panel(f"Shouhu 守护 on [bold]{a.chain}[/bold]\nwallet {s['wallet']}\nbalance {fmt(s['balance'])}   per-transfer cap {fmt(s['per_transfer_cap'])}   24h cap {fmt(s['rolling_cap'])}\n"
                        f"assistant: {'rules only (no model)' if a.rules else 'AI model'}   commands: /portfolio /requests /quit", title="guarded agent wallet"))
    while True:
        try:
            text = console.input("[bold cyan]you>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/quit", "/exit"):
            break
        if text == "/portfolio":
            console.print(get_portfolio(ctx))
            continue
        if text == "/requests":
            for r in ctx.requests.list():
                console.print(f"{r['id']} {r['status']} {fmt(r['amount'])} -> {r['name'] or r['to']}")
            continue
        with console.status("thinking..."):
            try:
                reply = agent.chat(text)
            except Exception as e:  # keep the session alive, show the error
                reply = f"(error: {type(e).__name__}: {e})"
        console.print(f"[bold green]shouhu>[/bold green] {reply}")


if __name__ == "__main__":
    main()
