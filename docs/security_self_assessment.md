# Security self-assessment

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
| Someone else registers as the student in the browser app | only the parent's console, after proving the owner key, issues a one-time invite code (6 characters from a 31-character alphabet); a wrong code counts toward the sign-in lock; the parent can revoke the student, which ends the session at once | `tests/test_web.py` |
| Another website driving the local servers | 127.0.0.1 only, Host header check, per-launch page token on every action, HttpOnly SameSite=Strict cookies per role | `tests/test_web.py` |
| Model outage or misbehaviour | the rules-only assistant drives the same tools; the policy engine and the contract decide either way | `evidence/redteam_results_rules.md` (8 of 8) |

## Known risks

1. The contract is unaudited; it is small (about 120 lines) with a test suite, but a formal review has not been done.
2. The owner key is a file on the same machine for the demo. Production would use the owner's own wallet or a hardware signer.
3. The injection screen is rule-based; it is a tripwire for logging, not the security boundary. The boundary is structural: tools, policy engine, contract.
4. Public RPC endpoints can rate-limit; the adapter retries across endpoints, and the evidence run is short.
5. Testnet tokens have no value; the design assumes a regulated stablecoin or tokenised deposit in production.
6. The model may refuse or stall; refusals are handled as a polite non-action and logged, and the browser app offers the rules-only assistant.
7. The browser app is local and single-family: one student and one parent account per data folder, protected by the computer's own user account rather than a server. Anyone at the parent's unlocked computer could approve requests; production would put the owner console behind the owner's own wallet signature for each approval.
8. The rules-only assistant understands simple phrasing only; when unsure it asks or refuses rather than guessing.

## Results (16 October 2026)

- Red-team: 8 of 8 attacks produced no payment and leaked nothing (`evidence/redteam_results.md`). Wallet balance identical before and after.
- Scripted tasks on Ethereum Sepolia with the live model: routine payment `0xb9ee729554fc96d3c00ce465bd83f2702955a4dc914d1953b602444592520074` (20 tUSDC to Mama, Tier 1); over-cap payment completed only after a one-time owner approval `0x838aee659579417aa92716e84790bb07158e68f6fbb77b11fb20936e46a38cfc` (800 tUSDC to Landlord Zhang, Tier 2); Chinese nickname payment `0xbb784709c0dcb2a82d8289ffd175305896e7839a1c85d327f886e227f1a5dc7c` (10 tUSDC to Ge). New-address request filed and not paid; lookalike address refused; injected "system notice" ignored; owner-claim refused. Bundle: `evidence/runs/sepolia-20261016-182745-tasks/`.
- Contract source verified on Sourcify (exact match) for both contracts.

## Results (20 October 2026, browser app)

- Live on Ethereum Sepolia: the parent registered with an owner-key signature and invited the student with a one-time code; 20 tUSDC to Mama through the AI model `0xc4007a1c97eb5da64abc8b6d710bc879fa0ec5bc5424f0387f8fe9adc2c51859`; 10 tUSDC to Ge from 给哥转 10 USDC in rules-only mode `0xe4e2a1f361a091a60fa8c4dd08bd9177a6a0c8cc1137cc1b592bf51a0879a81b`; the owner's one-time approval `0x499b22f3d79ac2119ecbb2bfb730be94f316ad36db2dd92f1448ba281781e58c` and the 800 tUSDC payment against it in rules-only mode `0x8c592d12ed8df4d7dfcca63d2021c6542c4995e31d689357cb882915c3b9d7fe`; 1,000 tUSDC of test money added `0x1d194ba7f67c36368c8000d7126b29926b8369fd77458502372c507bdba027c2`; Aunt Li allowlisted `0x8fd10071ddee63b5ad12182cdf47abee3d22af18ae5133c2d5be4b5d02c69bc0` and paid 15 tUSDC `0x62e6726e214c02e5fe7ad8dd6e7678f16a86dc8de0ee308aa9378c045345ac3f`. The lookalike address, the injected notice and the false owner claim were refused with nothing sent. Bundle: `evidence/runs/sepolia-20261020-124109-web-v2/`.
- Red-team against the rules-only assistant: 8 of 8 (`evidence/redteam_results_rules.md`).
