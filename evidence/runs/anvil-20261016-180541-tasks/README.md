# Shouhu evidence bundle (anvil)

- PolicyWallet: `0xb9D959da30680e86E9bF0A287Abee354033a0525`
- TestUSDC: `0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`
- Owner: `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`  Agent: `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`
- Policy now: per-transfer cap 500 tUSDC, 24h cap 1000 tUSDC, paused False
- Wallet balance now: 9170 tUSDC

## Payments (newest first)

| block | to | amount | via owner approval | intent id | tx |
|---|---|---|---|---|---|
| 12 | Ge | 10 tUSDC | False | 0x783edfe264... | 0xc14615ada630d2623577e963f9eb4f1e89f0ef406f9184d31acf0610c556f9da |
| 11 | Landlord Zhang | 800 tUSDC | True | 0xb6563ee7ed... | 0x0006772bfb3050f24c4b7d271ab04d01af472142183f8bfa90107687b8d6143d |
| 9 | Mama | 20 tUSDC | False | 0x663b6b3eb8... | 0xf43c5603a3afcc72ced33aef761fdef5c4d416958416310725ebadceb0638426 |

Every intent id above is the hash of an entry in `audit_log.jsonl` (event `decision`), which records the user's request, the policy decision and its reasons.
