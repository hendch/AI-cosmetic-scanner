# Evaluation

What we measured, how, and what we found. Every number here comes from a file in `eval/` that you can open
and re-run. Model for every AI step except OCR: `Qwen/Qwen2.5-7B-Instruct:featherless-ai` through the Hugging Face
router, temperature 0. OCR: `Qwen/Qwen3-VL-30B-A3B-Instruct` (same router, same token).

Words used below:

- **Scenario**: one real scan sent to the n8n webhook exactly as the app sends it, with the full answer saved.
- **Rule check**: a check written in code (no AI) that every report goes through (`app/report/checks.py`). If an
  error-level rule check fails, the scan answers `needs_review` instead of `completed`.
- **AI validator**: the validator agent. A model re-reads every claim of the report next to the text of the source it
  cites and says supported / overstated / unsupported. It is **advisory**: it is shown in the app, but it does not
  decide the status (see section 3 for why).
- **False alarm**: the validator flags a claim that is correct.

## Summary

| What | Result | Where |
|---|---|---|
| 5 end-to-end scenarios through n8n (local docker) | 5/5 behave as designed; every rule check passes; 1 to 23 s per scan | `eval/scenarios/2026-10-18_1511/` |
| Regulatory agent, prompt v4 (45 gold cases) | status 100 %, compliance 100 %, conditions 100 %, citations 100 % | `eval/regulatory/RESULTS.md` |
| Toxicology agent (Hind), 43 gold ingredients | rules only: 95.3 % concern levels right; with AI (v7, sunscreen product): 88.2 %, findings 90.9 % found and 90.9 % correct | `eval/toxicology/` |
| RAG retrieval (10 questions) | Recall@3 = 1.0, MRR = 0.9 with structured chunks; 0.2 with fixed-size chunks | `eval/rag/metrics.csv` |
| Label OCR (2 real label photos) | 15/15 and 23/25 ingredients identical to the database text | `CHANGES.md` 5.7 |
| Ingredient-name recognition (25 real products, 491 names) | 88.8 % recognised (84.5 % exact, 4.3 % after typo correction) | `eval/normalize/results.md` |
| AI validator, active prompt v5 (8 test drafts) | 6/8 verdicts right; on the live scenario reports, 10 of 10 flags were false alarms | `eval/validator/results/` |

The short version: the deterministic parts (rules, citations, rule checks) are reliable. The weak point is the
7B validator model, which over-flags correct findings. That is why it is advisory.

## 1. End-to-end scenarios

Run: `python -m scripts.run_scenarios` (local docker compose: API, n8n, Postgres; regulatory agent in live mode).
About 15 model calls for the whole run. Each answer is saved as JSON with the request and the time it took.

| # | Scenario | Product | Time | What happened |
|---|---|---|---|---|
| 1 | Barcode found | Balea Bodylotion Creme-Öl (4066447870213) | 16.5 s | 15 ingredients from Open Beauty Facts; sodium benzoate (V/1), piroctone olamine (V/35), potassium sorbate (V/4) restricted. Leave-on detected, so the right lettered item is used: sodium benzoate 0.5 % (item c), not 2.5 % (item a). |
| 2 | OCR fallback | barcode 3600523351350, then a CeraVe label photo | 0.4 s + 22.9 s | First answer `needs_input`: "We read the barcode 3600523351350, but Open Beauty Facts has no ingredient list ...". The label photo was then read by OCR: 25 ingredients, rinse-off detected from the label, sodium benzoate at 2.5 % (item a) and phenoxyethanol 1 %. |
| 3 | Unknown ingredient | Neutrogena Lipcare (3574660085563) | 1.2 s | Synthetic Wax, Polyisobutene and Copernicia Cerifera Cera are not in our dictionary: shown as "not recognised", not assessed, and the report says so. No restricted ingredient, so no model call. |
| 4 | Missing concentration | Balea Shampoo Anti-Schuppen (4066447982596) | 12.9 s | 3 Annex V preservatives whose limit cannot be checked because labels never print concentrations: "cannot be checked", never "met". Linalool (III/84) only has to be named in the ingredient list, which it is, so it is marked met by rule. |
| 5 | No cruelty-free evidence | Isana Gesichtswasser (4305615657196) | 14.9 s | No brand claim and no certification found: animal testing "not verified". Leave-on detected from the German category "Gesichtswasser". |

What the scenarios found, and what was fixed on the same day (all in `CHANGES.md`):

