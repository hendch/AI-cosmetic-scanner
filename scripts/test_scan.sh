#!/usr/bin/env bash
# Send one scan to the n8n webhook and print the answer.
# Usage: ./scripts/test_scan.sh <webhook-key> [barcode] [n8n-url]
#   webhook-key = EXPO_PUBLIC_WEBHOOK_KEY;  n8n-url defaults to http://localhost:5678 (docker compose)
curl -s -X POST "${3:-http://localhost:5678}/webhook/cosmetic-scanner-live" \
  -H "X-API-Key: ${1:?webhook key}" -H "Content-Type: application/json" \
  -d "{\"barcode\":\"${2:-4066447870213}\"}" | python3 -m json.tool
