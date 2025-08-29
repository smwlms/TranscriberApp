#!/usr/bin/env bash
set -euo pipefail

# Simple smoke tests for Transcriber API
BASE_URL="${BASE_URL:-http://127.0.0.1:${FLASK_PORT:-5000}}"
API_PREFIX="${API_PREFIX:-/api/v1}"

echo "[0] Waiting for server at ${BASE_URL} ..."
for i in $(seq 1 30); do
  if curl -fsS "${BASE_URL}/" >/dev/null 2>&1; then
    echo "Server is up."
    break
  fi
  printf '.'; sleep 1
  if [ "$i" -eq 30 ]; then
    echo "\nTimeout waiting for server."; exit 1
  fi
done

echo "\n[1] Health check ${BASE_URL}/"
curl -fsS "${BASE_URL}/" | jq . || curl -fsS "${BASE_URL}/" || true

echo "\n[2] Adjust: plain text -> results/testnote.txt"
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from smoke test","append":false}' \
  "${BASE_URL}${API_PREFIX}/transcriptions/testnote/adjust" | jq . || true

echo "\n[3] Adjust: transcript -> transcripts/demo.json + results/demo.html"
curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -d '{"transcript":[{"start":0.0,"text":"Welkom!","speaker_name":"Spreker A"},{"start":2.5,"text":"Hoi daar","speaker_name":"Spreker B"}]}' \
  "${BASE_URL}${API_PREFIX}/transcriptions/demo/adjust" | jq . || true

echo "\n[4] Fetch generated files (HTML/TXT)"
echo "TXT URL: ${BASE_URL}/results/testnote.txt"
echo "HTML URL: ${BASE_URL}/results/demo.html"
echo "JSON URL: ${BASE_URL}/transcripts/demo.json"

echo "\nDone."
