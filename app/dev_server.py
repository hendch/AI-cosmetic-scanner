"""Local dev entry point for the toxicology and ethics modules only.

The real application entry point is owned by Person 1 (integration); it should
include the same routers. Run with: uvicorn app.dev_server:app --reload
"""

from fastapi import FastAPI

from app.ethics.router import router as ethics_router
from app.toxicology.router import router as toxicology_router

app = FastAPI(title="AI Cosmetic Safety - toxicology & ethics (dev)")
app.include_router(toxicology_router)
app.include_router(ethics_router)
