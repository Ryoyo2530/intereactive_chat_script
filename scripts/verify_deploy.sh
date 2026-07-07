#!/usr/bin/env bash
set -euo pipefail

BASE="${1:-}"
if [[ -z "$BASE" ]]; then
  echo "Usage: ./scripts/verify_deploy.sh https://your-app.onrender.com"
  exit 1
fi

BASE="${BASE%/}"
echo "=== Deploy verification: $BASE ==="

curl -sf "$BASE/" | grep -q '另一半台词' && echo "[OK] Homepage + slogan" || { echo "[FAIL] Homepage"; exit 1; }
curl -sf "$BASE/api/scripts" | grep -q 'example_script' && echo "[OK] Scripts API" || { echo "[FAIL] Scripts API"; exit 1; }

CONFIG=$(curl -sf "$BASE/api/config/llm")
echo "$CONFIG" | grep -q '"configured"' && echo "[OK] LLM config endpoint" || { echo "[FAIL] LLM config"; exit 1; }

if echo "$CONFIG" | grep -q '"configured": true'; then
  echo "[OK] LLM configured on server"
else
  echo "[WARN] LLM not configured — set LLM_API_KEY in Render env vars"
fi

SID=$(curl -sf -X POST "$BASE/api/session/start" \
  -H 'Content-Type: application/json' \
  -d '{"script_id":"example_script"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "[OK] Session start: $SID"

STREAM=$(curl -s -N -X POST "$BASE/api/session/message/stream" \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"message\":\"你好\"}" | head -3 || true)
echo "$STREAM" | grep -q 'data:' && echo "[OK] Stream message" || { echo "[FAIL] Stream message"; exit 1; }

echo "=== All checks passed ==="
