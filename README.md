# Shouhu 守护 — a policy-guarded AI agent wallet

Shouhu is an AI agent with its own wallet key. It can pay people on the user's behalf, but only inside limits
the owner set in a smart contract the agent cannot change: a per-transfer cap, a rolling 24-hour cap,
an allowlist of contacts and a pause switch. Anything outside those limits becomes an approval request that
only the owner can settle, with a separate key, outside the chat. Every payment emits an intent id on-chain that
links the transaction hash to the agent's audit log.

Entry for the 2026 Shenzhen International FinTech Competition, International Track, Topic F (Agent Wallet).
Repository: https://github.com/SeerieTheGreat/AIAgent
Scenario: a family in Shenzhen funds a student abroad; contacts are Mama, Ge (older brother), the landlord,
the university bursar and a friend. Amounts are in tUSDC, a test token with no value.

## Three layers that must all agree before money moves

1. **The model** (Claude Opus 5.5 through the official SDK) plans, clarifies and explains. It never decides whether a payment is allowed.
2. **The policy engine** (`shouhu/policy.py`, a pure function) resolves the recipient, applies the address-provenance rule, the lookalike check, the caps and the allowlist, and returns allow, request or refuse with written reasons.
3. **The PolicyWallet contract** (`contracts/src/PolicyWallet.sol`) enforces the same caps and allowlist for the agent key on-chain, and executes exceptions only against a one-time owner approval for that exact recipient, amount and intent id.

Security claim, precisely: no tool can move funds outside policy; the model cannot change policy; the chain enforces the agent's caps. The red-team table (`evidence/redteam_results.md`) and a contract revert hash prove those three sentences.

Technical documentation (system architecture, core algorithms, security design): `docs/Shouhu_Technical_Documentation.pdf`, also readable here as [`docs/technical_documentation.md`](docs/technical_documentation.md).

## Quick start (judge mode, no faucet, no accounts)

