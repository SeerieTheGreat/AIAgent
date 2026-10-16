"""Export the evidence bundle: deployment, payments with explorer links, audit log, requests, transcripts."""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from . import config, contacts as contacts_mod
from .chain import Chain
from .money import fmt


def export(chain_name: str, extra_files: list[Path] | None = None, label: str = "") -> Path:
    chain = Chain(chain_name)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = config.EVIDENCE_DIR / "runs" / f"{chain_name}-{stamp}{('-' + label) if label else ''}"
    out.mkdir(parents=True, exist_ok=True)
    contacts = contacts_mod.load()
    names = {c.address.lower(): c.name for c in contacts}
    payments = chain.payments(limit=200)
    for p in payments:
        p["to_name"] = names.get(p["to"].lower())
        p["amount_fmt"] = fmt(p["amount"])
        p["explorer"] = chain.explorer_tx(p["tx_hash"])
    (out / "payments.json").write_text(json.dumps(payments, indent=1))
    (out / "deployment.json").write_text(json.dumps(chain.deployment, indent=1))
    for src in (config.AUDIT_PATH, config.REQUESTS_PATH, config.CONTACTS_PATH):
        if src.exists():
            shutil.copy(src, out / src.name)
    for f in extra_files or []:
        if f and Path(f).exists():
            shutil.copy(f, out / Path(f).name)
    s = chain.wallet_state()
    lines = [f"# Shouhu evidence bundle ({chain_name})", "",
             f"- PolicyWallet: `{chain.deployment['wallet']}`" + (f" ({chain.explorer_address(chain.deployment['wallet'])})" if chain.explorer_address(chain.deployment['wallet']) else ""),
             f"- TestUSDC: `{chain.deployment['token']}`", f"- Owner: `{chain.deployment['owner']}`  Agent: `{chain.deployment['agent']}`",
             f"- Policy now: per-transfer cap {fmt(s['per_transfer_cap'])}, 24h cap {fmt(s['rolling_cap'])}, paused {s['paused']}",
             f"- Wallet balance now: {fmt(s['balance'])}", "", "## Payments (newest first)", "",
             "| block | to | amount | via owner approval | intent id | tx |", "|---|---|---|---|---|---|"]
    for p in payments:
        tx = f"[{p['tx_hash'][:12]}...]({p['explorer']})" if p["explorer"] else p["tx_hash"]
        lines.append(f"| {p['block']} | {p['to_name'] or p['to']} | {p['amount_fmt']} | {p['via_approval']} | {p['intent_id'][:12]}... | {tx} |")
    lines += ["", "Every intent id above is the hash of an entry in `audit_log.jsonl` (event `decision`), which records the user's request, the policy decision and its reasons."]
    (out / "README.md").write_text("\n".join(lines) + "\n")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-evidence")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--label", default="")
    a = ap.parse_args(argv)
    print(export(a.chain, label=a.label))


if __name__ == "__main__":
    main()
