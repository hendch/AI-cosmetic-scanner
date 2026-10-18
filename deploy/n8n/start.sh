#!/bin/sh
# Start n8n with the project's workflows imported and published.
set -e

# Render gives every web service its public URL; n8n needs it to build webhook URLs.
if [ -z "$N8N_WEBHOOK_URL" ] && [ -n "$RENDER_EXTERNAL_URL" ]; then
  export N8N_WEBHOOK_URL="$RENDER_EXTERNAL_URL/"
fi
if [ -z "$N8N_EDITOR_BASE_URL" ] && [ -n "$N8N_WEBHOOK_URL" ]; then
  export N8N_EDITOR_BASE_URL="$N8N_WEBHOOK_URL"
fi

for f in /opt/scanner/workflows/*.json; do
  [ -e "$f" ] || continue
  id=$(node -e "console.log(require(process.argv[1]).id || '')" "$f")
  echo "[start] importing $(basename "$f") (id $id)"
  n8n import:workflow --input="$f"
  if [ -n "$id" ]; then
    # A workflow that cannot be published (e.g. a node is misconfigured) must not stop n8n from starting.
    n8n publish:workflow --id="$id" || echo "[start] WARNING: could not publish workflow $id"
  fi
done

exec n8n start
