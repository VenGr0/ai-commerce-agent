#!/usr/bin/env bash
set -euo pipefail
BASE=${BASE:-http://localhost:8000}
EMAIL=${EMAIL:-demo@example.com}
PASSWORD=${PASSWORD:-change-me-123}

TOKEN=$(curl -sS -X POST "$BASE/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

echo "TOKEN=$TOKEN"
echo "Open $BASE/docs or $BASE/static/index.html"
