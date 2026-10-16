# Shouhu evidence bundle (anvil)

- PolicyWallet: `0xb9D959da30680e86E9bF0A287Abee354033a0525`
- TestUSDC: `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`
- Owner: `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`  Agent: `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`
- Policy now: per-transfer cap 500 tUSDC, 24h cap 1000 tUSDC, paused False
- Wallet balance now: 9170 tUSDC

## Payments (newest first)

| block | to | amount | via owner approval | intent id | tx |
|---|---|---|---|---|---|
| 12 | Ge | 10 tUSDC | False | 0x26017c48bb... | 0x97274982ec53f4e52246216a7ad1e8b1d6ef5f796661be500c09376b64113fb6 |
| 11 | Landlord Zhang | 800 tUSDC | True | 0x576eb76b93... | 0x9e8d71a33fb06fef4c9f898868c85c8ccc4c12f5ba1de8b010906a091822e044 |
| 9 | Mama | 20 tUSDC | False | 0xc461166b86... | 0x85ddd6d86cb68b81a30830b49dd83715a59b59097ec2d6379b40873010b3f903 |

Every intent id above is the hash of an entry in `audit_log.jsonl` (event `decision`), which records the user's request, the policy decision and its reasons.
