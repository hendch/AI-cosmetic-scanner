import io, json, re, requests
from pathlib import Path
from typing import Optional
from PIL import Image
from pyzbar.pyzbar import decode

from app.common.llm import LLMError
from app.ingestion.normalize import normalize_items, normalize_list
from app.ingestion.ocr import OcrError, read_label

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

RINSE_OFF = ("shampoo", "conditioner", "shower", "body-wash", "bath", "soap",
             "cleans", "face-wash", "hair-mask", "scrub")
LEAVE_ON = ("cream", "lotion", "serum", "moistur", "deodorant", "sun", "lip",
            "makeup", "make-up", "foundation", "mascara", "perfume", "balm", "oil")


def exposure_from_categories(tags):
    joined = " ".join(tags or [])
    if any(k in joined for k in RINSE_OFF):  # checked first, so "cleansing cream" -> rinse_off
        return "rinse_off"
    if any(k in joined for k in LEAVE_ON):
        return "leave_on"
    return None


def category_text(tags):
    return tags[-1].split(":")[-1].replace("-", " ") if tags else ""


def scan_barcode(img_bytes: bytes) -> Optional[str]:
    try:
        codes = decode(Image.open(io.BytesIO(img_bytes)))
    except Exception:  # not an image: reported as "no barcode detected"
        return None
    return codes[0].data.decode() if codes else None


OCR_UNSURE_CONFIDENCE = 0.7  # below the agents' 0.8 threshold: they mark the name as unverified


def lookup_barcode(code):
    # Only digits: the barcode becomes a cache file name (no "../" path tricks).
    if not re.fullmatch(r"\d{8,14}", code or ""):
        return None
    path = CACHE_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        r = requests.get(f"https://world.openbeautyfacts.org/api/v2/product/{code}.json",
                         params={"fields": "product_name,brands,ingredients_text,categories_tags,labels_tags"},
                         headers={"User-Agent": "school-project/0.1"}, timeout=10).json()
    except (requests.RequestException, ValueError):
        return None  # reported as "barcode not found or no ingredients"
    if r.get("status") == 1:
        path.write_text(json.dumps(r["product"]), encoding="utf-8")
        return r["product"]
    return None


def _apply_ocr(out: dict, label_image: bytes) -> bool:
    """Read the label photo into `out`. True if it produced ingredients."""
    try:
        res = read_label(label_image)
    except (OcrError, LLMError) as exc:
        out["warnings"].append(f"label photo could not be read: {exc}")
        return False
    if not res.readable or not res.ingredients:
        out["warnings"].append("no readable ingredient list on the label photo")
        return False
    out["ingredients"], out["needs_review"] = normalize_items(res.ingredients)
    unsure = {u.strip().lower() for u in res.uncertain}
    for ing in out["ingredients"]:
        if ing["raw"].strip().lower() in unsure:
            ing["confidence"] = min(ing["confidence"], OCR_UNSURE_CONFIDENCE)
            out["needs_review"] = True
    if unsure:
        out["warnings"].append("label photo: some names were hard to read: " + ", ".join(sorted(unsure)))
    product = out["product"]
    product["name"] = product["name"] or (res.product_name or "")
    product["brand"] = product["brand"] or (res.brand or "")
    if not product["category"] and res.product_type:
        product["category"] = res.product_type.lower()
        product["exposure_type"] = product["exposure_type"] or exposure_from_categories([res.product_type.lower()])
    out["source"] = "ocr"
    return True


def build_response(barcode: Optional[str], label_image: Optional[bytes] = None) -> dict:
    """Barcode first (Open Beauty Facts); if that gives no ingredient list, the label photo (OCR)."""
    out = {"source": None,
           "product": {"name": "", "brand": "", "barcode": barcode or "",
                       "category": "", "exposure_type": None, "labels": []},
           "ingredients": [], "needs_review": False, "warnings": []}
    text = None
    if barcode:
        p = lookup_barcode(barcode)
        if p:
            cats = p.get("categories_tags", [])
            name = p.get("product_name", "")
            # Many products have no categories on Open Beauty Facts: fall back to the product name
            # ("Bodylotion Creme-Öl" -> leave-on), so product-type rules can still be checked.
            out["product"].update(
                name=name, brand=p.get("brands", ""),
                category=category_text(cats) or name.lower(),
                exposure_type=exposure_from_categories(cats) or exposure_from_categories([name.lower()]),
                labels=p.get("labels_tags", []))
        if p and p.get("ingredients_text"):
            text, out["source"] = p["ingredients_text"], "barcode"
        else:
            out["warnings"].append("barcode not found or no ingredients")
    elif not label_image:
        out["warnings"].append("no barcode detected")
    if text is not None:
        out["ingredients"], out["needs_review"] = normalize_list(text)
        return out
    if label_image and _apply_ocr(out, label_image):
        return out
    out["warnings"].append("no input produced ingredients")
    out["needs_review"] = True
    return out