Requirements: Python 3.12 via [uv](https://docs.astral.sh/uv/), [Foundry](https://getfoundry.sh) for the local chain, an Anthropic API key.

```bash
uv sync                               # installs the Python environment
uv run python -m shouhu.keys          # generates the owner key (.owner.env) and the agent key (.env), testnet only
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
uv run shouhu-demo --chain anvil      # starts a local chain, deploys, runs the eight scripted tasks, exports evidence
uv run shouhu-demo --chain anvil --offline   # the same without a model: policy engine and chain only
uv run shouhu-redteam                 # eight attacks against the live agent, results table in evidence/
uv run shouhu-redteam --rules         # the same attacks against the rules-only assistant (no model)
uv run pytest                         # contract-adjacent Python tests, policy, screening, integration on Anvil
cd contracts && forge install foundry-rs/forge-std@v1.17.0 --no-git   # once: the test library (contracts/lib is not committed)
forge test                            # the Solidity test suite (12 tests)
```

## Interactive use

```bash
uv run shouhu-deploy --chain anvil    # or --chain sepolia once the owner address holds test ether
uv run shouhu-chat --chain anvil      # the student's terminal chat with the agent (--rules: no model)
uv run shouhu-owner --chain anvil status          # owner-only governance, separate process, separate key file
uv run shouhu-owner --chain anvil approve R1      # approve one exception exactly as filed
uv run shouhu-owner --chain anvil policy --per-transfer 500 --rolling 1000
uv run shouhu-owner --chain anvil allow "Xiao Wang" | disallow ... | pause | unpause
uv run shouhu-evidence --chain sepolia           # export payments, hashes, audit log and requests
```

## Browser interface

```bash
uv run shouhu-web --chain sepolia --reset-demo   # live wallet, clean sign-ups; or --chain anvil for a fresh local chain
uv run shouhu-web --chain anvil --assistant rules # no model at all (also the default when no API key is set)
```

Opens the student's chat at http://127.0.0.1:8787/ and starts the owner console at http://127.0.0.1:8788/ as a
separate process, the only one that reads `.owner.env`. Both have a top bar (Chat or Console, Transactions, Verify).

- **Registration with an invite code.** The parent registers first, in the owner console: the console signs a
  statement with the owner key and refuses unless the signer is the contract's `owner()`; optional new limits go
  on-chain with `setPolicy`. The parent then gets a one-time invite code (and link) for the student; the student
  can only sign up with it (name, Chinese name, password; bound to the wallet, no key). The parent can revoke the
  student, which ends the student's session at once and issues a new code. Passwords are salted scrypt hashes in
  `data/accounts.json`; each page has its own session cookie; five wrong passwords or codes lock sign-in for 30 s.
  `--reset-accounts` shows the sign-up screens again; `--reset-demo` also clears requests, registered contacts and
  owner activity, for a clean live demo (script: `docs/Shouhu_Live_Demo_Script.pdf`).
- **The chat.** A receipt card for every tool result (paid with the transaction hash, request filed for the owner,
  or refused with reasons), the live caps and 24-hour spend, approval requests, contacts and recent payments. The
  header switches between the **AI model** and **Rules only**: a deterministic assistant (`shouhu/rules.py`) that
  reads simple English and Chinese requests and calls the same five tools, so the policy engine and the contract
  decide exactly as with the model. It is the fallback when the model is unavailable.
- **Owner console.** Approve a request once, exactly as filed, or deny it; register a contact (name, Chinese name,
  address or a generated test address) with `setAllowlist` in the same step; change the limits (`setPolicy`); add
  test money (the token's public mint); pause the agent; invite or revoke the student. Every owner transaction is
  listed with its proof.
- **Transactions.** `/transactions` on either page lists every event of the wallet read from the chain since the
  deployment (payments, one-time approvals, allowlist and limit changes, pauses, money added), with totals,
  filters, the signing key, proof links, and CSV or JSON export (`shouhu/ledger.py`).
- **Proof of transaction.** `/proof?tx=0x…` re-reads a transaction, its receipt and block from the chain, decodes
  the events and checks: success, signing key, target contract, token movement, Tier 1 or Tier 2 (the stored
  one-time approval), and that the on-chain intent id is the hash of a policy decision in the audit log. Payments
  get a receipt (number, recipient, amount, memo, tier, approval link) and a "check it yourself" panel with the
  Etherscan link and the `shouhu-verify` command. Printable and downloadable as JSON.

Both servers listen on 127.0.0.1 only, refuse foreign Host headers, require a signed-in session for data and a
per-launch page token on every action. The local chain keeps its accounts and requests in `data/anvil/`.
Standard library only; no extra dependencies. Walkthrough with screenshots: `docs/Shouhu_Demo_Guide.pdf`, Section 6.

## Live deployment (Ethereum Sepolia)

| Contract | Address | Source |
|---|---|---|
| PolicyWallet | `0xb9D959da30680e86E9bF0A287Abee354033a0525` | [explorer](https://sepolia.etherscan.io/address/0xb9D959da30680e86E9bF0A287Abee354033a0525), [Sourcify exact match](https://repo.sourcify.dev/contracts/full_match/11155111/0xb9D959da30680e86E9bF0A287Abee354033a0525/) |
| TestUSDC | `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931` | [explorer](https://sepolia.etherscan.io/address/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931), [Sourcify exact match](https://repo.sourcify.dev/contracts/full_match/11155111/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931/) |

Owner `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`, agent `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`, deployed at block 11926706 (`deployments/sepolia.json`). Policy: per-transfer cap 500 tUSDC, 24-hour cap 1,000 tUSDC, six allowlisted contacts (the five defaults and Aunt Li, added from the web console). Evidence runs with transaction hashes live under `evidence/runs/`; the latest, `evidence/runs/sepolia-20261020-124109-web-v2/`, holds all 20 Sepolia payments with the audit log. Public endpoints keep logs for only a few days, so history reads fall back to endpoints with full history (`HISTORY_RPCS` in `shouhu/chain.py`).

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
shouhu/webapp.py      browser interface for the student's chat (agent key only); starts the owner console
shouhu/owner_web.py   owner console in the browser (separate process, owner key); shouhu/static/ holds the pages
shouhu/accounts.py    student and parent sign-up and sign-in (scrypt hashes, sessions, invite codes)
shouhu/rules.py       rules-only assistant: no model, same tools, same policy engine
shouhu/ledger.py      every wallet event read from the chain, for the Transactions page
shouhu/proof.py       proof of transaction: re-reads a hash from the chain and checks it
shouhu/demo.py        judge mode: scripted tasks, owner approval in a subprocess, evidence export
shouhu/redteam.py     eight attacks, pass = no payment and no secret
evidence/             audit log, red-team results, exported runs with hashes and explorer links
docs/                 technical documentation (PDF and Markdown), security self-assessment, demo script
```

## Known limits (see docs/security_self_assessment.md)

The contract is small and tested but unaudited. The owner key lives in a file on the same machine for the demo; in production it would sit in the owner's own wallet. The injection screen is rule-based and is a tripwire only; the guarantee is structural. Testnet money only.

## Rights

Copyright 2026 the Shouhu team. All rights reserved. Submitted to the 2026 Shenzhen International FinTech Competition (International Track, Topic F); the organisers may use the entry for non-commercial promotion as set out in the competition rules. Intellectual property remains with the contestants.
