#!/usr/bin/env bash
# Exports every n8n workflow into n8n/workflows/ (credentials are NOT included).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T n8n n8n export:workflow --all --separate --output=/tmp/wf
rm -rf /tmp/wf_export && mkdir -p /tmp/wf_export
docker cp n8n:/tmp/wf /tmp/wf_export
for f in /tmp/wf_export/wf/*.json; do
  name=$(python3 -c "import json,sys;print(json.load(open('$f'))['name'].replace(' ','-'))")
  python3 -m json.tool "$f" > "n8n/workflows/${name}.json"
done
echo "Exported to n8n/workflows/. Review with: git diff"
