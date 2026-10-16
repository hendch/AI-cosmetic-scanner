"""Build data/peta_brands.json from PETA's Beauty Without Bunnies lists.

Scrapes both the "don't test" and "do test" company lists (50 companies per page)
into one JSON file used by the ethics agent for brand lookup. The output is not
committed (public repo); rerun this script to regenerate it.

Usage: python -m scripts.build_peta_brands
"""

import html
import json
import re
import time
import unicodedata
from datetime import date
from pathlib import Path

import httpx
import truststore

truststore.inject_into_ssl()  # use the OS certificate store (needed behind some proxies)

OUTPUT = Path(__file__).resolve().parent.parent / "data" / "peta_brands.json"
LISTS = {
    "dont_test": "https://crueltyfree.peta.org/companies-dont-test/",
    "do_test": "https://crueltyfree.peta.org/companies-do-test/",
}
REQUEST_DELAY_SECONDS = 1.0
MAX_PAGES = 500

COMPANY_LINK = re.compile(
    r'<a href="(https://crueltyfree\.peta\.org/company/[^"]+)"[^>]*class="link">([^<]+)</a>'
)
TOOLTIP = re.compile(r'title="([^"]+)"')


def normalize(name: str) -> str:
    """Lowercase, strip accents and punctuation: "L'Oréal Paris" -> "loreal paris"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", ascii_name.lower())).strip()


def parse_page(page_html: str, status: str) -> list[dict]:
    companies = []
    for block in page_html.split("<li>"):
        link = COMPANY_LINK.search(block)
        if not link:
            continue
        name = html.unescape(link.group(2)).strip()
        labels = sorted({html.unescape(t).strip() for t in TOOLTIP.findall(block)} - {name})
        companies.append(
            {"name": name, "normalized": normalize(name), "status": status, "labels": labels, "url": link.group(1)}
        )
    return companies


def scrape_list(client: httpx.Client, status: str, base_url: str) -> list[dict]:
    companies = []
    for page in range(1, MAX_PAGES + 1):
        url = base_url if page == 1 else f"{base_url}page/{page}/"
        response = client.get(url)
        if response.status_code == 404:
            break
        response.raise_for_status()
        found = parse_page(response.text, status)
        if not found:
            break
        companies.extend(found)
        print(f"{status}: page {page}, {len(companies)} companies")
        time.sleep(REQUEST_DELAY_SECONDS)
    return companies


def main() -> None:
    headers = {"User-Agent": "AI-cosmetic-safety student project (brand lookup)"}
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        companies = [c for status, url in LISTS.items() for c in scrape_list(client, status, url)]

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "source": "PETA Beauty Without Bunnies",
                "source_id": "peta_beauty_without_bunnies",
                "lists": LISTS,
                "retrieved": date.today().isoformat(),
                "companies": companies,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(companies)} companies to {OUTPUT}")


if __name__ == "__main__":
    main()
