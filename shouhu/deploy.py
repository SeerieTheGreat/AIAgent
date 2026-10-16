"""Deploy the contracts, fund the wallet with test money, allowlist the contacts, fund the agent's gas."""
from __future__ import annotations

import argparse
import sys

from . import config, contacts as contacts_mod
from .chain import Chain, ChainError, account_from
from .keys import ensure_keys
from .money import fmt

FAUCETS = ("https://cloud.google.com/application/web3/faucet/ethereum/sepolia",
           "https://faucets.chain.link/sepolia")


def deploy(chain_name: str, fund_agent_eth: float, mint_units: int, per_cap: int, rolling: int, quiet: bool = False) -> dict:
    ensure_keys()
    owner = account_from(config.owner_key())
    agent = account_from(config.agent_key())
    chain = Chain(chain_name)
    say = (lambda *a: None) if quiet else print
    if chain_name == "anvil":
        chain.anvil_set_balance(owner.address, 10 ** 21)
        chain.anvil_set_balance(agent.address, 10 ** 20)
    owner_eth = chain.eth_balance(owner.address)
    say(f"chain {chain_name} via {chain.rpc_url}; owner {owner.address} has {owner_eth / 1e18:.4f} ETH")
    if owner_eth < int(0.01 * 1e18):
        raise ChainError(f"owner address {owner.address} needs test ether first. Faucets: {', '.join(FAUCETS)}")
    dep = chain.deploy(owner, agent.address, per_cap, rolling)
    say(f"TestUSDC    {dep['token']}  tx {dep['token_tx']}")
    say(f"PolicyWallet {dep['wallet']}  tx {dep['wallet_tx']}")
    r = chain.mint(owner, dep["wallet"], mint_units)
    say(f"minted {fmt(mint_units)} to the wallet  tx {r.tx_hash}")
    for c in contacts_mod.load():
        r = chain.set_allowlist(owner, c.address, True)
        say(f"allowlisted {c.name:18s} {c.address}  tx {r.tx_hash}")
    want = int(fund_agent_eth * 1e18)
    if chain.eth_balance(agent.address) < want:
        r = chain.send_eth(owner, agent.address, want)
        say(f"funded agent {agent.address} with {fund_agent_eth} ETH for gas  tx {r.tx_hash}")
    if chain.explorer_address(dep["wallet"]):
        say(f"explorer: {chain.explorer_address(dep['wallet'])}")
    say(f"saved deployments/{chain_name}.json")
    return dep


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deploy the Shouhu contracts to a chain")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("--fund-agent-eth", type=float, default=None, help="ETH to send to the agent key for gas")
    ap.add_argument("--mint", type=float, default=config.INITIAL_WALLET_FUNDING / config.UNIT, help="tUSDC to mint into the wallet")
    ap.add_argument("--per-transfer-cap", type=float, default=config.DEFAULT_PER_TRANSFER_CAP / config.UNIT)
    ap.add_argument("--rolling-cap", type=float, default=config.DEFAULT_ROLLING_CAP / config.UNIT)
    a = ap.parse_args(argv)
    fund = a.fund_agent_eth if a.fund_agent_eth is not None else (1.0 if a.chain == "anvil" else 0.01)
    try:
        deploy(a.chain, fund, int(a.mint * config.UNIT), int(a.per_transfer_cap * config.UNIT), int(a.rolling_cap * config.UNIT))
    except ChainError as e:
        print(f"deploy failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
