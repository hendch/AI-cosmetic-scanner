"""Build corpus/toxicology/clp/clp_test_ingredients.csv from the ECHA Annex VI Excel.

One row per test ingredient. Harmonised classifications are filled from Annex VI
(matched on CAS number); ingredients without an entry are marked harmonised=no,
and their notified classification is filled in by hand from ECHA CHEM.

Usage: python -m scripts.build_clp_table
"""

import csv
from pathlib import Path

import openpyxl

CLP_DIR = Path(__file__).resolve().parent.parent / "corpus" / "toxicology" / "clp"
ANNEX_VI = CLP_DIR / "annex_vi_clp_table_atp23_en.xlsx"
OUTPUT = CLP_DIR / "clp_test_ingredients.csv"

# (normalized INCI name, ECHA substance name, CAS No, EC No, note)
TEST_INGREDIENTS = [
    ("glycerin", "Glycerol", "56-81-5", "200-289-5", ""),
    ("niacinamide", "Nicotinamide", "98-92-0", "202-713-4", ""),
    ("phenoxyethanol", "2-phenoxyethanol", "122-99-6", "204-589-7", ""),
    ("methylisothiazolinone", "2-methylisothiazol-3(2H)-one", "2682-20-4", "220-239-6", ""),
    ("salicylic acid", "salicylic acid", "69-72-7", "200-712-3", ""),
    ("bht", "2,6-di-tert-butyl-p-cresol", "128-37-0", "204-881-4", ""),
    ("retinol", "Retinol", "68-26-8", "200-683-7", ""),
    ("homosalate", "Homosalate", "118-56-9", "204-260-8", ""),
    ("octocrylene", "Octocrilene", "6197-30-4", "228-250-8", ""),
    ("benzophenone-3", "Oxybenzone", "131-57-7", "205-031-5", ""),
    ("propylparaben", "Propyl 4-hydroxybenzoate", "94-13-3", "202-307-7", ""),
    ("butylparaben", "butyl 4-hydroxybenzoate", "94-26-8", "202-318-7", ""),
    (
        "titanium dioxide",
        "Titanium dioxide",
        "13463-67-7",
        "236-675-5",
        "Former harmonised Carc. 2 (inhalation, powder form) was annulled by the EU courts; not in Annex VI ATP23.",
    ),
    (
        "butylphenyl methylpropional",
        "2-(4-tert-butylbenzyl)propionaldehyde",
        "80-54-6",
        "201-289-8",
        "Lilial; banned in EU cosmetics as CMR.",
    ),
    ("zinc pyrithione", "pyrithione zinc", "13463-41-7", "236-671-3", "Banned in EU cosmetics as CMR."),
]

# Ingredients without a harmonised entry: ECHA CHEM page and the recommended (starred)
# notified classification, filled in by hand from that page.
# ingredient: (ECHA CHEM URL, notified classification, accessed date)
NOTIFIED = {
    "glycerin": ("https://chem.echa.europa.eu/100.000.263", "", ""),
    "niacinamide": ("https://chem.echa.europa.eu/100.002.467", "", ""),
    "bht": ("https://chem.echa.europa.eu/100.004.439", "", ""),
    "retinol": ("https://chem.echa.europa.eu/100.000.621", "", ""),
    "homosalate": ("https://chem.echa.europa.eu/100.003.874", "", ""),
    "octocrylene": ("https://chem.echa.europa.eu/100.025.683", "", ""),
    "benzophenone-3": ("https://chem.echa.europa.eu/100.004.575", "", ""),
    "propylparaben": ("https://chem.echa.europa.eu/100.002.098", "", ""),
    "butylparaben": ("https://chem.echa.europa.eu/100.002.108", "", ""),
    "titanium dioxide": ("https://chem.echa.europa.eu/100.033.327", "", ""),
}

FIELDS = [
    "ingredient",
    "echa_substance_name",
    "cas",
    "ec",
    "harmonised",
    "annex_vi_index_no",
    "annex_vi_chemical_name",
    "atp",
    "hazard_classes",
    "hazard_statements",
    "notified_classification",
    "notified_source_url",
    "accessed_date",
    "note",
]


def _join(cell) -> str:
    return "; ".join(part.strip() for part in str(cell or "").splitlines() if part.strip())


def load_annex_vi_by_cas() -> dict[str, tuple]:
    sheet = openpyxl.load_workbook(ANNEX_VI, read_only=True)["ATP23"]
    rows = sheet.iter_rows(values_only=True)
    for row in rows:
        if row[0] == "Index No":
            break
    return {str(row[5]).strip(): row for row in rows if row[5]}


def main() -> None:
    annex_vi = load_annex_vi_by_cas()
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for ingredient, echa_name, cas, ec, note in TEST_INGREDIENTS:
            entry = annex_vi.get(cas)
            row = dict.fromkeys(FIELDS, "")
            row.update(
                ingredient=ingredient,
                echa_substance_name=echa_name,
                cas=cas,
                ec=ec,
                note=note,
                harmonised="yes" if entry else "no",
            )
            if entry:
                row.update(
                    annex_vi_index_no=entry[0],
                    atp=entry[1],
                    annex_vi_chemical_name=_join(entry[3]),
                    hazard_classes=_join(entry[6]),
                    hazard_statements=_join(entry[7]),
                )
            elif ingredient in NOTIFIED:
                url, classification, accessed = NOTIFIED[ingredient]
                row.update(notified_source_url=url, notified_classification=classification, accessed_date=accessed)
            writer.writerow(row)
            print(f"{ingredient:30} harmonised={row['harmonised']:3} {row['hazard_classes']}")


if __name__ == "__main__":
    main()
