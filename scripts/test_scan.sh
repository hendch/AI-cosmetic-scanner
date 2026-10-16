#!/usr/bin/env bash
# Usage: ./scripts/test_scan.sh <api-key> [barcode]   (workflow must be Active; use /webhook-test/ while testing in the editor)
curl -s -X POST "http://localhost:5678/webhook/cosmetic-scanner-live" \
  -H "X-API-Key: ${1:?api key}" -H "Content-Type: application/json" \
  -d "{\"barcode\":\"${2:-4006381333931}\",\"market\":\"EU\"}" | python3 -m json.tool
