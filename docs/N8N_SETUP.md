# AI Cosmetic Scanner: n8n & integration

```bash
cp .env.example .env            # fill N8N_ENCRYPTION_KEY (openssl rand -hex 16) and POSTGRES_PASSWORD
docker compose up -d --build    # n8n, scanner-api (app.main:app), ollama (+model pull), postgres
```
Then open http://localhost:5678, import `deploy/n8n/workflows/AI-Cosmetic-Scanner-Live-Only.json`,
create the 3 credentials (Header Auth, Ollama, Postgres) and run it.

Contract: `docs/CONTRACT.md`. Test the mock: `pytest tests/test_integration.py`.
Test a scan: `./scripts/test_scan.sh <api-key> [barcode]`.
