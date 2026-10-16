# Regulatory agent: evaluation results

Date: 2026-10-16. Model: `Qwen/Qwen2.5-7B-Instruct:featherless-ai` through the Hugging Face router,
temperature 0. Retrieval: `RETRIEVAL_BACKEND=local` (placeholder reading `corpus/regulatory/`).
Gold: `gold.json`, 45 ingredient cases (6 eval products in `products/` + the samples in `samples/input/`),
34 scored conditions. Scoring: `scripts/eval_regulatory.py`.

## Results

| Prompt | Run | Status | Compliance | Conditions | Citations | Wording | LLM calls | Retries | Fallbacks | Overrides | Status disagreements |
|---|---|---|---|---|---|---|---|---|---|---|---|
| mock (rules only) | - | 100.0 | 95.6 | 91.2 | 100.0 | 0 | 0 | 0 | 0 | 0 | 0 |
| v1 (naive) | A | 100.0 | 91.1 | 94.1 | 100.0 | 0 | 25 | 0 | 0 | 30 | 4 |
| v1 | B | 100.0 | 86.7 | 94.1 | 100.0 | 0 | 25 | 0 | 0 | 25 | 6 |
| v2 | A | 100.0 | 97.8 | 100.0 | 100.0 | 0 | 25 | 0 | 0 | 16 | 0 |
| v2 | B | 100.0 | 100.0 | 100.0 | 100.0 | 0 | 25 | 0 | 0 | 16 | 0 |
| v3 | A | 100.0 | 93.3 | 94.1 | 100.0 | 0 | 26 | 1 | 0 | 22 | 0 |
| v3 | B | 100.0 | 93.3 | 94.1 | 100.0 | 0 | 26 | 1 | 0 | 21 | 0 |
| v3 | C | 100.0 | 93.3 | 94.1 | 100.0 | 0 | 26 | 1 | 0 | 18 | 0 |
| **v4 (current)** | C | **100.0** | **100.0** | **100.0** | **100.0** | 0 | 25 | 0 | 0 | 3 | 0 |

Files: run A = `live_runA_2026-10-16_table.txt` (table only; its JSON files were overwritten by run B);
run B = `results_live_v1.json`, `results_live_v2.json`, `results_live_v3_runB.json`;
run C = `results_live_v3.json`, `results_live_v4.json`; mock = `results_mock_mock.json`.
Each live JSON holds the errors, every safety override and the raw model answers.

Status and citations are 100 % everywhere because both are decided in code: the status comes from the
retrieved annex and citations are checked against the passages. The prompts only change the condition
results, and through them the compliance check.

The provider is not fully deterministic at temperature 0: v1 and v2 differ between runs A and B.
v3 gave exactly the same 5 errors in all three runs. v4 was run once.

### The two cases only an LLM can get right

| Case | mock | v1 | v2 | v3 | v4 |
|---|---|---|---|---|---|
| `baby_nappy_cream` propylparaben, V/12a usage -> `not_satisfied` | unknown | ok (A, B) | ok (A, B) | ok (A, B, C; in A only after the retry) | ok |
| `toothpaste` salicylic acid, "not to be used in oral products" -> `not_satisfied` | unknown | wrong (A, B) | ok (A, B) | wrong (A, B, C) | ok, but wrong reason (see below) |

## Errors per version

