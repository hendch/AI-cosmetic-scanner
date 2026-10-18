# n8n with the project's workflows baked in. On every start it imports deploy/n8n/workflows/*.json
# (same IDs, so they are updated, not duplicated) and publishes them, so the workflow in git is
# always the one that runs. Build context: deploy/n8n
FROM n8nio/n8n:2.43.7

COPY --chown=node:node workflows/ /opt/scanner/workflows/
COPY --chown=node:node start.sh /opt/scanner/start.sh

# Render routes to this port; n8n's own default is 5678.
ENV N8N_PORT=10000 \
    PORT=10000 \
    N8N_DIAGNOSTICS_ENABLED=false \
    N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
    N8N_PROXY_HOPS=1 \
    GENERIC_TIMEZONE=Africa/Tunis
EXPOSE 10000

ENTRYPOINT ["/bin/sh", "/opt/scanner/start.sh"]
