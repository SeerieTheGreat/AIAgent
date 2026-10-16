"""Generate the owner and agent keys once and keep them in .env (testnet only, never shown to the model)."""
from __future__ import annotations

from eth_account import Account

from . import config


def ensure_keys() -> dict:
    env = config.ENV_PATH
    lines = env.read_text().splitlines() if env.exists() else []
    have = {l.split("=", 1)[0] for l in lines if "=" in l and not l.startswith("#")}
    added = []
    if not config.OWNER_ENV_PATH.exists() or "OWNER_PRIVATE_KEY" not in config.OWNER_ENV_PATH.read_text():
        acct = Account.create()
        config.OWNER_ENV_PATH.write_text(f"# Owner key. Only shouhu-owner and shouhu-deploy read this file.\nOWNER_PRIVATE_KEY={acct.key.hex()}\n")
        added.append("owner")
    if "AGENT_PRIVATE_KEY" not in have:
        acct = Account.create()
        lines.append(f"AGENT_PRIVATE_KEY={acct.key.hex()}")
        added.append("agent")
    if "ANTHROPIC_API_KEY" not in have:
        lines.append("# Paste your Anthropic API key after the = sign (no quotes). It stays on this Mac.")
        lines.append("ANTHROPIC_API_KEY=")
    if "SHOUHU_CHAIN" not in have:
        lines.append("SHOUHU_CHAIN=anvil")
    env.write_text("\n".join(lines) + "\n")
    # reload so this process sees the values
    from dotenv import load_dotenv
    load_dotenv(env, override=True)
    owner = Account.from_key(config.owner_key()).address
    agent = Account.from_key(config.agent_key()).address
    (config.ROOT / "ADDRESSES.md").write_text(
        "# Shouhu wallet addresses (testnet only)\n\n"
        f"- Owner address (send faucet test ether here): `{owner}`\n"
        f"- Agent address (the AI's own key): `{agent}`\n\n"
        "Private keys live only in `.env` on this machine and are never shown to the model.\n")
    return {"owner": owner, "agent": agent, "added": added}


if __name__ == "__main__":
    print(ensure_keys())
