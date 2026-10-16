"""Chain adapter: one serialized signer, dry-run before every send, decoded revert reasons."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from eth_abi import decode as abi_decode
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.exceptions import ContractCustomError, ContractLogicError, TimeExhausted

from . import config


class ChainError(RuntimeError):
    pass


def hx(h) -> str:
    """Hex string with a 0x prefix for hashes/bytes regardless of web3 version."""
    t = h.hex() if hasattr(h, "hex") else str(h)
    return t if t.startswith("0x") else "0x" + t


def load_artifact(name: str) -> dict:
    return json.loads((config.ARTIFACTS / f"{name}.json").read_text())


def deployment_path(chain: str) -> Path:
    return config.DEPLOYMENTS / f"{chain}.json"


def load_deployment(chain: str) -> dict | None:
    p = deployment_path(chain)
    return json.loads(p.read_text()) if p.exists() else None


def _error_decoder(abi: list) -> dict:
    table = {}
    for item in abi:
        if item.get("type") == "error":
            types = [i["type"] for i in item.get("inputs", [])]
            sig = f"{item['name']}({','.join(types)})"
            table[keccak(text=sig)[:4].hex()] = (item["name"], types, [i["name"] for i in item.get("inputs", [])])
    return table


@dataclass
class Receipt:
    tx_hash: str
    block: int
    gas_used: int
    status: int


class Chain:
    def __init__(self, name: str | None = None, deployment: dict | None = None, rpc_url: str | None = None):
        self.name = name or config.CHAIN
        self._rpc_override = rpc_url
        if self.name not in config.CHAINS:
            raise ChainError(f"unknown chain {self.name}")
        self.cfg = config.CHAINS[self.name]
        self.w3 = self._connect()
        self._lock = threading.Lock()
        self.token_abi = load_artifact("TestUSDC")["abi"]
        self.wallet_abi = load_artifact("PolicyWallet")["abi"]
        self._errors = _error_decoder(self.wallet_abi)
        self.deployment = deployment or load_deployment(self.name)
        self.token = self.wallet = None
        if self.deployment:
            self.token = self.w3.eth.contract(address=self.deployment["token"], abi=self.token_abi)
            self.wallet = self.w3.eth.contract(address=self.deployment["wallet"], abi=self.wallet_abi)

    # ------------------------------------------------------------------ connection
    def _connect(self) -> Web3:
        last = None
        for url in ([self._rpc_override] if self._rpc_override else self.cfg["rpcs"]):
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 20}))
                if w3.is_connected() and w3.eth.chain_id == self.cfg["chain_id"]:
                    self.rpc_url = url
                    return w3
            except Exception as e:  # try the next endpoint
                last = e
        raise ChainError(f"no working RPC for {self.name}: {last}")

    def explorer_tx(self, tx_hash: str) -> str | None:
        t = self.cfg["explorer_tx"]
        return t.format(tx_hash) if t else None

    def explorer_address(self, addr: str) -> str | None:
        t = self.cfg["explorer_address"]
        return t.format(addr) if t else None

    # ------------------------------------------------------------------ reads
    def eth_balance(self, addr: str) -> int:
        return self.w3.eth.get_balance(to_checksum_address(addr))

    def wallet_state(self) -> dict:
        w = self.wallet
        return {
            "wallet": w.address,
            "token": self.token.address,
            "balance": self.token.functions.balanceOf(w.address).call(),
            "per_transfer_cap": w.functions.perTransferCap().call(),
            "rolling_cap": w.functions.rollingCap().call(),
            "spent_24h": w.functions.spentLast24h().call(),
            "headroom": w.functions.agentHeadroom().call(),
            "paused": w.functions.paused().call(),
            "owner": w.functions.owner().call(),
            "agent": w.functions.agent().call(),
        }

    def is_allowlisted(self, addr: str) -> bool:
        return self.wallet.functions.allowlist(to_checksum_address(addr)).call()

    def approval(self, intent_id: bytes) -> dict:
        to, amount, used = self.wallet.functions.approvals(intent_id).call()
        return {"to": to, "amount": amount, "used": used}

    def token_balance(self, addr: str) -> int:
        return self.token.functions.balanceOf(to_checksum_address(addr)).call()

    def payments(self, limit: int = 50) -> list[dict]:
        """Payment events of our wallet, newest first, read in block chunks that public endpoints accept."""
        start = int(self.deployment.get("deploy_block", 0))
        latest = self.w3.eth.block_number
        out = []
        step = 4000
        frm = start
        while frm <= latest:
            to = min(frm + step - 1, latest)
            logs = self.wallet.events.Payment().get_logs(from_block=frm, to_block=to)
            for lg in logs:
                a = lg["args"]
                out.append({"intent_id": "0x" + bytes(a["intentId"]).hex(), "to": a["to"], "amount": int(a["amount"]),
                            "by": a["by"], "via_approval": bool(a["viaApproval"]), "tx_hash": hx(lg["transactionHash"]),
                            "block": lg["blockNumber"]})
            frm = to + 1
        out.sort(key=lambda x: x["block"], reverse=True)
        return out[:limit]

    # ------------------------------------------------------------------ writes
    def decode_error(self, exc: Exception) -> str:
        data = getattr(exc, "data", None)
        if isinstance(data, str) and data.startswith("0x") and len(data) >= 10:
            sel = data[2:10]
            if sel in self._errors:
                name, types, names = self._errors[sel]
                try:
                    args = abi_decode(types, bytes.fromhex(data[10:])) if types else ()
                except Exception:
                    args = ()
                pretty = ", ".join(f"{n}={v}" for n, v in zip(names, args))
                return f"{name}({pretty})"
            return f"custom error {data[:10]}"
        if isinstance(exc, ContractLogicError):
            return f"revert: {exc}"
        return f"{type(exc).__name__}: {exc}"

    def send(self, account, fn, *, value: int = 0, timeout: int = 150) -> Receipt:
        """Dry-run, sign with the given account, send, wait. One signer at a time."""
        with self._lock:
            try:
                fn.call({"from": account.address, "value": value})
            except (ContractCustomError, ContractLogicError) as e:
                raise ChainError(self.decode_error(e)) from e
            nonce = self.w3.eth.get_transaction_count(account.address, "pending")
            base = self.w3.eth.get_block("latest").get("baseFeePerGas", 0) or 0
            try:
                prio = max(int(self.w3.eth.max_priority_fee), 10**9)
            except Exception:
                prio = 2 * 10**9
            tx = fn.build_transaction({
                "from": account.address, "nonce": nonce, "chainId": self.cfg["chain_id"], "value": value,
                "maxPriorityFeePerGas": prio, "maxFeePerGas": base * 2 + prio,
            })
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.25)
            for attempt in range(2):
                signed = account.sign_transaction(tx)
                h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                try:
                    r = self.w3.eth.wait_for_transaction_receipt(h, timeout=timeout)
                    if r["status"] != 1:
                        raise ChainError(f"transaction {hx(h)} reverted on-chain")
                    return Receipt(hx(h), r["blockNumber"], r["gasUsed"], r["status"])
                except TimeExhausted:
                    # bump the fee and replace the same nonce once
                    tx["maxPriorityFeePerGas"] = int(tx["maxPriorityFeePerGas"] * 1.5)
                    tx["maxFeePerGas"] = int(tx["maxFeePerGas"] * 1.5)
            raise ChainError("transaction not confirmed after a fee bump; check the explorer before retrying")

    def send_eth(self, account, to: str, wei: int, timeout: int = 150) -> Receipt:
        with self._lock:
            nonce = self.w3.eth.get_transaction_count(account.address, "pending")
            base = self.w3.eth.get_block("latest").get("baseFeePerGas", 0) or 0
            prio = 10**9
            tx = {"from": account.address, "to": to_checksum_address(to), "value": wei, "nonce": nonce,
                  "chainId": self.cfg["chain_id"], "maxPriorityFeePerGas": prio, "maxFeePerGas": base * 2 + prio}
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.3)   # never hard-code 21000: intrinsic costs change
            signed = account.sign_transaction(tx)
            h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            r = self.w3.eth.wait_for_transaction_receipt(h, timeout=timeout)
            if r["status"] != 1:
                raise ChainError(f"ether transfer {hx(h)} failed on-chain (gas used {r['gasUsed']} of {tx['gas']})")
            return Receipt(hx(h), r["blockNumber"], r["gasUsed"], r["status"])

    # agent paths
    def agent_transfer(self, agent, to: str, amount: int, intent_id: bytes) -> Receipt:
        return self.send(agent, self.wallet.functions.agentTransfer(to_checksum_address(to), amount, intent_id))

    def agent_transfer_with_approval(self, agent, to: str, amount: int, intent_id: bytes) -> Receipt:
        return self.send(agent, self.wallet.functions.agentTransferWithApproval(to_checksum_address(to), amount, intent_id))

    # owner paths
    def approve_once(self, owner, intent_id: bytes, to: str, amount: int) -> Receipt:
        return self.send(owner, self.wallet.functions.approveOnce(intent_id, to_checksum_address(to), amount))

    def set_policy(self, owner, per_transfer_cap: int, rolling_cap: int) -> Receipt:
        return self.send(owner, self.wallet.functions.setPolicy(per_transfer_cap, rolling_cap))

    def set_allowlist(self, owner, to: str, allowed: bool) -> Receipt:
        return self.send(owner, self.wallet.functions.setAllowlist(to_checksum_address(to), allowed))

    def set_paused(self, owner, paused: bool) -> Receipt:
        return self.send(owner, self.wallet.functions.setPaused(paused))

    def owner_transfer(self, owner, to: str, amount: int, intent_id: bytes) -> Receipt:
        return self.send(owner, self.wallet.functions.ownerTransfer(to_checksum_address(to), amount, intent_id))

    def mint(self, account, to: str, amount: int) -> Receipt:
        return self.send(account, self.token.functions.mint(to_checksum_address(to), amount))

    # ------------------------------------------------------------------ deployment
    def deploy(self, owner, agent_address: str, per_transfer_cap: int, rolling_cap: int, save: bool = True) -> dict:
        tok_art = load_artifact("TestUSDC")
        wal_art = load_artifact("PolicyWallet")
        with self._lock:
            r1 = self._deploy_one(owner, tok_art, [])
            r2 = self._deploy_one(owner, wal_art, [to_checksum_address(agent_address), r1["address"], per_transfer_cap, rolling_cap])
        dep = {"chain": self.name, "chain_id": self.cfg["chain_id"], "token": r1["address"], "wallet": r2["address"],
               "owner": owner.address, "agent": to_checksum_address(agent_address), "deploy_block": r1["block"],
               "token_tx": r1["tx"], "wallet_tx": r2["tx"], "deployed_at": time.time(), "rpc": self.rpc_url}
        self.deployment = dep
        self.token = self.w3.eth.contract(address=dep["token"], abi=self.token_abi)
        self.wallet = self.w3.eth.contract(address=dep["wallet"], abi=self.wallet_abi)
        if save:
            config.DEPLOYMENTS.mkdir(parents=True, exist_ok=True)
            deployment_path(self.name).write_text(json.dumps(dep, indent=1))
        return dep

    def _deploy_one(self, owner, art: dict, args: list) -> dict:
        C = self.w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
        nonce = self.w3.eth.get_transaction_count(owner.address, "pending")
        base = self.w3.eth.get_block("latest").get("baseFeePerGas", 0) or 0
        prio = 10**9
        tx = C.constructor(*args).build_transaction({"from": owner.address, "nonce": nonce, "chainId": self.cfg["chain_id"],
                                                     "maxPriorityFeePerGas": prio, "maxFeePerGas": base * 2 + prio})
        tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.2)
        signed = owner.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        r = self.w3.eth.wait_for_transaction_receipt(h, timeout=240)
        if r["status"] != 1:
            raise ChainError(f"deployment of {art['contractName']} failed")
        return {"address": r["contractAddress"], "block": r["blockNumber"], "tx": hx(h)}

    # ------------------------------------------------------------------ local chain helpers
    def anvil_set_balance(self, addr: str, wei: int) -> None:
        self.w3.provider.make_request("anvil_setBalance", [to_checksum_address(addr), hex(wei)])


def account_from(key: str | None):
    if not key:
        raise ChainError("missing private key in .env (run: uv run python -m shouhu.keys)")
    return Account.from_key(key)
