"""n8n <-> FastAPI contract endpoints (see docs/CONTRACT.md).

The prefix is /v1 (not /integration) because the n8n workflow calls these exact paths.
"""
from fastapi import APIRouter, Request

from app.integration import mock

router = APIRouter(prefix="/v1", tags=["integration"])


@router.post("/product/resolve")
async def product_resolve(req: Request):
    return mock.product_resolve(await req.json())


@router.post("/label/extract")
async def label_extract(req: Request):
    return mock.label_extract(await req.json())


@router.post("/ingredients/normalize")
async def ingredients_normalize(req: Request):
    return mock.ingredients_normalize(await req.json())


@router.post("/evidence/retrieve")
async def evidence_retrieve(req: Request):
    return mock.evidence_retrieve(await req.json())
