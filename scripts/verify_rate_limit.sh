#!/usr/bin/env bash
# Rate-limit smoke test for v1.3 backend hardening.
# Fires (limit + 5) requests to /api/scripts and expects at least one 429.
#
# Usage:
#   ./scripts/verify_rate_limit.sh                          # local default
#   ./scripts/verify_rate_limit.sh http://127.0.0.1:8000 10   # custom base + expected limit
#
# For a reliable local test, start the server with a low limit:
#   RATE_LIMIT_PER_MINUTE=10 uvicorn main:app --port 8000

set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"
LIMIT="${2:-120}"
BASE="${BASE%/}"

REQUESTS=$((LIMIT + 5))
echo "=== Rate limit test: $BASE (limit=$LIMIT, firing $REQUESTS requests) ==="

ok=0
blocked=0

for i in $(seq 1 "$REQUESTS"); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/scripts" || echo "000")
  if [[ "$code" == "200" ]]; then
    ok=$((ok + 1))
  elif [[ "$code" == "429" ]]; then
    blocked=$((blocked + 1))
  else
    echo "[FAIL] Unexpected status $code on request $i"
    exit 1
  fi
done

echo "  200 responses: $ok"
echo "  429 responses: $blocked"

if [[ "$blocked" -ge 1 ]]; then
  echo "[OK] Rate limiter returned 429"
else
  echo "[FAIL] Expected at least one 429 within $REQUESTS requests"
  exit 1
fi

echo "=== Rate limit check passed ==="
