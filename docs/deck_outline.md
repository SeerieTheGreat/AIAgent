# Deck outline (ten-minute talk)

1. Title: Shouhu 守护, an AI agent that can pay but can never overspend. Team, university, Topic F.
2. The problem: an AI that holds a wallet is one jailbreak away from draining it. Prompt injection, social engineering, key theft.
3. The idea in one picture: three layers that must all agree. Model plans and explains; policy engine decides; contract enforces.
4. Scenario: a family in Shenzhen funds a student abroad. Contacts, caps, allowlist, pause.
5. Demo highlights (video): routine payment with hash; over-cap request approved once by the owner with a separate key, second hash; new address needs approval; lookalike refused; injected "system notice" ignored; "I'm the owner" refused; Chinese nickname payment.
6. The contract: 120 lines, explicit functions, hourly-bucket rolling cap, one-time approvals, intent ids in events. Verified source on the explorer.
7. Security claim and proof: no tool can move funds outside policy; the model cannot change policy; the chain enforces the agent's caps. Red-team table: eight attacks, zero payments, zero leaks. Contract revert hash.
8. What makes it trustworthy: address provenance rule, deterministic decisions with written reasons, audit log joined to chain events by intent id, judge mode anyone can run in one command.
9. Fit for the Chinese market: EVM contract deploys unchanged on FISCO BCOS; stablecoin or tokenised deposit; investor protection by construction.
10. Future work: scheduled payments, conversions, browser-wallet owner signing, token screening, social recovery, ERC-4337 session keys.
