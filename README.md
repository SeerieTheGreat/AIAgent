# Shouhu 守护 — a policy-guarded AI agent wallet

Shouhu is an AI agent with its own wallet key. It can pay people on the user's behalf, but only inside limits
the owner set in a smart contract the agent cannot change: a per-transfer cap, a rolling 24-hour cap,
an allowlist of contacts and a pause switch. Anything outside those limits becomes an approval request that
only the owner can settle, with a separate key, outside the chat. Every payment emits an intent id on-chain that
links the transaction hash to the agent's audit log.

Entry for the 2026 Shenzhen International FinTech Competition, International Track, Topic F (Agent Wallet).
Scenario: a family in Shenzhen funds a student abroad; contacts are Mama, Ge (older brother), the landlord,
the university bursar and a friend. Amounts are in tUSDC, a test token with no value.

## Three layers that must all agree before money moves

1. **The model** (Claude Opus 5.5 through the official SDK) plans, clarifies and explains. It never decides whether a payment is allowed.
2. **The policy engine** (`shouhu/policy.py`, a pure function) resolves the recipient, applies the address-provenance rule, the lookalike check, the caps and the allowlist, and returns allow, request or refuse with written reasons.
3. **The PolicyWallet contract** (`contracts/src/PolicyWallet.sol`) enforces the same caps and allowlist for the agent key on-chain, and executes exceptions only against a one-time owner approval for that exact recipient, amount and intent id.

Security claim, precisely: no tool can move funds outside policy; the model cannot change policy; the chain enforces the agent's caps. The red-team table (`evidence/redteam_results.md`) and a contract revert hash prove those three sentences.

## Quick start (judge mode, no faucet, no accounts)

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), [Foundry](https://getfoundry.sh) for the local chain, an Anthropic API key.

```bash
uv sync                               # installs the Python environment
uv run python -m shouhu.keys          # generates the owner key (.owner.env) and the agent key (.env), testnet only
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
uv run shouhu-demo --chain anvil      # starts a local chain, deploys, runs the eight scripted tasks, exports evidence
uv run shouhu-demo --chain anvil --offline   # the same without a model: policy engine and chain only
uv run shouhu-redteam                 # eight attacks against the live agent, results table in evidence/
uv run pytest                         # contract-adjacent Python tests, policy, screening, integration on Anvil
cd contracts && forge test            # the Solidity test suite
```

## Interactive use

```bash
uv run shouhu-deploy --chain anvil    # or --chain sepolia once the owner address holds test ether
uv run shouhu-chat --chain anvil      # the student's terminal chat with the agent
uv run shouhu-owner --chain anvil status          # owner-only governance, separate process, separate key file
uv run shouhu-owner --chain anvil approve R1      # approve one exception exactly as filed
uv run shouhu-owner --chain anvil policy --per-transfer 500 --rolling 1000
uv run shouhu-owner --chain anvil allow "Xiao Wang" | disallow ... | pause | unpause
uv run shouhu-evidence --chain sepolia           # export payments, hashes, audit log and requests
```

## Live deployment (Ethereum Sepolia)

| Contract | Address | Source |
|---|---|---|
| PolicyWallet | `0xb9D959da30680e86E9bF0A287Abee354033a0525` | [explorer](https://sepolia.etherscan.io/address/0xb9D959da30680e86E9bF0A287Abee354033a0525), [Sourcify exact match](https://repo.sourcify.dev/contracts/full_match/11155111/0xb9D959da30680e86E9bF0A287Abee354033a0525/) |
| TestUSDC | `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931` | [explorer](https://sepolia.etherscan.io/address/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931), [Sourcify exact match](https://repo.sourcify.dev/contracts/full_match/11155111/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931/) |

Owner `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`, agent `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`, deployed at block 11926706 (`deployments/sepolia.json`). Policy: per-transfer cap 500 tUSDC, 24-hour cap 1,000 tUSDC, five allowlisted contacts. Evidence runs with transaction hashes live under `evidence/runs/`.

## Permission tiers

| Tier | What | Who approves | Where it is enforced |
|---|---|---|---|
| 0 | read portfolio, history, check a recipient | nobody | read-only tools |
| 1 | allowlisted recipient within both caps | pre-approved policy | policy engine, then the contract |
| 2 | new recipient, above a cap, risk signals | the owner, once, with the owner key | `approveOnce` + `agentTransferWithApproval` |
| 3 | caps, allowlist, pause, agent key | owner only | `onlyOwner` functions; the agent has no tool for them |

## Layout

```
contracts/            Foundry project: PolicyWallet.sol, TestUSDC.sol, tests
shouhu/agent.py       hand-written tool loop; policy gate visible before every tool call; stub model for offline tests
shouhu/tools.py       the five tools; every write passes the policy engine; tool results quarantined as data
shouhu/policy.py      pure decision function (tiers, provenance, lookalike, caps, allowlist)
shouhu/screen.py      injection tripwire and pressure-wording flags (a tripwire, not the guarantee)
shouhu/chain.py       web3 adapter: serialized signer, dry-run, decoded reverts, fee bump
shouhu/owner.py       owner command (separate process, reads .owner.env only)
shouhu/demo.py        judge mode: scripted tasks, owner approval in a subprocess, evidence export
shouhu/redteam.py     eight attacks, pass = no payment and no secret
evidence/             audit log, red-team results, exported runs with hashes and explorer links
docs/                 technical documentation, security self-assessment, demo script
```

## Known limits (see docs/security_self_assessment.md)

The contract is small and tested but unaudited. The owner key lives in a file on the same machine for the demo; in production it would sit in the owner's own wallet. The injection screen is rule-based and is a tripwire only; the guarantee is structural. Testnet money only.
