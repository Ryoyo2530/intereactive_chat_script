#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-}"
if [[ -z "$BASE" ]]; then
  echo "Usage: ./scripts/verify_deploy.sh https://your-app.onrender.com"
  exit 1
fi

BASE="${BASE%/}"
SCRIPT_ID="${VERIFY_SCRIPT_ID:-fanfic_friendship_001}"
echo "=== Deploy verification: $BASE ==="

curl -sf "$BASE/" | grep -q '另一半台词' && echo "[OK] Homepage + slogan" || { echo "[FAIL] Homepage"; exit 1; }
curl -sf "$BASE/api/scripts" | grep -q "$SCRIPT_ID" && echo "[OK] Scripts API ($SCRIPT_ID)" || { echo "[FAIL] Scripts API"; exit 1; }

CONFIG=$(curl -sf "$BASE/api/config/llm")
echo "$CONFIG" | grep -q '"configured"' && echo "[OK] LLM config endpoint" || { echo "[FAIL] LLM config"; exit 1; }

if echo "$CONFIG" | grep -q '"configured": true'; then
  echo "[OK] LLM configured on server"
else
  echo "[WARN] LLM not configured — set LLM_API_KEY in Render env vars"
fi

CACHE=$(curl -sI "$BASE/echoes/echoes.css" | tr -d '\r' | grep -i '^cache-control:' || true)
if echo "$CACHE" | grep -qi 'max-age=86400'; then
  echo "[OK] Static cache header on echoes.css"
else
  echo "[FAIL] Missing Cache-Control max-age on echoes.css (got: ${CACHE:-none})"
  exit 1
fi

GZIP=$(curl -sI -H 'Accept-Encoding: gzip' "$BASE/echoes/echoes.css" | tr -d '\r' | grep -i '^content-encoding:' || true)
if echo "$GZIP" | grep -qi 'gzip'; then
  echo "[OK] GZip enabled for static assets"
else
  echo "[WARN] No Content-Encoding: gzip (may be below minimum_size threshold)"
fi

if echo "$CONFIG" | grep -q '"configured": true'; then
  SID=$(curl -sf -X POST "$BASE/api/session/start" \
    -H 'Content-Type: application/json' \
    -d "{\"script_id\":\"$SCRIPT_ID\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
  echo "[OK] Session start: $SID"

  STREAM=$(curl -s -N -X POST "$BASE/api/session/message/stream" \
    -H 'Content-Type: application/json' \
    -d "{\"session_id\":\"$SID\",\"message\":\"你好\"}" | head -3 || true)
  echo "$STREAM" | grep -q 'data:' && echo "[OK] Stream message" || { echo "[FAIL] Stream message"; exit 1; }
else
  echo "[SKIP] Session/stream checks (LLM not configured)"
fi

if [[ "${VERIFY_RATE_LIMIT:-}" == "1" ]]; then
  LIMIT="${RATE_LIMIT_PER_MINUTE:-120}"
  "$(dirname "$0")/verify_rate_limit.sh" "$BASE" "$LIMIT"
else
  echo "[SKIP] Rate limit load test (set VERIFY_RATE_LIMIT=1 to enable)"
fi

echo "=== All checks passed ==="
