"""Demo helper: ask the contract directly (dry-run, no gas spent) whether the agent key could make a payment.

Shows the on-chain enforcement independently of the model and the policy engine.
"""
from __future__ import annotations

import argparse

from . import config, contacts as contacts_mod
from .chain import Chain
from .money import fmt, to_units
from .owner import _resolve


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shouhu-try", description="Dry-run an agent payment against the contract")
    ap.add_argument("--chain", default=config.CHAIN, choices=list(config.CHAINS))
    ap.add_argument("who", help="contact name or 0x address")
    ap.add_argument("amount", help="amount in tUSDC")
    a = ap.parse_args(argv)
    chain = Chain(a.chain)
    contacts = contacts_mod.load()
    agent = chain.wallet.functions.agent().call()     # a dry run needs no signature, so no key: anyone can ask
    to = _resolve(contacts, a.who)
    units = to_units(a.amount)
    fn = chain.wallet.functions.agentTransfer(to, units, b"\x00" * 32)
    print(f"asking PolicyWallet {chain.wallet.address} on {a.chain}: may the agent key send {fmt(units)} to {to}?")
    try:
        fn.call({"from": agent})
        print("contract answer: ALLOWED (within caps and allowlist). Nothing was sent; this was a dry run.")
    except Exception as e:  # ContractCustomError or ContractLogicError
        print(f"contract answer: REJECTED with {chain.decode_error(e)}")
        print("The model never had a say in this; the limits live on-chain and only the owner key can change them.")


if __name__ == "__main__":
    main()