- **A user's barcode photo answered "ingredient list could not be read".** The barcode (6001230011808) was read fine;
  that product has no ingredient list in Open Beauty Facts. The message now says which barcode was read and what is
  missing. Same for a photo with no barcode and no list.
- **Scenario 3 first answered `needs_input`**: Open Beauty Facts did not answer in time and the API reported that as
  "not found" (saved as `3_unknown_ingredient_first_try_obf_timeout.json`). The lookup now retries once and an outage
  gets its own message ("try again in a minute").
- **Linalool was "cannot be checked"** although its only condition is to be named in the list it was read from. Now met
  by rule, and the model is not called when the rules decide every condition (saves credits).
- **Benzyl alcohol, Isana**: the same allergen rule sits in the warnings column for some entries; covered too.
- **Isana and the liquid soap had no leave-on / rinse-off type**: their categories are German. German and French
  category words were added.
- **The n8n workflow kept running the old version after a change** (fixed version id). The id now changes with the content.

## 2. Regulatory agent

Full write-up: `eval/regulatory/RESULTS.md`. 45 gold ingredient cases (6 products + the samples), 34 scored conditions.

| Prompt | Status | Compliance | Conditions | Citations | Model calls |
|---|---|---|---|---|---|
| rules only (no model) | 100 | 95.6 | 91.4 | 100 | 0 |
| v1 | 100 | 86.7 to 91.1 | 94.1 | 100 | 25 |
| v2 | 100 | 97.8 to 100 | 100 | 100 | 25 |
| v3 | 100 | 93.3 | 94.1 | 100 | 26 |
| **v4 (active)** | **100** | **100** | **100** | **100** | 25 |

Status and citations are decided in code, so they are always right; the model only interprets conditions such as
"not to be used in oral products". Rules only went from 91.2 to 91.4 % on conditions after today's allergen rule.
The provider is not fully deterministic at temperature 0 (v1 and v2 differ between runs).

## 3. AI validator: prompt comparison

Run: `python -m scripts.run_validator_eval v5 v6` (one model call per case and version). Cases in
`eval/validator/cases.json`:

| Case | Built from | Expected |
|---|---|---|
| supported_draft | hand-written, correct | valid |
| risk_leap_and_false_compliance | hand-written: "harmful to users", "complies with the 1 % limit" with unknown concentration | invalid |
| wrong_subject_and_brand_as_certification | hand-written: glycerin citing the phenoxyethanol entry; brand claim called "certified" | invalid |
| real_balea_lotion | real report, rules-only wording | valid |
| real_balea_shampoo | real report, rules-only wording | valid |
| real_soap_planted_errors | real report + 2 planted errors (wrong limit item; linalool "banned") | invalid |
| live_balea_lotion | scenario 1 report, live agent wording | valid |
| live_cerave_ocr | scenario 2 report, live agent wording | valid |

| Prompt | What changed | Verdicts right | Planted problems found (4 in the first 3 cases, 6 once the real cases were added) |
|---|---|---|---|
| v1 | one yes/no answer | 1/3 | n/a (no per-claim verdicts) |
| v2 | per-claim verdicts | 2/3 | 2/4 |
| v3 | stricter rules | 2/3 | 4/4 |
| v4 | brand claims reported as claims are fine | 3/3, then 5/6 with the real cases | 5/6 |
| **v5 (active)** | how annex entries, lettered items and "cannot be checked" work | **6/6**, 6/8 with the live cases | 3/6 |
| v6 (rejected) | product facts checked against the draft; "Other products" | 4/8 | not saved (see the note in `prompts/validator/v6.yaml`) |

What this shows:

- Each prompt fixed what it targeted, and each one broke something else. v5 stopped the false alarms on the
  rules-only reports, but on reports worded by the live regulatory agent it still asks the regulation text to prove
  "the concentration is unknown" (a fact about the product, not about the regulation). v6 told it exactly that and got
  worse. A 7B model does not reliably follow this many rules.
- In the 5 live scenarios the validator flagged 10 claims. We checked each against the annex text: **all 10 are
  correct**, so all 10 flags are false alarms. It flagged nothing that was wrong (there was nothing wrong to flag).
- The problems v5 misses are caught by rule checks: a citation about another ingredient (`citation_subject`), a brand
  claim called certified (`claims_have_evidence`), and, new today, "prohibited" backed by an Annex III entry
  (`status_matches_annex`). That is why rule checks decide the status and the validator is advisory
  (`VALIDATOR_BLOCKING=false`).
