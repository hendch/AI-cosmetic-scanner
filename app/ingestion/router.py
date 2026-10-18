import base64
import re
from typing import Optional

import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.common_schemas import ProductInput
from app.ingestion.extract import build_response, scan_barcode
from app.ingestion.mock import MOCK

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
USE_MOCK = False
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.post("/extract", response_model=ProductInput)
async def extract(barcode: Optional[str] = Form(None),
                  barcode_image: Optional[UploadFile] = File(None),
                  label_image: Optional[UploadFile] = File(None)):
    """File uploads (handy from /docs). Barcode number or barcode photo; label photo is the fallback."""
    if USE_MOCK:
        return MOCK
    if not barcode and barcode_image:
        barcode = scan_barcode(await barcode_image.read())
    label = await label_image.read() if label_image else None
    return build_response(barcode, label)


class ScanRequest(BaseModel):
    """What n8n forwards from the app. Image refs are data URIs (data:image/jpeg;base64,...) or https URLs."""
    barcode: Optional[str] = None
    barcode_image_ref: Optional[str] = None
    label_image_ref: Optional[str] = None


def image_from_ref(ref: str) -> bytes:
    m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", ref, re.DOTALL)
    if m:
        data = base64.b64decode(m.group(1), validate=False)
    elif ref.startswith("https://"):
        try:
            r = requests.get(ref, timeout=15, stream=True)
            r.raise_for_status()
            data = r.raw.read(MAX_IMAGE_BYTES + 1, decode_content=True)
        except requests.RequestException as exc:
            raise HTTPException(422, f"Could not download the image: {exc}") from exc
    else:
        raise HTTPException(422, "Image refs must be a data:image/...;base64 URI or an https URL")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image larger than 10 MB")
    return data


@router.post("/scan", response_model=ProductInput)
def scan(req: ScanRequest):
    """JSON version of /extract, called by n8n."""
    if USE_MOCK:
        return MOCK
    barcode = (req.barcode or "").strip() or None
    if not barcode and req.barcode_image_ref:
        barcode = scan_barcode(image_from_ref(req.barcode_image_ref))
    label = image_from_ref(req.label_image_ref) if req.label_image_ref else None
    return build_response(barcode, label)
