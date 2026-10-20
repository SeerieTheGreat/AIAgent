# Shouhu 守护 — Execution Evidence

**Execution evidence: real on-chain transaction hashes on Ethereum Sepolia**

2026 Shenzhen International FinTech Competition (FinTechathon) · International Track · Topic F: Agent Wallet — Autonomous On-chain Wallet  
Team Shouhu · De La Salle University Manila · Yohann Manuel Miranda (team leader), Aleana Sia, Weihong Chen, Aaron Hester Chong, Jon Austin Lin  
Version 1.0 · 20 October 2026 · read from the chain on 2026-10-20 18:19 UTC+8 (Beijing time)  

**Evidence at a glance**

- **Network and contracts:** Ethereum Sepolia (chain id 11155111). PolicyWallet [`0xb9D959da30680e86E9bF0A287Abee354033a0525`](https://sepolia.etherscan.io/address/0xb9D959da30680e86E9bF0A287Abee354033a0525) and TestUSDC [`0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`](https://sepolia.etherscan.io/address/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931), both source-verified on Sourcify (exact match).
- **46 transactions:** 2 deployments, 11 rule changes, 2 deposits of test money (11,000 tUSDC), 7 one-time owner approvals, **23 payments by the AI agent (16 Tier 1 inside the limits, 7 Tier 2 with the parent’s approval)**, and **3 transactions the contract rejected**.
- **Traceable:** 23 of 23 payments link to the student’s words and the policy decision through the intent id written on-chain (audit log committed in the public repository).
- **Checked:** every wallet transaction passes the proof checks (41 of 41); no payment left the wallet outside policy; balance 5,150 tUSDC.
- **Machine-readable:** `transactions.csv` and `transactions.json` (every hash with its Etherscan link), `proof_checks.json`, `rejections.json`, `verify_all_payments.txt`, `audit_log.jsonl`.

> Every payment the agent made is on-chain, inside the parent’s policy, and traceable to the student’s own words. The contract refused every attempt to go around the policy.

A print version of this report is in [`Shouhu_Execution_Evidence.pdf`](Shouhu_Execution_Evidence.pdf).

**Contents:** [1. How to check any hash](#1-how-to-check-any-hash) · [2. Deployment and setup](#2-deployment-and-setup) · [3. Payments by the AI agent](#3-payments-by-the-ai-agent) · [4. Transactions the contract rejected](#4-transactions-the-contract-rejected) · [5. Rule changes and deposits](#5-rule-changes-and-deposits) · [6. Runs that produced the transactions](#6-runs-that-produced-the-transactions) · [7. Live app screenshots](#7-live-app-screenshots) · [8. Files and other evidence](#8-files-and-other-evidence) · [Appendix. Every transaction](#appendix-every-transaction)

## 1. How to check any hash

1. Open the hash on Etherscan (every hash in this report is a link). Check **Status: Success**, **From** (the agent key `0xe46A…b291` or the owner key `0x4444…9EEF`), **To** the PolicyWallet, and under **Logs** the `Payment` or `ApprovalGranted` event and the tUSDC `Transfer`.
2. Compare the contract source on Sourcify ([PolicyWallet](https://repo.sourcify.dev/11155111/0xb9D959da30680e86E9bF0A287Abee354033a0525), exact match) with `contracts/src/PolicyWallet.sol` in the repository.
3. Read the intent id in the `Payment` event: it is the keccak-256 hash of the policy decision in the audit log (`evidence/runs/sepolia-20261020-181247/audit_log.jsonl`). Recompute it, or run `uv run shouhu-verify --chain sepolia <hash>` to see the student’s words, the decision, its tier and reasons.
4. Ask the live contract directly, with no keys: `uv run shouhu-try --chain sepolia mama 600` answers REJECTED (`ExceedsPerTransferCap`).

Repository: [https://github.com/SeerieTheGreat/AIAgent](https://github.com/SeerieTheGreat/AIAgent). Contract addresses: PolicyWallet [`0xb9D959da30680e86E9bF0A287Abee354033a0525`](https://sepolia.etherscan.io/address/0xb9D959da30680e86E9bF0A287Abee354033a0525), TestUSDC [`0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931`](https://sepolia.etherscan.io/address/0x6b2f3F61DB4e45D07453D58dF2F4eB27C5284931), owner key `0x4444b10a36E88682C63caE89E2ADb561651e9EEF`, agent key `0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291`.

## 2. Deployment and setup

| Time (UTC+8) | What happened | Signed by | Transaction |
|---|---|---|---|
| 10-16 18:15 | deploy TestUSDC (0x6b2f3F61…) | owner key (parent) | [`0x09fc9fe7…fdaee2`](https://sepolia.etherscan.io/tx/0x09fc9fe7db1c0febd1a793932804f9ffb05b4f87d8639ba3f64ce40b56fdaee2) |
| 10-16 18:15 | deploy PolicyWallet (0xb9D959da…) | owner key (parent) | [`0xa858a9a4…f6d9b9`](https://sepolia.etherscan.io/tx/0xa858a9a45f83dc612b81984473310fd179ae6adc4fe40fbe96a086b27ff6d9b9) |
| 10-16 18:15 | AgentUpdated: agent key 0xe46Ab06dF31a8E03BAAe6aA5912b60B10e0Fb291 | owner key (parent) | [`0xa858a9a4…f6d9b9`](https://sepolia.etherscan.io/tx/0xa858a9a45f83dc612b81984473310fd179ae6adc4fe40fbe96a086b27ff6d9b9) |
| 10-16 18:15 | PolicyUpdated: limits 500 tUSDC per transfer, 1000 tUSDC per 24 hours | owner key (parent) | [`0xa858a9a4…f6d9b9`](https://sepolia.etherscan.io/tx/0xa858a9a45f83dc612b81984473310fd179ae6adc4fe40fbe96a086b27ff6d9b9) |
| 10-16 18:16 | Transfer into the wallet (test money minted): 10000 tUSDC into the PolicyWallet | owner key (parent) | [`0x14d03120…e45df2`](https://sepolia.etherscan.io/tx/0x14d0312002dc2603273242ca748357759d98d72afd2ae92d7ef31dce97e45df2) |
| 10-16 18:16 | AllowlistUpdated: Mama added to the allowlist | owner key (parent) | [`0xd1c15e59…1c43dc`](https://sepolia.etherscan.io/tx/0xd1c15e59ae425feb4467ba362afa7b6240a1232bb9b8b455ab9fbd8d121c43dc) |
| 10-16 18:16 | AllowlistUpdated: Ge added to the allowlist | owner key (parent) | [`0xb66b24a2…5de605`](https://sepolia.etherscan.io/tx/0xb66b24a26b7d8d7e5f1f85608767f7543dd8f4e24c93da59354a51e2965de605) |
| 10-16 18:16 | AllowlistUpdated: Landlord Zhang added to the allowlist | owner key (parent) | [`0x9a886db8…6c35fb`](https://sepolia.etherscan.io/tx/0x9a886db8a557953990825e8ec61c4ca5a11044b37cdec81ea3a099427f6c35fb) |
| 10-16 18:16 | AllowlistUpdated: University Bursar added to the allowlist | owner key (parent) | [`0xbce911f4…29483e`](https://sepolia.etherscan.io/tx/0xbce911f4158555460d4e6953de4d43920b3d23538ead83ee760677713f29483e) |
| 10-16 18:17 | AllowlistUpdated: Xiao Wang added to the allowlist | owner key (parent) | [`0x19c6182f…63cd48`](https://sepolia.etherscan.io/tx/0x19c6182fa9a1f2240d26f5e512c5ff07714b51d7d4685c24642c0001e663cd48) |

The PolicyWallet constructor set the agent key and the limits (500 tUSDC per transfer, 1,000 tUSDC per 24 hours) in its deployment transaction; the owner then minted 10,000 tUSDC of test money into the wallet and allowlisted the five default contacts.

## 3. Payments by the AI agent

### 3.1 Tier 1: inside the parent’s limits (16 payments)

Signed by the agent key with `agentTransfer`. The policy engine allowed each one, and the contract re-checked the allowlist, the per-transfer cap and the rolling 24-hour cap.

| Time (UTC+8) | Payment | The student’s words | Transaction |
|---|---|---|---|
| 10-16 18:25 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0xb9ee7295…520074`](https://sepolia.etherscan.io/tx/0xb9ee729554fc96d3c00ce465bd83f2702955a4dc914d1953b602444592520074) |
| 10-16 18:27 | 10 tUSDC to Ge | “给哥转 10 USDC” | [`0xbb784709…a5dc7c`](https://sepolia.etherscan.io/tx/0xbb784709c0dcb2a82d8289ffd175305896e7839a1c85d327f886e227f1a5dc7c) |
| 10-19 15:18 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0x3330ce7a…45ca06`](https://sepolia.etherscan.io/tx/0x3330ce7a8b2fd8d8cca4ecbb914c803385ae73677636e151be0066988545ca06) |
| 10-19 15:20 | 10 tUSDC to Ge | “给哥转 10 USDC” | [`0xe50ff1be…ed42aa`](https://sepolia.etherscan.io/tx/0xe50ff1be2e6638fa55e1d87922f0e3dce37195fc2b6821e66195b26651ed42aa) |
| 10-20 01:37 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0xe21b79ff…b5363f`](https://sepolia.etherscan.io/tx/0xe21b79ff273815d9c72cd1f57185024993a1747894abeba8367ae12419b5363f) |
| 10-20 01:42 | 10 tUSDC to Ge | “给哥转 10 USDC” | [`0x0352e2f7…3cc6c7`](https://sepolia.etherscan.io/tx/0x0352e2f70339d7045fbeaef5fa7cfd527122af87449c5ce84434dbcef23cc6c7) |
| 10-20 06:51 | 15 tUSDC to Aunt Li 李阿姨 | “给李阿姨转 15 USDC” | [`0x4830a81f…c8c332`](https://sepolia.etherscan.io/tx/0x4830a81f1e1d1e8e872ee4964a1b8cbc52fb7593f3ec87726a6afc67e1c8c332) |
| 10-20 07:00 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0x9d9d76a5…247ffb`](https://sepolia.etherscan.io/tx/0x9d9d76a59ac88348e32915235b80866cf7e28457a38a9cbe73f26ab287247ffb) |
| 10-20 07:02 | 15 tUSDC to Aunt Li 李阿姨 | “给李阿姨转 15 USDC” | [`0xb8a35a26…e23213`](https://sepolia.etherscan.io/tx/0xb8a35a263a31ff7c7e4a1e251442f6068c504ede4e4f21281f19cae1e4e23213) |
| 10-20 07:05 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0x2f126f72…af39ce`](https://sepolia.etherscan.io/tx/0x2f126f72298d101555f5089a8504141fbf39be570c895c2459b32f1ab6af39ce) |
| 10-20 07:10 | 15 tUSDC to Aunt Li 李阿姨 | “给李阿姨转 15 USDC” | [`0x53f802b5…d3c0a3`](https://sepolia.etherscan.io/tx/0x53f802b50f4715201f67b1f1f711b4f6909571aeb98381fc8756b90e9dd3c0a3) |
| 10-20 12:19 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0xc4007a1c…c51859`](https://sepolia.etherscan.io/tx/0xc4007a1c97eb5da64abc8b6d710bc879fa0ec5bc5424f0387f8fe9adc2c51859) |
| 10-20 12:20 | 10 tUSDC to Ge | “给哥转 10 USDC” | [`0xe4e2a1f3…79a81b`](https://sepolia.etherscan.io/tx/0xe4e2a1f361a091a60fa8c4dd08bd9177a6a0c8cc1137cc1b592bf51a0879a81b) |
| 10-20 12:28 | 15 tUSDC to Aunt Li 李阿姨 | “给李阿姨转 15 USDC” | [`0x62e6726e…45ac3f`](https://sepolia.etherscan.io/tx/0x62e6726e214c02e5fe7ad8dd6e7678f16a86dc8de0ee308aa9378c045345ac3f) |
| 10-20 17:53 | 20 tUSDC to Mama | “Send 20 USDC to Mama.” | [`0xe2dbb06c…67e502`](https://sepolia.etherscan.io/tx/0xe2dbb06cd1d699ba135ef11232c766f5a22c440b3542abc9b9a17eb0bd67e502) |
| 10-20 17:55 | 10 tUSDC to Ge | “给哥转 10 USDC” | [`0x5f3bbedc…8a517d`](https://sepolia.etherscan.io/tx/0x5f3bbedca4e630015ba51820660304dc5c5f47badde580cd7ec71504178a517d) |

### 3.2 Tier 2: with the parent’s one-time approval (7 payments)

Each request went above the 500 tUSDC per-transfer cap, so the policy engine filed it for the parent. The parent approved exactly that recipient and amount once with the owner key (`approveOnce`), and the agent then executed it with `agentTransferWithApproval`, which marks the approval used.

| Time (UTC+8) | Payment | The student’s words → reason for approval | Parent’s approval | Payment |
|---|---|---|---|---|
| 10-16 18:26 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0xd4961bcc…4b0509`](https://sepolia.etherscan.io/tx/0xd4961bcc9dd7fc245bb69baceb04673e2c7095877499c675fac27dbacc4b0509) | [`0x838aee65…a38cfc`](https://sepolia.etherscan.io/tx/0x838aee659579417aa92716e84790bb07158e68f6fbb77b11fb20936e46a38cfc) |
| 10-19 15:19 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x16f6267e…dc96d1`](https://sepolia.etherscan.io/tx/0x16f6267ee9394bfe52cee8c77d7d48ca76253609482abeb1b197ef8842dc96d1) | [`0x4d6b84ae…87ab48`](https://sepolia.etherscan.io/tx/0x4d6b84aec33229f1d50ec07da161d54702c546773048b7289f6e6e451187ab48) |
| 10-20 01:39 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x18fa60fe…aafaa2`](https://sepolia.etherscan.io/tx/0x18fa60fe57de1bb73d5b7ddac8c9e4b6c542e0320c57fae46e2696370faafaa2) | [`0xf729b1d8…f5aa68`](https://sepolia.etherscan.io/tx/0xf729b1d85a840532167add73cacb484ecbeebfde67ad91a2d581a6c37bf5aa68) |
| 10-20 07:01 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x4a0f6659…c18c27`](https://sepolia.etherscan.io/tx/0x4a0f66598463d333080aa76f5c24239731145431e898f27adca21be86cc18c27) | [`0xc4805f36…e8b8ba`](https://sepolia.etherscan.io/tx/0xc4805f36ca0d8e736662b84097f3fb0e5f2483c6e80b89deadb84c53e8e8b8ba) |
| 10-20 07:08 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x8d783a7b…d636a7`](https://sepolia.etherscan.io/tx/0x8d783a7b439c3bc83a5ce1ab23ec1e47b7412c5b1533708bf25856ce4cd636a7) | [`0xdec61abe…ab1377`](https://sepolia.etherscan.io/tx/0xdec61abe7b51de693b79f497e3c677fce111c299a19eec04beeb0ae601ab1377) |
| 10-20 12:23 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x499b22f3…81e58c`](https://sepolia.etherscan.io/tx/0x499b22f3d79ac2119ecbb2bfb730be94f316ad36db2dd92f1448ba281781e58c) | [`0x8c592d12…b9d7fe`](https://sepolia.etherscan.io/tx/0x8c592d12ed8df4d7dfcca63d2021c6542c4995e31d689357cb882915c3b9d7fe) |
| 10-20 17:54 | 800 tUSDC to Landlord Zhang | “Pay the landlord 800 USDC for the apartment deposit.” → 800 tUSDC exceeds the per-transfer cap of 500 tUSDC | [`0x7da07536…2a3a51`](https://sepolia.etherscan.io/tx/0x7da075360343b7c5ad0846376880123248ecac27c184ae0261bf6c777c2a3a51) | [`0x3b577f89…6d282e`](https://sepolia.etherscan.io/tx/0x3b577f89b3b46e565385ea3655036d2084b7108b357d5c26c39de47d136d282e) |

The approval and the payment share one intent id, and the same id identifies the policy decision in the audit log. A second attempt with the same approval reverts with `ApprovalUsed` (contract test `test_approvalFlow`).

## 4. Transactions the contract rejected

To show what happens if the software above the contract is bypassed or compromised, three transactions were sent directly with the agent key on 20 October 2026, skipping the policy engine and the app’s dry run. The contract rejected all three; nothing moved, and the wallet balance stayed at 5,980 tUSDC.

| Attempt by the agent key | Rejected with | Status | Transaction |
|---|---|---|---|
| 600 tUSDC to Mama (per-transfer cap is 500) | `ExceedsPerTransferCap(amount=600000000, cap=500000000)` | Failed (reverted) | [`0xd1a63517…4c2319`](https://sepolia.etherscan.io/tx/0xd1a63517dcae701846483ca8d4b65192f62400e44be3754166f48d7aae4c2319) |
| 1 tUSDC to the scam address from attack A1 (not allowlisted) | `NotAllowlisted(to=0x9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f9f)` | Failed (reverted) | [`0x6dbe08db…d8b31f`](https://sepolia.etherscan.io/tx/0x6dbe08db28f00badd416618c511e0105e187a994627657fc36ad64ea6fd8b31f) |
| setPolicy(10,000 / 100,000 tUSDC) signed by the agent key (only the owner may change limits) | `NotOwner()` | Failed (reverted) | [`0x5511583e…9b046a`](https://sepolia.etherscan.io/tx/0x5511583e2dbcf295efc7da7aaca70dcf50ea8d5dcf2eee79bd0bdff6459b046a) |

Each revert reason was confirmed by replaying the same call against the chain state of the block before (for example block 11,954,297). Etherscan shows the three transactions as failed; because the contract is verified on Sourcify rather than Etherscan, Etherscan may show the custom error only as raw data, which `shouhu-verify` and the replay decode.

- **Over the per-transfer cap:** the agent cannot pay more than 500 tUSDC at once, even to an allowlisted contact.
- **Not on the allowlist:** the agent cannot pay the scammer’s address from red-team attack A1.
- **Not the owner:** the agent key cannot raise its own limits; only the owner key can call `setPolicy`.

## 5. Rule changes and deposits

| Time (UTC+8) | What happened | Signed by | Transaction |
|---|---|---|---|
| 10-20 06:49 | Aunt Li 李阿姨 added to the allowlist | owner key (parent) | [`0x972f309e…debbbc`](https://sepolia.etherscan.io/tx/0x972f309e9a86e370d9e202fa9b6df604898ffb7a8921e9cac6e86b6a4adebbbc) |
| 10-20 07:02 | Aunt Li 李阿姨 added to the allowlist | owner key (parent) | [`0xb24f3b4a…207ef1`](https://sepolia.etherscan.io/tx/0xb24f3b4a34843475471046319085ae384727f16f6fa7eff0a9df36cc7a207ef1) |
| 10-20 07:09 | Aunt Li 李阿姨 added to the allowlist | owner key (parent) | [`0xabdbbde0…6cd419`](https://sepolia.etherscan.io/tx/0xabdbbde096a8f9589bea8a8229605b2ad6dfb19ded2f65c7779c4a33356cd419) |
| 10-20 12:22 | 1000 tUSDC into the PolicyWallet | owner key (parent) | [`0x1d194ba7…a027c2`](https://sepolia.etherscan.io/tx/0x1d194ba7f67c36368c8000d7126b29926b8369fd77458502372c507bdba027c2) |
| 10-20 12:27 | Aunt Li 李阿姨 added to the allowlist | owner key (parent) | [`0x8fd10071…c69bc0`](https://sepolia.etherscan.io/tx/0x8fd10071ddee63b5ad12182cdf47abee3d22af18ae5133c2d5be4b5d02c69bc0) |

Aunt Li 李阿姨 was registered as a contact from the owner console in several runs of the web app; each registration is an allowlist transaction signed by the owner key, and she is allowlisted once on-chain. The 1,000 tUSDC deposit is test money added from the owner console.

## 6. Runs that produced the transactions

| When (UTC+8) | Run | Payments |
|---|---|---|
| 16 Oct 18:25–18:27 | Judge mode on Sepolia: the eight scripted tasks with the AI model (terminal); owner approval in a separate process. Bundle `evidence/runs/sepolia-20261016-182745-tasks/` | 3 (2 Tier 1, 1 Tier 2) |
| 19 Oct 15:18–15:20 | Demo-guide test: terminal chat on Sepolia with the owner command in a second terminal | 3 (2 Tier 1, 1 Tier 2) |
| 20 Oct 01:37–07:10 | Browser app (student chat and owner console) on Sepolia, including contact registration (Aunt Li) | 10 (7 Tier 1, 3 Tier 2) |
| 20 Oct 12:19–12:28 | Browser app v2: parent registration with the owner key, student invite, AI model and rules-only assistant, owner console approval, test money. Bundle `evidence/runs/sepolia-20261020-124109-web-v2/` | 4 (3 Tier 1, 1 Tier 2) |
| 20 Oct 17:07–17:08 | Contract rejection tests with the agent key (section 4) | 0 (3 rejected) |
| 20 Oct 17:52–17:55 | Demo video, recorded live: parent registration, student invite, AI model and rules-only assistant, the parent’s approval in the owner console. Bundle `evidence/runs/sepolia-20261020-181247/` | 3 (2 Tier 1, 1 Tier 2) |

Every payment’s decision is in the committed audit log; each run used its own session id (`demo-20261016-182524`, `web-20261020-121856` and others), shown in `transactions.csv`.

## 7. Live app screenshots

![screenshot](img/web_transactions_sepolia.jpg)

*The Transactions page of the live app on 20 October 2026 at 12:23 UTC+8 (before the last payment of that run): every event of the wallet read from the chain, with the signing key and a proof link for each.*

![screenshot](img/web_receipt_sepolia.jpg)

*The proof page for the 800 tUSDC Tier 2 payment [`0x8c592d12…b9d7fe`](https://sepolia.etherscan.io/tx/0x8c592d12ed8df4d7dfcca63d2021c6542c4995e31d689357cb882915c3b9d7fe): every check passed, with the receipt number SH-11952885-42 and a link to the parent’s one-time approval.*

## 8. Files and other evidence

| File (in this folder) | Contents |
|---|---|
| `transactions.csv`, `transactions.json` | All 48 records (46 transactions): time, block, event, amount, tier, signer, status, full hash, Etherscan link, intent id, the student’s words, the decision and its reasons |
| `proof_checks.json` | For every transaction, the checks of the app’s proof page (status, signer, target contract, token movement, tier, intent id to decision); contract creations and the three rejected transactions are expected to fail the payment checks |
| `rejections.json` | The three rejected transactions with the decoded revert reason and the replay confirmation |
| `verify_all_payments.txt` | `shouhu-verify --chain sepolia --all` on a fresh copy of the public repository: each payment, its events and its audit entry; then the three rejected transactions |
| `audit_log.jsonl` | The audit log behind the payments (the same file as `evidence/runs/sepolia-20261020-181247/audit_log.jsonl`) |

The same files are public in the repository under `evidence/onchain/`. Other evidence there: the red-team results (`evidence/redteam_results.md`, `evidence/redteam_results_rules.md`, 8 of 8 in both modes), the scripted-task bundles with transcripts (`evidence/runs/`), and the fresh-copy test logs (`docs/test_results/`).

## Appendix. Every transaction

All transactions of the deployment, oldest first, with full hashes. Each opens on Etherscan.

| Time | Transaction | Key | Status | Hash |
|---|---|---|---|---|
| 10-16 18:15 | deploy TestUSDC | owner key | Success | [`0x09fc9fe7db1c0febd1a793932804f9ffb05b4f87d8639ba3f64ce40b56fdaee2`](https://sepolia.etherscan.io/tx/0x09fc9fe7db1c0febd1a793932804f9ffb05b4f87d8639ba3f64ce40b56fdaee2) |
| 10-16 18:15 | deploy PolicyWallet (sets the agent key and the limits) | owner key | Success | [`0xa858a9a45f83dc612b81984473310fd179ae6adc4fe40fbe96a086b27ff6d9b9`](https://sepolia.etherscan.io/tx/0xa858a9a45f83dc612b81984473310fd179ae6adc4fe40fbe96a086b27ff6d9b9) |
| 10-16 18:16 | 10000 tUSDC into the PolicyWallet | owner key | Success | [`0x14d0312002dc2603273242ca748357759d98d72afd2ae92d7ef31dce97e45df2`](https://sepolia.etherscan.io/tx/0x14d0312002dc2603273242ca748357759d98d72afd2ae92d7ef31dce97e45df2) |
| 10-16 18:16 | Mama added to the allowlist | owner key | Success | [`0xd1c15e59ae425feb4467ba362afa7b6240a1232bb9b8b455ab9fbd8d121c43dc`](https://sepolia.etherscan.io/tx/0xd1c15e59ae425feb4467ba362afa7b6240a1232bb9b8b455ab9fbd8d121c43dc) |
| 10-16 18:16 | Ge added to the allowlist | owner key | Success | [`0xb66b24a26b7d8d7e5f1f85608767f7543dd8f4e24c93da59354a51e2965de605`](https://sepolia.etherscan.io/tx/0xb66b24a26b7d8d7e5f1f85608767f7543dd8f4e24c93da59354a51e2965de605) |
| 10-16 18:16 | Landlord Zhang added to the allowlist | owner key | Success | [`0x9a886db8a557953990825e8ec61c4ca5a11044b37cdec81ea3a099427f6c35fb`](https://sepolia.etherscan.io/tx/0x9a886db8a557953990825e8ec61c4ca5a11044b37cdec81ea3a099427f6c35fb) |
| 10-16 18:16 | University Bursar added to the allowlist | owner key | Success | [`0xbce911f4158555460d4e6953de4d43920b3d23538ead83ee760677713f29483e`](https://sepolia.etherscan.io/tx/0xbce911f4158555460d4e6953de4d43920b3d23538ead83ee760677713f29483e) |
| 10-16 18:17 | Xiao Wang added to the allowlist | owner key | Success | [`0x19c6182fa9a1f2240d26f5e512c5ff07714b51d7d4685c24642c0001e663cd48`](https://sepolia.etherscan.io/tx/0x19c6182fa9a1f2240d26f5e512c5ff07714b51d7d4685c24642c0001e663cd48) |
| 10-16 18:25 | 20 tUSDC to Mama | agent key | Success | [`0xb9ee729554fc96d3c00ce465bd83f2702955a4dc914d1953b602444592520074`](https://sepolia.etherscan.io/tx/0xb9ee729554fc96d3c00ce465bd83f2702955a4dc914d1953b602444592520074) |
| 10-16 18:26 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0xd4961bcc9dd7fc245bb69baceb04673e2c7095877499c675fac27dbacc4b0509`](https://sepolia.etherscan.io/tx/0xd4961bcc9dd7fc245bb69baceb04673e2c7095877499c675fac27dbacc4b0509) |
| 10-16 18:26 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0x838aee659579417aa92716e84790bb07158e68f6fbb77b11fb20936e46a38cfc`](https://sepolia.etherscan.io/tx/0x838aee659579417aa92716e84790bb07158e68f6fbb77b11fb20936e46a38cfc) |
| 10-16 18:27 | 10 tUSDC to Ge | agent key | Success | [`0xbb784709c0dcb2a82d8289ffd175305896e7839a1c85d327f886e227f1a5dc7c`](https://sepolia.etherscan.io/tx/0xbb784709c0dcb2a82d8289ffd175305896e7839a1c85d327f886e227f1a5dc7c) |
| 10-19 15:18 | 20 tUSDC to Mama | agent key | Success | [`0x3330ce7a8b2fd8d8cca4ecbb914c803385ae73677636e151be0066988545ca06`](https://sepolia.etherscan.io/tx/0x3330ce7a8b2fd8d8cca4ecbb914c803385ae73677636e151be0066988545ca06) |
| 10-19 15:19 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x16f6267ee9394bfe52cee8c77d7d48ca76253609482abeb1b197ef8842dc96d1`](https://sepolia.etherscan.io/tx/0x16f6267ee9394bfe52cee8c77d7d48ca76253609482abeb1b197ef8842dc96d1) |
| 10-19 15:19 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0x4d6b84aec33229f1d50ec07da161d54702c546773048b7289f6e6e451187ab48`](https://sepolia.etherscan.io/tx/0x4d6b84aec33229f1d50ec07da161d54702c546773048b7289f6e6e451187ab48) |
| 10-19 15:20 | 10 tUSDC to Ge | agent key | Success | [`0xe50ff1be2e6638fa55e1d87922f0e3dce37195fc2b6821e66195b26651ed42aa`](https://sepolia.etherscan.io/tx/0xe50ff1be2e6638fa55e1d87922f0e3dce37195fc2b6821e66195b26651ed42aa) |
| 10-20 01:37 | 20 tUSDC to Mama | agent key | Success | [`0xe21b79ff273815d9c72cd1f57185024993a1747894abeba8367ae12419b5363f`](https://sepolia.etherscan.io/tx/0xe21b79ff273815d9c72cd1f57185024993a1747894abeba8367ae12419b5363f) |
| 10-20 01:39 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x18fa60fe57de1bb73d5b7ddac8c9e4b6c542e0320c57fae46e2696370faafaa2`](https://sepolia.etherscan.io/tx/0x18fa60fe57de1bb73d5b7ddac8c9e4b6c542e0320c57fae46e2696370faafaa2) |
| 10-20 01:39 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0xf729b1d85a840532167add73cacb484ecbeebfde67ad91a2d581a6c37bf5aa68`](https://sepolia.etherscan.io/tx/0xf729b1d85a840532167add73cacb484ecbeebfde67ad91a2d581a6c37bf5aa68) |
| 10-20 01:42 | 10 tUSDC to Ge | agent key | Success | [`0x0352e2f70339d7045fbeaef5fa7cfd527122af87449c5ce84434dbcef23cc6c7`](https://sepolia.etherscan.io/tx/0x0352e2f70339d7045fbeaef5fa7cfd527122af87449c5ce84434dbcef23cc6c7) |
| 10-20 06:49 | Aunt Li 李阿姨 added to the allowlist | owner key | Success | [`0x972f309e9a86e370d9e202fa9b6df604898ffb7a8921e9cac6e86b6a4adebbbc`](https://sepolia.etherscan.io/tx/0x972f309e9a86e370d9e202fa9b6df604898ffb7a8921e9cac6e86b6a4adebbbc) |
| 10-20 06:51 | 15 tUSDC to Aunt Li 李阿姨 | agent key | Success | [`0x4830a81f1e1d1e8e872ee4964a1b8cbc52fb7593f3ec87726a6afc67e1c8c332`](https://sepolia.etherscan.io/tx/0x4830a81f1e1d1e8e872ee4964a1b8cbc52fb7593f3ec87726a6afc67e1c8c332) |
| 10-20 07:00 | 20 tUSDC to Mama | agent key | Success | [`0x9d9d76a59ac88348e32915235b80866cf7e28457a38a9cbe73f26ab287247ffb`](https://sepolia.etherscan.io/tx/0x9d9d76a59ac88348e32915235b80866cf7e28457a38a9cbe73f26ab287247ffb) |
| 10-20 07:01 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x4a0f66598463d333080aa76f5c24239731145431e898f27adca21be86cc18c27`](https://sepolia.etherscan.io/tx/0x4a0f66598463d333080aa76f5c24239731145431e898f27adca21be86cc18c27) |
| 10-20 07:01 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0xc4805f36ca0d8e736662b84097f3fb0e5f2483c6e80b89deadb84c53e8e8b8ba`](https://sepolia.etherscan.io/tx/0xc4805f36ca0d8e736662b84097f3fb0e5f2483c6e80b89deadb84c53e8e8b8ba) |
| 10-20 07:02 | Aunt Li 李阿姨 added to the allowlist | owner key | Success | [`0xb24f3b4a34843475471046319085ae384727f16f6fa7eff0a9df36cc7a207ef1`](https://sepolia.etherscan.io/tx/0xb24f3b4a34843475471046319085ae384727f16f6fa7eff0a9df36cc7a207ef1) |
| 10-20 07:02 | 15 tUSDC to Aunt Li 李阿姨 | agent key | Success | [`0xb8a35a263a31ff7c7e4a1e251442f6068c504ede4e4f21281f19cae1e4e23213`](https://sepolia.etherscan.io/tx/0xb8a35a263a31ff7c7e4a1e251442f6068c504ede4e4f21281f19cae1e4e23213) |
| 10-20 07:05 | 20 tUSDC to Mama | agent key | Success | [`0x2f126f72298d101555f5089a8504141fbf39be570c895c2459b32f1ab6af39ce`](https://sepolia.etherscan.io/tx/0x2f126f72298d101555f5089a8504141fbf39be570c895c2459b32f1ab6af39ce) |
| 10-20 07:07 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x8d783a7b439c3bc83a5ce1ab23ec1e47b7412c5b1533708bf25856ce4cd636a7`](https://sepolia.etherscan.io/tx/0x8d783a7b439c3bc83a5ce1ab23ec1e47b7412c5b1533708bf25856ce4cd636a7) |
| 10-20 07:08 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0xdec61abe7b51de693b79f497e3c677fce111c299a19eec04beeb0ae601ab1377`](https://sepolia.etherscan.io/tx/0xdec61abe7b51de693b79f497e3c677fce111c299a19eec04beeb0ae601ab1377) |
| 10-20 07:09 | Aunt Li 李阿姨 added to the allowlist | owner key | Success | [`0xabdbbde096a8f9589bea8a8229605b2ad6dfb19ded2f65c7779c4a33356cd419`](https://sepolia.etherscan.io/tx/0xabdbbde096a8f9589bea8a8229605b2ad6dfb19ded2f65c7779c4a33356cd419) |
| 10-20 07:10 | 15 tUSDC to Aunt Li 李阿姨 | agent key | Success | [`0x53f802b50f4715201f67b1f1f711b4f6909571aeb98381fc8756b90e9dd3c0a3`](https://sepolia.etherscan.io/tx/0x53f802b50f4715201f67b1f1f711b4f6909571aeb98381fc8756b90e9dd3c0a3) |
| 10-20 12:19 | 20 tUSDC to Mama | agent key | Success | [`0xc4007a1c97eb5da64abc8b6d710bc879fa0ec5bc5424f0387f8fe9adc2c51859`](https://sepolia.etherscan.io/tx/0xc4007a1c97eb5da64abc8b6d710bc879fa0ec5bc5424f0387f8fe9adc2c51859) |
| 10-20 12:20 | 10 tUSDC to Ge | agent key | Success | [`0xe4e2a1f361a091a60fa8c4dd08bd9177a6a0c8cc1137cc1b592bf51a0879a81b`](https://sepolia.etherscan.io/tx/0xe4e2a1f361a091a60fa8c4dd08bd9177a6a0c8cc1137cc1b592bf51a0879a81b) |
| 10-20 12:21 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x499b22f3d79ac2119ecbb2bfb730be94f316ad36db2dd92f1448ba281781e58c`](https://sepolia.etherscan.io/tx/0x499b22f3d79ac2119ecbb2bfb730be94f316ad36db2dd92f1448ba281781e58c) |
| 10-20 12:22 | 1000 tUSDC into the PolicyWallet | owner key | Success | [`0x1d194ba7f67c36368c8000d7126b29926b8369fd77458502372c507bdba027c2`](https://sepolia.etherscan.io/tx/0x1d194ba7f67c36368c8000d7126b29926b8369fd77458502372c507bdba027c2) |
| 10-20 12:23 | 800 tUSDC to Landlord Zhang | agent key | Success | [`0x8c592d12ed8df4d7dfcca63d2021c6542c4995e31d689357cb882915c3b9d7fe`](https://sepolia.etherscan.io/tx/0x8c592d12ed8df4d7dfcca63d2021c6542c4995e31d689357cb882915c3b9d7fe) |
| 10-20 12:27 | Aunt Li 李阿姨 added to the allowlist | owner key | Success | [`0x8fd10071ddee63b5ad12182cdf47abee3d22af18ae5133c2d5be4b5d02c69bc0`](https://sepolia.etherscan.io/tx/0x8fd10071ddee63b5ad12182cdf47abee3d22af18ae5133c2d5be4b5d02c69bc0) |
| 10-20 12:28 | 15 tUSDC to Aunt Li 李阿姨 | agent key | Success | [`0x62e6726e214c02e5fe7ad8dd6e7678f16a86dc8de0ee308aa9378c045345ac3f`](https://sepolia.etherscan.io/tx/0x62e6726e214c02e5fe7ad8dd6e7678f16a86dc8de0ee308aa9378c045345ac3f) |
| 10-20 17:07 | Rejected: 600 tUSDC to Mama (over the cap) | agent key | Failed | [`0xd1a63517dcae701846483ca8d4b65192f62400e44be3754166f48d7aae4c2319`](https://sepolia.etherscan.io/tx/0xd1a63517dcae701846483ca8d4b65192f62400e44be3754166f48d7aae4c2319) |
| 10-20 17:08 | Rejected: 1 tUSDC to the A1 scam address | agent key | Failed | [`0x6dbe08db28f00badd416618c511e0105e187a994627657fc36ad64ea6fd8b31f`](https://sepolia.etherscan.io/tx/0x6dbe08db28f00badd416618c511e0105e187a994627657fc36ad64ea6fd8b31f) |
| 10-20 17:08 | Rejected: agent key calls setPolicy | agent key | Failed | [`0x5511583e2dbcf295efc7da7aaca70dcf50ea8d5dcf2eee79bd0bdff6459b046a`](https://sepolia.etherscan.io/tx/0x5511583e2dbcf295efc7da7aaca70dcf50ea8d5dcf2eee79bd0bdff6459b046a) |
| 10-20 17:53 | 20 tUSDC to Mama | agent key | Success | [`0xe2dbb06cd1d699ba135ef11232c766f5a22c440b3542abc9b9a17eb0bd67e502`](https://sepolia.etherscan.io/tx/0xe2dbb06cd1d699ba135ef11232c766f5a22c440b3542abc9b9a17eb0bd67e502) |
| 10-20 17:54 | approve 800 tUSDC to Landlord Zhang once | owner key | Success | [`0x7da075360343b7c5ad0846376880123248ecac27c184ae0261bf6c777c2a3a51`](https://sepolia.etherscan.io/tx/0x7da075360343b7c5ad0846376880123248ecac27c184ae0261bf6c777c2a3a51) |
| 10-20 17:54 | 800 tUSDC to Landlord Zhang · memo: Apartment deposit | agent key | Success | [`0x3b577f89b3b46e565385ea3655036d2084b7108b357d5c26c39de47d136d282e`](https://sepolia.etherscan.io/tx/0x3b577f89b3b46e565385ea3655036d2084b7108b357d5c26c39de47d136d282e) |
| 10-20 17:55 | 10 tUSDC to Ge | agent key | Success | [`0x5f3bbedca4e630015ba51820660304dc5c5f47badde580cd7ec71504178a517d`](https://sepolia.etherscan.io/tx/0x5f3bbedca4e630015ba51820660304dc5c5f47badde580cd7ec71504178a517d) |

---

tUSDC is a test token with no monetary value; all transactions are on the Ethereum Sepolia test network.
