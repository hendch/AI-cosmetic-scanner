import io, json, re, requests
from pathlib import Path
from typing import Optional
from PIL import Image
from pyzbar.pyzbar import decode
from rapidfuzz import process, fuzz

from app.ingestion.known import KNOWN, ALIASES

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
    codes = decode(Image.open(io.BytesIO(img_bytes)))
    return codes[0].data.decode() if codes else None


def split_ingredients(text):
    return [p.strip() for p in re.split(r",(?![^()]*\))", text) if p.strip()]


def normalize(raw, pos):
    c = re.sub(r"\s*\(.*?\)", "", raw.lower()).strip("*. ")   # drop "(Fragrance)", "(CI 77891)"
    c = ALIASES.get(c, c)
    if c in KNOWN:
        return {"position": pos, "raw": raw, "normalized": c, "matched": True, "confidence": 1.0}
    m = process.extractOne(c, KNOWN, scorer=fuzz.ratio)
    digits = lambda s: re.sub(r"\D", "", s)
    ok = bool(m and m[1] >= 92 and digits(c) == digits(m[0]))  # strict: "-3" must equal "-4"
    return {"position": pos, "raw": raw, "normalized": m[0] if ok else c,
            "matched": ok, "confidence": round(m[1] / 100, 2) if m else 0.0}


def lookup_barcode(code):
    path = CACHE_DIR / f"{code}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    r = requests.get(f"https://world.openbeautyfacts.org/api/v2/product/{code}.json",
                     params={"fields": "product_name,brands,ingredients_text,categories_tags,labels_tags"},
                     headers={"User-Agent": "school-project/0.1"}, timeout=10).json()
    if r.get("status") == 1:
        path.write_text(json.dumps(r["product"]), encoding="utf-8")
        return r["product"]
    return None


def build_response(barcode: Optional[str]) -> dict:
    out = {"source": "none",
           "product": {"name": "", "brand": "", "barcode": barcode or "",
                       "category": "", "exposure_type": None, "labels": []},
           "ingredients": [], "needs_review": False, "warnings": []}
    text = None
    if barcode:
        p = lookup_barcode(barcode)
        if p:
            cats = p.get("categories_tags", [])
            out["product"].update(
                name=p.get("product_name", ""), brand=p.get("brands", ""),
                category=category_text(cats), exposure_type=exposure_from_categories(cats),
                labels=p.get("labels_tags", []))
        if p and p.get("ingredients_text"):
            text, out["source"] = p["ingredients_text"], "barcode"
        else:
            out["warnings"].append("barcode not found or no ingredients")
    else:
        out["warnings"].append("no barcode detected")
    if text is None:
        out["warnings"].append("no input produced ingredients")
        out["needs_review"] = True
        return out
    out["ingredients"] = [normalize(r, i + 1) for i, r in enumerate(split_ingredients(text))]
    out["needs_review"] = any(not i["matched"] for i in out["ingredients"])
    return out