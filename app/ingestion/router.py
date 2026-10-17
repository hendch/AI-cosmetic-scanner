from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile

from app.common_schemas import ProductInput
from app.ingestion.extract import build_response, scan_barcode
from app.ingestion.mock import MOCK

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
USE_MOCK = False


@router.post("/extract", response_model=ProductInput)
async def extract(barcode: Optional[str] = Form(None),
                  barcode_image: Optional[UploadFile] = File(None)):
    if USE_MOCK:
        return MOCK
    if not barcode and barcode_image:
        barcode = scan_barcode(await barcode_image.read())
    return build_response(barcode)
