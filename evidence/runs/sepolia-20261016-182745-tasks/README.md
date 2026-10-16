# Shouhu evidence bundle (sepolia)

- PolicyWallet: `0xb9D959da30680e86E9bF0A287Abee354033a0525` (https://sepolia.etherscan.io/address/0xb9D959da30680e86E9bF0A287Abee354033a0525)
- TestUSDC: `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`
- Owner: `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`  Agent: `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`
- Policy now: per-transfer cap 500 tUSDC, 24h cap 1000 tUSDC, paused False
- Wallet balance now: 9170 tUSDC

## Payments (newest first)

| block | to | amount | via owner approval | intent id | tx |
|---|---|---|---|---|---|
| 11926763 | Ge | 10 tUSDC | False | 0x202eb83d14... | [0xbb784709c0...](https://sepolia.etherscan.io/tx/0xbb784709c0dcb2a82d8289ffd175305896e7839a1c85d327f886e227f1a5dc7c) |
| 11926758 | Landlord Zhang | 800 tUSDC | True | 0x7f0b506529... | [0x838aee6595...](https://sepolia.etherscan.io/tx/0x838aee659579417aa92716e84790bb07158e68f6fbb77b11fb20936e46a38cfc) |
| 11926755 | Mama | 20 tUSDC | False | 0xb53ae1d6ac... | [0xb9ee729554...](https://sepolia.etherscan.io/tx/0xb9ee729554fc96d3c00ce465bd83f2702955a4dc914d1953b602444592520074) |

Every intent id above is the hash of an entry in `audit_log.jsonl` (event `decision`), which records the user's request, the policy decision and its reasons.
