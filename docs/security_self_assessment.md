# Security self-assessment (draft for the submission)

## Permission-tier implementation

- Tier 0 (observe): `get_portfolio`, `get_history`, `check_recipient` are read-only.
- Tier 1 (routine): `transfer` executes only when the deterministic policy engine returns `allow`: allowlisted recipient, amount within the per-transfer cap, rolling 24-hour cap not exceeded, wallet not paused, balance sufficient, no address-poisoning match, address provenance satisfied. The contract re-checks caps, allowlist and pause for the agent key.
- Tier 2 (exception): anything else becomes an approval request. The owner approves exactly that recipient, amount and intent id with `approveOnce` from a separate process holding the owner key; the agent then calls `agentTransferWithApproval`, which burns the approval.
- Tier 3 (governance): caps, allowlist, pause, agent-key rotation and owner withdrawals are `onlyOwner`. The agent has no tool that reaches them.

## Threats and defences

| Threat | Defence | Evidence |
|---|---|---|
| Induced transfer (urgency, threats, "send everything") | wording flags escalate to Tier 2; new recipients are never Tier 1; contract caps bound any damage | red-team A1, A2 |
| Prompt injection through data (token names, memos, pasted messages) | tool results are wrapped as untrusted data with injection flags; the system prompt treats them as data; no tool can change policy | A3, A4, scripted task 6 |
| Privilege escalation ("I am the owner") | no policy tools; owner identity cannot be asserted in chat; contract `onlyOwner` | A5, task 7 |
| Information extraction | keys and settings never enter the model context; refusal rule | A7 |
| Address poisoning | lookalike check against contacts (same prefix and suffix, different middle) refuses before policy | task 5 |
| Hallucinated or injected addresses | provenance rule: a raw address must appear verbatim in the user's message or in the owner's contacts | A8, task 4 |
| Cap evasion by splitting | rolling 24-hour cap in hourly buckets on-chain; new recipients need approval anyway | A6 |
| Double payment | single serialized signer, dry-run before send, persisted request state, one-time approvals burn on use | contract tests |

## Known risks

1. The contract is unaudited; it is small (about 120 lines) with a test suite, but a formal review has not been done.
2. The owner key is a file on the same machine for the demo. Production would use the owner's own wallet or a hardware signer.
3. The injection screen is rule-based; it is a tripwire for logging, not the security boundary. The boundary is structural: tools, policy engine, contract.
4. Public RPC endpoints can rate-limit; the adapter retries across endpoints, and the evidence run is short.
5. Testnet tokens have no value; the design assumes a regulated stablecoin or tokenised deposit in production.
6. The model may refuse or stall; refusals are handled as a polite non-action and logged.
