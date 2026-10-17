"""Main application entry point (owned by integration).

Includes every module's router. Modules that are not merged yet are skipped,
so the app starts at every stage of the project.
Run with: uvicorn app.main:app --reload
"""
import importlib
from fastapi import FastAPI

app = FastAPI(title="AI Cosmetic Safety")

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