- **v1**: toothpaste salicylic acid usage `satisfied` ("The product is not an oral product"); limonene
  `not_satisfied` because the concentration is unknown (shampoo, toothpaste); benzophenone-3 usage
  `not_satisfied` after inventing a concentration ("if it were to be used at 0.5% ..."), in 1 product in
  run A and 3 in run B. Also changed the status to "prohibited" for Annex V/VI entries in 4-6 answers
  (ignored by code), and wrapped every answer in ```json fences.
- **v2**: run B had no errors. Run A had one: the face cream's salicylic acid usage was failed with an
  inverted argument ("The product is a face cream, which is not a preparation for children under 3").
- **v3**: fixed that v2 case but regressed on two that v2 got right: toothpaste salicylic acid is
  "not an oral product" again, and limonene is `not_satisfied` because the concentration is unknown. The
  model read "satisfied only with proof" as "otherwise not_satisfied". It also skipped conditions in 8-9 of
  26 answers.
- **v4**: no scored errors. One reasoning error: for the toothpaste it writes "The product is a rinse-off
  hair product, which is not an oral product, but the entry explicitly states it is not to be used in oral
  products" -> `not_satisfied`. The result is right but the reason contradicts it, and the consumer
  explanation repeats "rinse-off hair product". The eval scores results, not reasons.

All observed failures, with the exact model output, are in `known_failures` of `prompts/regulatory/v*.yaml`.

## What each version fixed

| Version | Change | Effect |
|---|---|---|
| v1 | Naive: "is it allowed, is the product compliant?", evidence and conditions given | Status from memory (ignored by code), guessed concentrations, invented label facts, JSON in fences |
| v2 | Status given by code ("do not change it"), evidence-only, strict rules (unknown concentration -> unknown, no label text, no safe/unsafe wording), JSON only | Concentration overrides 15 -> 0, status disagreements 4-6 -> 0, no fences, oral-product case solved |
| v3 | Explicit rule for "Other products except ..." lists; "satisfied" only with explicit proof | Fixed v2's age/purpose claims, but regressed (oral product, limonene). Product-type matching had already moved to code (`rules.match_product_type`) because v3 still misread the exclusion list |
| v4 | "not_satisfied" also needs proof (missing info = unknown, including a concentration threshold inside a usage condition); name the product kind before judging usage; one answer item per condition index | 100 % on every metric, skipped conditions 8-9 -> 0, overrides 18-22 -> 3 |

## Safety overrides (code beats the LLM)

| Rule | v1 A | v1 B | v2 A | v2 B | v3 A | v3 B | v3 C | v4 C |
|---|---|---|---|---|---|---|---|---|
| Unknown concentration -> `unknown` (LLM said not_satisfied / not_applicable) | 15 | 15 | 0 | 0 | 4 | 4 | 4 | 1 |
| Label warning without label text -> `unknown` (LLM said satisfied / not_satisfied) | 15 | 10 | 14 | 14 | 9 | 8 | 6 | 2 |
| Condition skipped by the LLM, filled by rule | 0 | 0 | 2 | 2 | 9 | 9 | 8 | 0 |
| Product type decided by rule wins | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| **Total** | 30 | 25 | 16 | 16 | 22 | 21 | 18 | 3 |

The product-type rule never had to override, because since v3 the rule's decision is shown to the model as
"already decided by rule" and the model copies it. One retry happened in each v3 run (propylparaben skipped
a usage condition the code cannot fill), and it fixed the answer each time. No fallbacks were needed in any run.

## Conclusions for the report

Every decision that can be made safely by code has moved out of the prompt: legal status comes from the
retrieved annex, product-type matching for lettered annex items is done by `rules.match_product_type` because
the 7B model kept misreading "Other products except ..." lists even with explicit instructions, and unknown
concentrations and missing label text are forced to `unknown` whatever the model says (25-30 corrections per
run with the naive prompt, 3 with v4). The LLM is left with what code cannot easily decide, the usage
conditions in free text, and there prompt wording matters in both directions: v3's "satisfied only with proof"
fixed one false claim but made the model treat missing information as a violation, which v4 fixed by
requiring proof for `not_satisfied` too. v4 reaches 100 % on all metrics, but on the toothpaste it gets the right
result for a contradictory reason, so the next step is to decide "not to be used in oral products" in code from
the product category, the same way as product types. The evaluation also shows the provider is not fully
deterministic at temperature 0, so single-run differences of one or two cases should not be over-read.

## Reproduce

```
python -m scripts.eval_regulatory --mode mock
python -m scripts.eval_regulatory --mode live --prompts v1 v2 v3 v4   # about 100 calls, needs HF_TOKEN in .env
```
