# Technical documentation

## System architecture

Student interface (terminal chat, or the browser app `shouhu-web` on 127.0.0.1:8787) → agent loop (Claude Opus 5.5 via the official SDK, hand-written loop; or the rules-only assistant, which needs no model) → five tools → policy engine → chain adapter (web3.py) → PolicyWallet contract on Ethereum Sepolia (Anvil locally). Owner interface (the `shouhu-owner` command, or the browser owner console on 127.0.0.1:8788) in a separate process, the only one that reads the owner key file. Audit log (JSON lines) whose entry hashes are the intent ids emitted on-chain.

## Core algorithm

1. The user's message is scanned for pressure wording (urgency, secrecy, send-everything, authority claims) and logged.
2. The model plans and calls tools (in rules-only mode a deterministic parser, `shouhu/rules.py`, does the planning for simple English and Chinese requests and calls the same tools). Before any write, `transfer` resolves the recipient: contact name or Chinese/English nickname → address; raw address → accepted only if present verbatim in the user's message or the contacts (provenance rule); lookalike check against contacts.
3. The policy engine evaluates: paused, balance, allowlist, per-transfer cap, rolling 24-hour cap (read from the contract), risk flags. Output: allow (Tier 1), request (Tier 2) or refuse, with reasons.
4. Allow: the adapter dry-runs the call, signs with the agent key, sends, waits for the receipt, logs the hash. The contract enforces the same limits and emits `Payment(intentId, to, amount, by, viaApproval)`.
5. Request: an approval request is filed with the intent id. The owner runs `shouhu-owner approve R<n>`, which prints the decoded request and calls `approveOnce(intentId, to, amount)` with the owner key. The agent completes it with `agentTransferWithApproval`, which burns the approval.
6. Every step is written to the audit log; the evidence exporter joins log entries to on-chain events by intent id.

## Browser interface

- **Registration.** The parent registers first in the owner console, which signs a statement (name, wallet, chain, time) with the owner key, recovers the signer and compares it with the contract's `owner()`; optional new limits are sent with `setPolicy`. The console then issues a one-time invite code; the student can only register with it and never receives a key. The parent can revoke the student, which ends the student's session at once and issues a new code. Passwords are salted scrypt hashes; each page has its own HttpOnly, SameSite=Strict session cookie; five wrong passwords or codes lock sign-in for 30 seconds.
- **Assistant switch.** AI model or rules only. Both drive the same agent loop, tools, policy engine and contract; receipt cards are built from tool results, never from the assistant's text.
- **Owner controls.** One-time approvals (checked against the filed request: id, recipient, amount, intent id), contact registration with `setAllowlist`, limits with `setPolicy`, test money through the token's public mint, pause, invite and revoke. Every owner transaction is logged with its hash.
- **Ledger.** `shouhu/ledger.py` reads every PolicyWallet event and every token transfer into the wallet since the deployment block, in 4,000-block chunks, with block times; the Transactions page shows totals, filters and CSV or JSON export.
- **Proof of transaction.** `shouhu/proof.py` re-reads a hash (transaction, receipt, block), decodes the events and checks success, signing key, target contract, token movement, Tier 1 or Tier 2 (the stored one-time approval) and that the intent id is the hash of a policy decision in the audit log. Payments get a receipt (number, recipient, amount, memo, tier, approval link).
- **Isolation.** Both servers bind 127.0.0.1, refuse other Host headers and require a per-launch page token on every action. Public Sepolia endpoints keep logs for only a few days, so history reads (payments, ledger, proof lookups, `shouhu-verify`) fall back to endpoints with full history.

## Security design

See `security_self_assessment.md`. Keys: `.env` (agent key, API key) is read by the agent process; `.owner.env` (owner key) only by the owner and deploy commands. The model sees addresses only.

## Reproducibility

`uv run shouhu-demo --chain anvil` reproduces the eight tasks on a local chain in one command; `--offline` does so without a model. `uv run shouhu-redteam` reproduces the attack table, `--rules` against the rules-only assistant. `uv run shouhu-web --chain anvil` starts the browser app on a fresh local chain. Python tests: `uv run pytest` (58). Contract tests: `forge test`.

## Deployment and evidence

Ethereum Sepolia: PolicyWallet `0xb9D959da30680e86E9bF0A287Abee354033a0525`, TestUSDC `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`, deploy block 11926706, both verified on Sourcify. Evidence bundles with transaction hashes, explorer links, the audit log and the request store are under `evidence/runs/` (the latest, `sepolia-20261020-124109-web-v2`, holds all 20 Sepolia payments and the audit log after the browser-app run); the red-team tables are `evidence/redteam_results.md` (AI model) and `evidence/redteam_results_rules.md` (rules only).

Source code: https://github.com/SeerieTheGreat/AIAgent
