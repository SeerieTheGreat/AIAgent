# Technical documentation (draft for the submission)

## System architecture

Terminal chat → agent loop (Claude Opus 5.5 via the official SDK, hand-written loop) → five tools → policy engine → chain adapter (web3.py) → PolicyWallet contract on Ethereum Sepolia (Anvil locally). Owner command in a separate process with its own key file. Audit log (JSON lines) whose entry hashes are the intent ids emitted on-chain.

## Core algorithm

1. The user's message is scanned for pressure wording (urgency, secrecy, send-everything, authority claims) and logged.
2. The model plans and calls tools. Before any write, `transfer` resolves the recipient: contact name or Chinese/English nickname → address; raw address → accepted only if present verbatim in the user's message or the contacts (provenance rule); lookalike check against contacts.
3. The policy engine evaluates: paused, balance, allowlist, per-transfer cap, rolling 24-hour cap (read from the contract), risk flags. Output: allow (Tier 1), request (Tier 2) or refuse, with reasons.
4. Allow: the adapter dry-runs the call, signs with the agent key, sends, waits for the receipt, logs the hash. The contract enforces the same limits and emits `Payment(intentId, to, amount, by, viaApproval)`.
5. Request: an approval request is filed with the intent id. The owner runs `shouhu-owner approve R<n>`, which prints the decoded request and calls `approveOnce(intentId, to, amount)` with the owner key. The agent completes it with `agentTransferWithApproval`, which burns the approval.
6. Every step is written to the audit log; the evidence exporter joins log entries to on-chain events by intent id.

## Security design

See `security_self_assessment.md`. Keys: `.env` (agent key, API key) is read by the agent process; `.owner.env` (owner key) only by the owner and deploy commands. The model sees addresses only.

## Reproducibility

`uv run shouhu-demo --chain anvil` reproduces the eight tasks on a local chain in one command; `--offline` does so without a model. `uv run shouhu-redteam` reproduces the attack table. Contract tests: `forge test`.
