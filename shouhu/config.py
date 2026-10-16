"""Settings. Secrets come from .env; nothing here is ever shown to the model."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"            # agent-side settings: agent key, API key, chain
OWNER_ENV_PATH = ROOT / ".owner.env"  # owner key only; read by the owner and deploy commands, never by the agent process
load_dotenv(ENV_PATH)

ARTIFACTS = ROOT / "shouhu" / "artifacts"
DEPLOYMENTS = ROOT / "deployments"
EVIDENCE_DIR = ROOT / "evidence"
DATA_DIR = ROOT / "data"
CONTACTS_PATH = ROOT / "contacts.json"
REQUESTS_PATH = DATA_DIR / "requests.json"
AUDIT_PATH = EVIDENCE_DIR / "audit_log.jsonl"

TOKEN_SYMBOL = "tUSDC"
TOKEN_DECIMALS = 6
UNIT = 10 ** TOKEN_DECIMALS


def _rpcs(*urls: str | None) -> list[str]:
    return [u for u in urls if u]


CHAINS = {
    "anvil": {
        "chain_id": 31337,
        "rpcs": _rpcs(os.environ.get("ANVIL_RPC_URL"), "http://127.0.0.1:8545"),
        "explorer_tx": None,
        "explorer_address": None,
    },
    "sepolia": {
        "chain_id": 11155111,
        "rpcs": _rpcs(os.environ.get("SEPOLIA_RPC_URL"), "https://ethereum-sepolia-rpc.publicnode.com",
                      "https://sepolia.drpc.org", "https://1rpc.io/sepolia", "https://rpc.sepolia.org"),
        "explorer_tx": "https://sepolia.etherscan.io/tx/{}",
        "explorer_address": "https://sepolia.etherscan.io/address/{}",
    },
    "base-sepolia": {
        "chain_id": 84532,
        "rpcs": _rpcs(os.environ.get("BASE_SEPOLIA_RPC_URL"), "https://sepolia.base.org",
                      "https://base-sepolia-rpc.publicnode.com"),
        "explorer_tx": "https://sepolia.basescan.org/tx/{}",
        "explorer_address": "https://sepolia.basescan.org/address/{}",
    },
}

CHAIN = os.environ.get("SHOUHU_CHAIN", "anvil")
MODEL = os.environ.get("SHOUHU_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("SHOUHU_EFFORT", "medium")
MAX_TOKENS = int(os.environ.get("SHOUHU_MAX_TOKENS", "4000"))
MAX_TOOL_ROUNDS = 8

# Default on-chain policy, in token base units.
DEFAULT_PER_TRANSFER_CAP = 500 * UNIT
DEFAULT_ROLLING_CAP = 1000 * UNIT
INITIAL_WALLET_FUNDING = 10_000 * UNIT


def owner_key() -> str | None:
    """Read the owner key from its own file without exporting it to the environment."""
    from dotenv import dotenv_values
    if OWNER_ENV_PATH.exists():
        return dotenv_values(OWNER_ENV_PATH).get("OWNER_PRIVATE_KEY") or None
    return os.environ.get("OWNER_PRIVATE_KEY")


def agent_key() -> str | None:
    return os.environ.get("AGENT_PRIVATE_KEY")