- Next step if the team wants a useful validator: a bigger model for this one call, or only send it claims the rule
  checks cannot judge.

## 4. RAG retrieval

`eval/rag/run_eval.py`, 10 questions with a known correct evidence item (`eval/rag/questions.csv`).

| Chunking | Recall@3 | Recall@5 | MRR |
|---|---|---|---|
| structured (one chunk per annex entry or opinion section), filtered | 1.0 | 1.0 | 0.9 |
| structured, unfiltered | 1.0 | 1.0 | 0.9 |
| fixed-size chunks | 0.2 | 0.2 | 0.15 |

Recall@3 = the right evidence is in the top 3 results. MRR = how high it ranks on average (1.0 = always first).
Structured chunks are why retrieval works; fixed-size chunks cut entries in half. The "not listed" question (coverage)
is only answered right with the ingredient filter on.

## 5. Label OCR

Two real label photos from Open Beauty Facts, compared with the ingredient text typed in the database:
Balea body lotion (German) 15/15 identical, 11 s; CeraVe cleanser (Swedish) 23/25, 17 s. The two differences are
one ingredient split differently and a label version that differs from the database text. Scenario 2 repeats the
CeraVe photo end to end.

## 6. Ingredient-name recognition

Run: `python -m scripts.eval_normalize` (no model calls; `--fetch` refreshes the product snapshot).
25 of the most-scanned German products on Open Beauty Facts with a real ingredient list, 491 names.

| | Count | Share |
|---|---|---|
| Recognised exactly | 415 | 84.5 % |
| Recognised after typo correction | 21 | 4.3 % |
| Not recognised | 55 | 11.2 % |

Fixed while measuring: lists separated by " - " were not split, and words broken across two lines on the package
("Ethyl - hexyl Triazone") were not joined; together +1.4 points. Most of what is left is missing from our source:
the Open Beauty Facts copy of the EU CosIng list lacks common names such as Polyisobutene, Olea Europaea Fruit Oil and
Aloe Barbadensis Leaf Juice. The full CosIng list is not offered as a download any more. A name that is not recognised
is never guessed: it is shown as "not recognised" and not assessed.

## 7. Toxicology agent (Hind)

Run: `python -m scripts.eval_toxicology` (modes `rules`, `live`, `replay`). Answer key `eval/toxicology/gold.json`:
8 products, 43 ingredients, with the expected concern level and the SCCS findings an answer should contain.

| Run | Concern level right | SCCS findings found | Findings correct | Coverage right | AI calls |
|---|---|---|---|---|---|
| Rules only, all 43 ingredients | 95.3 % | none (no AI) | - | 80.8 % | 0 |
| Prompt v6, sunscreen product (17 ingredients) | 94.1 % | 90.9 % | 83.3 % | 75.0 % | 18 |
| Prompt v7 (default), sunscreen product | 88.2 % | 90.9 % | 90.9 % | 75.0 % | 19 |

In every run citations were 100 % valid, no answer used verdict wording, and no number appeared that was not in a quote.
The code checks each AI finding (quote word for word, numbers and product types taken from the quote) and drops what fails.
v7 is the default: it is more precise, but v6 got more concern levels right on the one product tested live.

Coverage limit: the CLP table holds 15 ingredients and there are 12 SCCS opinions, so on real products most ingredients
are "not enough evidence" (14 of 15 for the Balea lotion, 13 of 14 for the Isana toner, run 2026-10-19).

## 8. Ethics (cruelty-free) agent (Hind)

A lookup in PETA's lists, no AI, so there is no prompt to evaluate; 13 unit tests cover each status (verified, claimed,
conflicting, not verified) and the brand vs parent-company rule. The five recorded scenarios (2026-10-18) ran before
this agent was merged, so their "not verified" results came from the earlier placeholder.

## 9. Limits of this evaluation

- Small sets: 5 scenarios, 8 validator cases, 45 regulatory cases, 10 retrieval questions, 2 OCR photos.
- The five scenarios were recorded before the toxicology and ethics agents were merged (2026-10-19); they should be
  re-run online to include them.
- The toxicology live evaluation covers one product (17 ingredients).
- The scenarios ran on local docker. Running them on Render: `python -m scripts.run_scenarios https://<n8n>.onrender.com/webhook/cosmetic-scanner-live`.
- Model calls used on 2026-10-18 for this evaluation: about 55 (validator eval 22, two scenario runs about 32, one app test).
