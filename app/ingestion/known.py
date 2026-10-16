# Ingredients the toxicology corpus has data on (from corpus/sources.csv).
# Ideally load this from the shared ingredient list (clp_test_ingredients.csv) so names never drift.
KNOWN = [
    "benzophenone-3", "bht", "homosalate", "methylisothiazolinone",
    "octocrylene", "parabens", "phenoxyethanol", "propylparaben",
    "retinol", "salicylic acid", "titanium dioxide", "zinc pyrithione",
]

# alias target must be in KNOWN, otherwise the alias does nothing
ALIASES = {
    "water": "aqua", "eau": "aqua", "fragrance": "parfum",
    "oxybenzone": "benzophenone-3",
    "butylated hydroxytoluene": "bht",
    "ci 77891": "titanium dioxide",
    "vitamin a": "retinol",
    "retinyl palmitate": "retinol", "retinyl acetate": "retinol",
    "methylparaben": "parabens", "ethylparaben": "parabens",
    "butylparaben": "parabens", "isobutylparaben": "parabens",
    "isopropylparaben": "parabens",
}
