# Defence glossary (plain language for the on-site defence)

- **Wallet / key**: a wallet is an address on the chain; the key is the secret that signs transactions from it. Shouhu has two keys: the owner's and the agent's.
- **Smart contract**: a small program on the chain that holds the money and refuses any transaction that breaks its rules. Our contract is PolicyWallet.
- **Allowlist**: the list of addresses the agent may pay. Only the owner can change it.
- **Per-transfer cap / 24-hour cap**: the most the agent may send in one payment and in any 24-hour window. Enforced by the contract, not by the AI.
- **One-time approval**: the owner signs "exactly this recipient, this amount, this intent id, once". The agent then executes it and the approval is burned.
- **Intent id**: a fingerprint of the audit-log entry for a decision; it is written into the on-chain event, so each transaction links back to the conversation that caused it.
- **Address poisoning**: a scam where an attacker uses an address that looks like a contact's (same beginning and end). The agent refuses lookalikes.
- **Prompt injection**: instructions hidden in data (a memo, a token name, a pasted message). The agent treats all data as data; no tool can change policy anyway.
- **Provenance rule**: a raw address can only be paid if it appears in the user's own message or in the owner's contacts, so the AI cannot invent or be fed an address.
- **Dry-run**: before sending, the agent simulates the transaction against the chain to see whether it would be refused and why.
- **Testnet**: a public practice chain with free test ether. Our transactions are real on-chain transactions on Ethereum Sepolia; the token has no value.
- **Sourcify / verified source**: the contract's source code is published and matched to the deployed bytecode, so judges can read exactly what runs.
