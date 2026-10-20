"""Re-check the Shouhu execution evidence against Ethereum Sepolia, without the app's code.

Run from the repository root (after `uv sync`):

    uv run python evidence/onchain/check_onchain.py

It reads transactions.json, rejections.json and audit_log.jsonl from this folder and uses only raw JSON-RPC calls
and its own event decoding (eth_utils and eth_abi), so a bug in the app cannot hide itself. It checks:

  1. every listed transaction: status, block, time, sender, recipient, nonce, gas, fee, the function called and the events;
  2. completeness: the owner key and the agent key signed exactly the listed transactions (their nonces);
  3. the wallet's balance equals the deposits minus the payments;
  4. every Tier 2 payment used the owner's one-time approval for the same intent id, now marked used;
  5. the allowlist and the limits;
  6. the three rejected transactions revert again, with the same errors, when replayed at the block before;
  7. every payment's intent id is the hash of a policy decision in audit_log.jsonl with the same amount, recipient and tier.
  8. both contracts are verified on Sourcify with an exact match (skipped if Sourcify cannot be reached).

State checks (2 to 5) are made at the block where the evidence was collected, so later activity does not change them.
They need a node that serves past state; set SEPOLIA_RPC_URL to use your own.
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from eth_abi import decode
from eth_utils import keccak

HERE = Path(__file__).resolve().parent
DATA = json.loads((HERE / "transactions.json").read_text(encoding="utf8"))
REJ = json.loads((HERE / "rejections.json").read_text(encoding="utf8"))
# the submission folder carries a copy of the audit log; in the repository it is in the evidence bundle
AUDIT_FILE = next(f for f in (HERE / "audit_log.jsonl", HERE.parent / "runs/sepolia-20261020-181247/audit_log.jsonl") if f.exists())
AUDIT = [json.loads(l) for l in AUDIT_FILE.read_text(encoding="utf8").splitlines() if l.strip()]
RECS = DATA["transactions"]
W, T = DATA["wallet"].lower(), DATA["token"].lower()
OWNER, AGENT = DATA["owner"].lower(), DATA["agent"].lower()
AT = hex(DATA["collected_at_block"])
UNIT = 10 ** 6                                   # tUSDC has 6 decimals
UTC8 = timezone(timedelta(hours=8))
RPCS = [u for u in [os.environ.get("SEPOLIA_RPC_URL"), "https://gateway.tenderly.co/public/sepolia",
                    "https://eth-sepolia.api.onfinality.io/public", "https://0xrpc.io/sep", "https://ethereum-sepolia-rpc.publicnode.com"] if u]
fails, passes = [], 0


def rpc(method, params):
    """Ask each endpoint in turn; a revert in eth_call comes back as {'revert': error}."""
    last = None
    for url in RPCS:
        for _ in range(2):
            try:
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": "shouhu-check/1"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    out = json.loads(r.read())
                if "error" in out:
                    if method == "eth_call" and "revert" in json.dumps(out["error"]).lower():
                        return {"revert": out["error"]}
                    last = out["error"]; break             # this endpoint cannot answer (for example pruned state)
                if out.get("result") is not None:
                    return out["result"]
                last = "empty result"; break
            except Exception as e:
                last = e; time.sleep(1)
    raise RuntimeError(f"{method}: no endpoint answered ({last})")


def check(ok, what):
    global passes
    if ok:
        passes += 1
    else:
        fails.append(what); print("FAIL", what)


sig = lambda text: "0x" + keccak(text=text).hex()
selector = lambda text: sig(text)[:10]
EVENTS = {sig("Payment(bytes32,address,uint256,address,bool)"): "Payment", sig("ApprovalGranted(bytes32,address,uint256)"): "ApprovalGranted",
          sig("AllowlistUpdated(address,bool)"): "AllowlistUpdated", sig("PolicyUpdated(uint256,uint256)"): "PolicyUpdated",
          sig("AgentUpdated(address)"): "AgentUpdated", sig("PausedSet(bool)"): "PausedSet", sig("Transfer(address,address,uint256)"): "Transfer"}
ERRORS = {selector(e): e for e in ["NotOwner()", "NotAgent()", "IsPaused()", "NotAllowlisted(address)", "ExceedsPerTransferCap(uint256,uint256)",
                                   "ExceedsRollingCap(uint256,uint256,uint256)", "ApprovalMismatch()", "ApprovalUsed()", "TransferFailed()", "ZeroAddress()"]}
topic_addr = lambda t: "0x" + t[-40:]


def decode_log(lg):
    name, data = EVENTS.get(lg["topics"][0] if lg["topics"] else ""), bytes.fromhex(lg["data"][2:])
    e = {"event": name, "contract": lg["address"].lower()}
    if name == "Payment":
        amount, via = decode(["uint256", "bool"], data)
        e.update(intent=lg["topics"][1].lower(), to=topic_addr(lg["topics"][2]), by=topic_addr(lg["topics"][3]), amount=amount, via_approval=via)
    elif name == "ApprovalGranted":
        e.update(intent=lg["topics"][1].lower(), to=topic_addr(lg["topics"][2]), amount=decode(["uint256"], data)[0])
    elif name == "AllowlistUpdated":
        e.update(to=topic_addr(lg["topics"][1]), allowed=decode(["bool"], data)[0])
    elif name == "PolicyUpdated":
        e.update(per_transfer=decode(["uint256", "uint256"], data)[0], rolling=decode(["uint256", "uint256"], data)[1])
    elif name == "AgentUpdated":
        e.update(agent=topic_addr(lg["topics"][1]))
    elif name == "Transfer":
        e.update(frm=topic_addr(lg["topics"][1]), to=topic_addr(lg["topics"][2]), amount=decode(["uint256"], data)[0])
    return e


def call(fn_sig, args_hex="", block=AT, to=W):
    return rpc("eth_call", [{"to": to, "data": selector(fn_sig) + args_hex}, block])


pad = lambda a: "0" * 24 + a[2:].lower()

# 1. every listed transaction ------------------------------------------------------------------------------------
print(f"Checking {len(RECS)} records ({len(dict.fromkeys(r['tx_hash'] for r in RECS))} transactions) against Sepolia, "
      f"collected at block {DATA['collected_at_block']:,} ({DATA['collected_at_utc8']} UTC+8)")
chain = {}
for h in dict.fromkeys(r["tx_hash"].lower() for r in RECS):
    tx, rc = rpc("eth_getTransactionByHash", [h]), rpc("eth_getTransactionReceipt", [h])
    blk = rpc("eth_getBlockByNumber", [rc["blockNumber"], False])
    chain[h] = {"tx": tx, "rc": rc, "time": int(blk["timestamp"], 16), "logs": [decode_log(l) for l in rc["logs"]]}

for r in RECS:
    h = r["tx_hash"].lower(); c = chain[h]; tx, rc = c["tx"], c["rc"]
    tag = f"{r['time_utc8']} {h[:12]} ({r['details'][:48]})"
    check(int(rc["status"], 16) == r["status"], f"{tag}: status")
    check(int(rc["blockNumber"], 16) == r["block"], f"{tag}: block")
    check(c["time"] == r["time"] and datetime.fromtimestamp(c["time"], UTC8).strftime("%Y-%m-%d %H:%M:%S") == r["time_utc8"], f"{tag}: time")
    check(tx["from"].lower() == r["from"].lower(), f"{tag}: sender")
    check((tx["to"] or "").lower() == (r["to"] or "").lower(), f"{tag}: recipient")
    check((rc.get("contractAddress") or "").lower() == (r.get("contract_created") or "").lower(), f"{tag}: created contract")
    check(int(tx["nonce"], 16) == r["nonce"], f"{tag}: nonce")
    gas = int(rc["gasUsed"], 16)
    check(gas == r["gas_used"] and abs(gas * int(rc["effectiveGasPrice"], 16) / 1e18 - r["fee_eth"]) < 1e-12, f"{tag}: gas and fee")
    logs, cat = c["logs"], r["category"]
    if cat == "payment":
        pay = [e for e in logs if e["event"] == "Payment"]
        check(len(pay) == 1, f"{tag}: one Payment event")
        if pay:
            p = pay[0]
            check(p["intent"] == r["intent_id"].lower(), f"{tag}: intent id")
            check(p["by"] == AGENT and tx["from"].lower() == AGENT, f"{tag}: signed by the agent key")
            check(p["amount"] == round(float(r["amount"].replace(",", "").split()[0]) * UNIT), f"{tag}: amount")
            check((2 if p["via_approval"] else 1) == r["tier"], f"{tag}: tier")
            fn = "agentTransferWithApproval(address,uint256,bytes32)" if p["via_approval"] else "agentTransfer(address,uint256,bytes32)"
            check(tx["input"][:10] == selector(fn), f"{tag}: function {fn.split('(')[0]}")
            check(any(e["event"] == "Transfer" and e["contract"] == T and e["frm"] == W and e["to"] == p["to"] and e["amount"] == p["amount"] for e in logs),
                  f"{tag}: the token moved the same amount from the wallet to the recipient")
    elif cat == "approval":
        g = [e for e in logs if e["event"] == "ApprovalGranted"]
        check(len(g) == 1 and g[0]["intent"] == r["intent_id"].lower() and tx["from"].lower() == OWNER, f"{tag}: owner approval for this intent id")
    elif cat == "governance":
        check(any(e["event"] == r["event"] for e in logs) and tx["from"].lower() == OWNER, f"{tag}: {r['event']} signed by the owner key")
    elif cat == "deposit":
        check(any(e["event"] == "Transfer" and e["contract"] == T and e["to"] == W and e["amount"] == round(float(r["amount"].replace(",", "").split()[0]) * UNIT)
                  for e in logs), f"{tag}: tokens into the wallet")
    elif cat == "deployment":
        check((rc.get("contractAddress") or "").lower() in (W, T) and tx["to"] is None and tx["from"].lower() == OWNER, f"{tag}: contract created by the owner key")
    elif cat == "rejected":
        check(int(rc["status"], 16) == 0 and not logs and tx["from"].lower() == AGENT, f"{tag}: failed, no events, sent by the agent key")
    elif cat == "gas":
        # a plain ether transfer; this version of Sepolia logs ether transfers from the system address 0xfff...fffe
        stated = round(float(r["details"].split(" ETH")[0]) * 10 ** 18)
        check(tx["input"] == "0x" and int(tx["value"], 16) == stated and all(e["contract"] == "0x" + "f" * 39 + "e" for e in logs),
              f"{tag}: plain ether transfer of the stated amount")

# 2. completeness: every transaction the two keys ever signed is in the file ----------------------------------------------
for name, key in (("owner key", OWNER), ("agent key", AGENT)):
    signed = {h for h, c in chain.items() if c["tx"]["from"].lower() == key}
    nonce = int(rpc("eth_getTransactionCount", [key, AT]), 16)
    check(nonce == len(signed), f"{name}: nonce {nonce} at the collection block, {len(signed)} transactions listed")
    print(f"  {name}: signed {nonce} transactions up to block {DATA['collected_at_block']:,}; all {len(signed)} are listed")

# 3. balance -----------------------------------------------------------------------------------------------------
ok_tx = [c for c in chain.values() if int(c["rc"]["status"], 16) == 1]
inflow = sum(e["amount"] for c in ok_tx for e in c["logs"] if e["event"] == "Transfer" and e["contract"] == T and e["to"] == W)
outflow = sum(e["amount"] for c in ok_tx for e in c["logs"] if e["event"] == "Transfer" and e["contract"] == T and e["frm"] == W)
balance = int(call("balanceOf(address)", pad(W), to=T), 16)
check(balance == inflow - outflow, f"balance {balance / UNIT:,} tUSDC vs deposits {inflow / UNIT:,} minus payments {outflow / UNIT:,}")
print(f"  wallet balance {balance / UNIT:,.0f} tUSDC = {inflow / UNIT:,.0f} deposited - {outflow / UNIT:,.0f} paid")
payments = [e for c in ok_tx for e in c["logs"] if e["event"] == "Payment"]
check(all(e["by"] == AGENT for e in payments), "every payment was made by the agent key (no owner transfers)")

# 4. approvals ---------------------------------------------------------------------------------------------------
for c in ok_tx:
    for g in (e for e in c["logs"] if e["event"] == "ApprovalGranted"):
        to, amount, used = decode(["address", "uint256", "bool"], bytes.fromhex(call("approvals(bytes32)", g["intent"][2:])[2:]))
        paid = [p for p in payments if p["intent"] == g["intent"]]
        check(used and to.lower() == g["to"] and amount == g["amount"] and len(paid) == 1 and paid[0]["via_approval"]
              and paid[0]["to"] == g["to"] and paid[0]["amount"] == g["amount"], f"approval {g['intent'][:12]}: used once, by a payment of exactly that amount to that recipient")

# 5. allowlist and limits ------------------------------------------------------------------------------------------
last = {}
for c in sorted(ok_tx, key=lambda c: int(c["rc"]["blockNumber"], 16)):
    for e in c["logs"]:
        if e["event"] == "AllowlistUpdated":
            last[e["to"]] = e["allowed"]
for a, allowed in last.items():
    now = decode(["bool"], bytes.fromhex(call("allowlist(address)", pad(a))[2:]))[0]
    check(now == allowed, f"allowlist {a}: {now}")
print(f"  allowlisted: {sum(1 for v in last.values() if v)} addresses")
policy = [e for c in sorted(ok_tx, key=lambda c: int(c["rc"]["blockNumber"], 16)) for e in c["logs"] if e["event"] == "PolicyUpdated"][-1]
per, roll = (int(call(f), 16) for f in ("perTransferCap()", "rollingCap()"))
paused = int(call("paused()"), 16)
check((per, roll, paused) == (policy["per_transfer"], policy["rolling"], 0), f"limits {per / UNIT:,.0f} / {roll / UNIT:,.0f} tUSDC as last set, paused {paused}")
print(f"  limits {per / UNIT:,.0f} tUSDC per transfer, {roll / UNIT:,.0f} tUSDC per 24 hours, not paused")
check(topic_addr(call("owner()")) == OWNER and topic_addr(call("agent()")) == AGENT, "owner and agent keys of the contract")

# 6. rejected transactions, replayed at the block before ----------------------------------------------------------
for x in REJ:
    tx = chain[x["tx_hash"].lower()]["tx"]; blk = int(chain[x["tx_hash"].lower()]["rc"]["blockNumber"], 16)
    res = rpc("eth_call", [{"from": tx["from"], "to": tx["to"], "data": tx["input"], "gas": tx["gas"]}, hex(blk - 1)])
    err = res.get("revert") if isinstance(res, dict) else None
    data = err.get("data") if isinstance(err, dict) else None
    data = data.get("data") if isinstance(data, dict) else data
    name = ERRORS.get((data or "")[:10])
    if name is None:
        check(False, f"rejection {x['tx_hash'][:12]}: the replay did not revert with a known error ({str(res)[:80]})"); continue
    types = name[name.index("(") + 1:-1]
    args = decode(types.split(","), bytes.fromhex(data[10:])) if types else ()
    shown = name.split("(")[0] + "(" + ", ".join(str(a).lower() if isinstance(a, str) else str(a) for a in args) + ")"
    recorded = x["revert_reason"].split("(")[0] + "(" + ", ".join(v.split("=")[-1].lower() for v in x["revert_reason"][x["revert_reason"].index("(") + 1:-1].split(", ") if v) + ")"
    check(shown == recorded, f"rejection {x['tx_hash'][:12]}: replay gives {shown}, recorded {x['revert_reason']}")
    print(f"  {x['tx_hash'][:12]} replayed at block {blk - 1:,}: {shown}")

# 7. intent ids and decisions ------------------------------------------------------------------------------------
def intent_of(e):
    return "0x" + keccak(text=json.dumps({k: e[k] for k in ("session", "seq", "event", "ts")}, sort_keys=True)).hex()
decisions = {intent_of(e): e for e in AUDIT if e.get("event") == "decision"}
for r in RECS:
    if r["category"] != "payment":
        continue
    p = next(e for e in chain[r["tx_hash"].lower()]["logs"] if e["event"] == "Payment")
    d = decisions.get(p["intent"])
    check(d is not None and d["amount"] == p["amount"] and d["resolved"].lower() == p["to"] and d["tier"] == (2 if p["via_approval"] else 1)
          and d["user_message"] == r["user_message"], f"{r['tx_hash'][:12]}: decision with the same amount, recipient, tier and words")

# 8. source code: the deployed bytecode is verified on Sourcify (skipped, not failed, if Sourcify cannot be reached) ------------
for label, a in (("PolicyWallet", W), ("TestUSDC", T)):
    try:
        req = urllib.request.Request(f"https://sourcify.dev/server/v2/contract/11155111/{a}", headers={"User-Agent": "shouhu-check/1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            v = json.loads(r.read())
        check(v.get("creationMatch") == "exact_match" and v.get("runtimeMatch") == "exact_match", f"Sourcify {label}: {v.get('match')}")
        print(f"  Sourcify {label}: creation {v.get('creationMatch')}, runtime {v.get('runtimeMatch')}")
    except Exception as e:
        print(f"  SKIP Sourcify {label}: not reachable ({str(e)[:60]})")

print(f"\n{passes} checks passed, {len(fails)} failed")
sys.exit(1 if fails else 0)
