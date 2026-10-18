"""Main application entry point (owned by integration).

Includes every module's router. Modules that are not merged yet are skipped,
so the app starts at every stage of the project.
Run with: uvicorn app.main:app --reload

When SCANNER_API_KEY is set (always on Render), every request except /health must send
the header X-API-Key: <that value>. The API is public and spends the team's HF credits.
"""
import importlib
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="AI Cosmetic Safety")

API_KEY = os.environ.get("SCANNER_API_KEY", "")
OPEN_PATHS = {"/health"}


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    if API_KEY and request.url.path not in OPEN_PATHS:
        if not secrets.compare_digest(request.headers.get("x-api-key", ""), API_KEY):
            return JSONResponse({"detail": "Missing or invalid X-API-Key header"}, status_code=401)
    return await call_next(request)


# (module path, router attribute); add a line when a new module lands.
ROUTER_MODULES = [
    "app.integration.router",
    "app.toxicology.router",
    "app.ethics.router",
    "app.regulatory.router",
    "app.rag.router",
    "app.ingestion.router",
    "app.report.router",
]

for module_path in ROUTER_MODULES:
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        if exc.name != module_path and not module_path.startswith(exc.name or "\0"):
            raise  # the module exists but one of its imports is broken
        continue
    app.include_router(module.router)


@app.get("/health")
async def health():
    return {"ok": True}
