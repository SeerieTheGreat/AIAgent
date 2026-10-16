#!/usr/bin/env bash
# Verify the deployed contracts on Sourcify (no API key needed) so the judges can read the source on the explorer.
# Usage: scripts/verify_sourcify.sh [sepolia|base-sepolia]
set -euo pipefail
CHAIN="${1:-sepolia}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEP="$ROOT/deployments/$CHAIN.json"
[ -f "$DEP" ] || { echo "no deployment file $DEP"; exit 1; }
TOKEN=$(python3 -c "import json;print(json.load(open('$DEP'))['token'])")
WALLET=$(python3 -c "import json;print(json.load(open('$DEP'))['wallet'])")
AGENT=$(python3 -c "import json;print(json.load(open('$DEP'))['agent'])")
case "$CHAIN" in
  sepolia) CHAIN_ID=11155111 ;;
  base-sepolia) CHAIN_ID=84532 ;;
  *) echo "unsupported chain $CHAIN"; exit 1 ;;
esac
PER_CAP=$(python3 -c "from shouhu import config; print(config.DEFAULT_PER_TRANSFER_CAP)" 2>/dev/null || echo 500000000)
ROLL_CAP=$(python3 -c "from shouhu import config; print(config.DEFAULT_ROLLING_CAP)" 2>/dev/null || echo 1000000000)
export PATH="$HOME/.foundry/bin:$PATH"
cd "$ROOT/contracts"
echo "verifying TestUSDC $TOKEN"
forge verify-contract --chain-id "$CHAIN_ID" --verifier sourcify "$TOKEN" src/TestUSDC.sol:TestUSDC || true
ARGS=$(cast abi-encode "constructor(address,address,uint256,uint256)" "$AGENT" "$TOKEN" "$PER_CAP" "$ROLL_CAP")
echo "verifying PolicyWallet $WALLET"
forge verify-contract --chain-id "$CHAIN_ID" --verifier sourcify --constructor-args "$ARGS" "$WALLET" src/PolicyWallet.sol:PolicyWallet || true
echo "check: https://repo.sourcify.dev/contracts/full_match/$CHAIN_ID/$WALLET/"
