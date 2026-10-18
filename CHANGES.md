# What changed on the `end-to-end` branch, and why

**Written for the team.** This branch was made by Omar between 2026-10-17 and 2026-10-18.
It starts from `main` at commit `844726a` (PR #10, Hind's restructure). Nothing here is merged into `main` yet.

**Goal of the branch:** make a real scan work from start to finish (app → n8n → our API → AI models → report),
and prepare everything to run online on Render.

How to read this file:

1. [Words used in this file](#1-words-used-in-this-file): plain explanations of every technical term.
2. [The problem we found](#2-the-problem-we-found-on-main): what was wrong on `main`, with evidence.
3. [Before and after](#3-before-and-after-how-a-scan-flows): how a scan flows.
4. [Status](#4-status-what-works-now-and-what-does-not): what works now and what does not.
5. [Every change in detail](#5-every-change-in-detail): before / now / why / example, area by area.
6. [What this means for your module](#6-what-this-means-for-your-module): one section per teammate.
7. [Still to do](#7-still-to-do).

---

## 1. Words used in this file

| Word | What it means here |
|---|---|
| **API** | Our Python server (FastAPI, `app/main.py`). Other programs send it requests and get answers back. |
| **Endpoint** | One address on the API that does one job, e.g. `POST /regulatory/analyze` ("send a product, get the regulatory findings"). You can try every endpoint at `/docs` when the API runs. |
| **n8n** | The automation tool that runs the pipeline: it receives the scan from the app and calls our endpoints in order. Each step in n8n is a **node**; the whole chain is the **workflow**. |
| **Render** | The hosting website where we will put the API, n8n, the web app and the database online. |
| **Model / LLM** | The AI that writes text (Qwen 2.5 7B for our agents). We do not run it on our computers: we send it requests over the internet. |
| **Hugging Face router** | The Hugging Face service (`https://router.huggingface.co/v1`) that forwards our requests to companies hosting the models. Every model we use goes through it, with **one key: `HF_TOKEN`** (the team token, kept in `.env`, never in git). |
| **Vision model** | A model that can look at an image. We use `Qwen/Qwen3-VL-30B-A3B-Instruct` to read ingredient labels from photos. |
| **OCR** | "Optical character recognition": reading text from a photo. Here: reading the ingredient list from a label photo. |
| **Embedding** | A list of 384 numbers that represents the meaning of a sentence. Two sentences with similar meaning get similar numbers. This is how the search finds "phenoxyethanol maximum concentration" in the regulation text. Model: `BAAI/bge-small-en-v1.5`. |
| **RAG** | "Retrieval-augmented generation": before an agent answers, we **search our documents** (the corpus) for the relevant passages and give them to the agent, so it answers from real sources instead of memory. |
| **Corpus** | Our collection of source documents: the EU cosmetics regulation (Regulation (EC) No 1223/2009) and its annexes, SCCS opinions, the CLP hazard table. Folder `corpus/`. |
| **Chunk** | A piece of a document stored in the search index. "Structure-aware" chunks follow the document's own structure (one chunk = one annex entry); "fixed-size" chunks cut every 500 tokens. |
| **Vector index / Qdrant** | The database that stores chunks with their embeddings and finds the closest ones to a question. Qdrant is the program we use. |
| **Annexes II-VI** | Parts of the EU cosmetics regulation. Annex II = **prohibited** substances. Annex III = **restricted** substances (allowed with conditions). Annex IV = colorants, V = preservatives, VI = UV filters (allowed, with conditions). Each substance has an **entry number**, written like "V/29" (Annex V, entry 29 = phenoxyethanol, max 1 %). |
| **INCI name** | The official ingredient name printed on cosmetics in the EU (e.g. `AQUA`, `GLYCERIN`, `SODIUM BENZOATE`). The official list is the EU **CosIng** database. |
| **Normalization** | Turning what is printed on a label ("Aqua/Water/Eau", "Glycerine", "Phenoxyethan0l") into one standard INCI name (`aqua`, `glycerin`, `phenoxyethanol`) so the agents recognise it. |
| **Mock** | Fake code that returns made-up answers so other parts can be built before the real code exists ("Day 1" in our plan). |
| **Docker image** | A packaged copy of a program with everything it needs, which Render runs. We have one for the API and one for n8n. |
| **Environment variable / `.env`** | A setting given to a program from outside its code (e.g. which model to use, the token). Locally they live in `.env` (never committed); on Render they are set in the dashboard. `.env.example` lists them without values. |
| **Pydantic** | The Python library that checks data has the right shape (e.g. that the model's answer is valid JSON with the right fields). |
| **Rule check** | A check written in code (always gives the same answer), e.g. "every claim cites a source". |
| **Validator agent** | An AI agent that re-reads the report and checks each claim against the text of its source. |
| **Test** | Code that checks other code works (`pytest`). On `main` there were 64 tests; now there are 127, all passing. |

---

## 2. The problem we found on `main`

We read every module and ran it (2026-10-17). Each module worked alone, but **they were not connected**:

- **The n8n workflow never called our API's real modules.** Its HTTP nodes called `/v1/product/resolve`, `/v1/label/extract`,
  `/v1/ingredients/normalize` and `/v1/evidence/retrieve`. Those four endpoints (`app/integration/mock.py`) return the same
  made-up product for every request: "Mock Moisturizer" with "Aqua, Glycerin, Parfum, Limonene". The regulatory,
  toxicology, ethics and validator agents in the workflow were separate AI nodes **inside n8n** (running on Ollama, a local
  model server we do not use), with their own prompts. So `/ingestion/extract`, `/regulatory/analyze`, `/toxicology/analyze`,
  `/ethics/analyze`, `/rag/retrieve` and `/report/validate` were never used by the pipeline.
- **Two data formats that never met.** Our modules use `ProductInput` with ingredients named `ingredient` and citations in
  `sources` (docs/STRUCTURE.md). The n8n workflow used `ingredient_id`, `evidence_ids` and `evidence_pack` (docs/CONTRACT.md).
- **Normalization recognised 12 ingredients.** A real product (Balea body lotion, barcode 4066447870213, 15 ingredients) came
  out with **0 of 15 recognised**, not even aqua or glycerin, so every agent answered "not assessed" for everything.
- **Toxicology and ethics are still the Day-1 mocks**: toxicology knows 3 ingredients; ethics says "certified" only for a brand
  literally named "Mock Certified Brand".
- **No label OCR on `main`.** It was written (with Google Gemini) on the old `barcode-and-ocr` branch, but when the code was
  reorganised into `app/ingestion/` on the `barcode-scan` branch, the OCR function was not copied. `barcode-scan` was merged
  (PR #5); `barcode-and-ocr` never was.
- **The regulatory agent could not use the RAG search.** It called `/retrieval/search`, which does not exist (the RAG endpoint is
  `/rag/retrieve`), and expected different field names. With the address fixed, every result would still have been thrown away,
  and methylisothiazolinone in a leave-on cream came out "not restricted": a dangerous wrong answer.

---

## 3. Before and after: how a scan flows

**Before (`main`):**

```
app ──► n8n ──► /v1/* mock endpoints ──► always "Mock Moisturizer"
               └─► 4 AI nodes inside n8n (Ollama, placeholder prompts)
Our real modules (ingestion, regulatory, toxicology, ethics, RAG, report): never called.
```

**Target (this branch; the parts marked ✔ are done, ✘ still to do):**

```
app ──► n8n (✘ workflow still to rewrite)
          │
          ├─► POST /ingestion/scan        ✔ barcode → Open Beauty Facts → ingredient list
          │                               ✔ no list? → label photo → vision model (OCR)
          │                               ✔ every name normalized to its INCI name
          ├─► POST /regulatory/analyze    ✔ EU annexes, found through the RAG search, + Qwen
          ├─► POST /toxicology/analyze    ✘ still the mock
          ├─► POST /ethics/analyze        ✘ still the mock
          ├─► POST /report/build          ✔ merges everything, attaches source text, runs 8 rule checks
          └─► POST /report/validate       ✔ validator agent re-checks each claim
                                          → back to the app: report + status (completed / needs_review)
All AI calls go to the Hugging Face router with HF_TOKEN.
```

---

## 4. Status: what works now and what does not

| Part | State on this branch |
|---|---|
| Deployment files for Render | **Ready** (`render.yaml`, both Docker images built and tested on our computer). Not deployed yet. |
| Barcode lookup | Works (Open Beauty Facts). |
| Ingredient normalization | **Fixed**: 14 of 15 ingredients recognised on the real Balea product (was 0 of 15). |
| Label OCR | **Done**: tested on 2 real label photos (15/15 and 23/25 ingredients, see 5.7). |
| RAG search | **Works online-ready**: no heavy AI library needed, search index shipped with the code, used by the regulatory agent. |
| Regulatory agent | **Fixed and extended**: 41 ingredients covered (was 19). Runs live on a real product. |
| Toxicology agent | **Still the Day-1 mock.** |
| Ethics agent | **Still the Day-1 mock.** |
| Report (`/report/build`) | **Done**, works on the real agent outputs. |
| Validator agent (`/report/validate`) | **Done**, advisory for now (see 5.5). |
| n8n workflow | **Not done**: still the old placeholder. |
| App (frontend) | **Not updated** to the new report format yet. |
| Recorded test scenarios and evaluation write-up | **Not done.** |

Tests: **127 pass** (64 on `main`). AI calls spent on this branch so far: about 35 (each section says how many).

---

## 5. Every change in detail

### 5.1 Deployment on Render

**Before.** There was no way to put the project online. `docker-compose.yml` started n8n with the `latest` version (any
update could break the workflow), an Ollama model server that downloads a 5 GB model (we do not use it: the team model is
on the Hugging Face router), and the workflow had to be imported by hand in the n8n website.

**Now.**

| Service on Render | Plan | What it does |
|---|---|---|
| `cosmetic-scanner-web` | free (static site) | The app's web version. |
| `cosmetic-scanner-n8n` | starter, $7/month | n8n. It needs to stay awake so the app's request is answered right away. |
| `cosmetic-scanner-api` | free | Our FastAPI server with all the modules. |
| `cosmetic-scanner-db` | free (expires after 30 days, enough for the course) | The database n8n needs. |

All four are described in **`render.yaml`**. In Render you choose "New > Blueprint", pick the repository, paste `HF_TOKEN`
once, and Render creates everything. Step-by-step instructions: **`docs/DEPLOY.md`**.

**n8n image (`deploy/n8n/Dockerfile`, `deploy/n8n/start.sh`).** n8n is pinned to version 2.43.7. Every time it starts it
imports the workflow file from git (`deploy/n8n/workflows/*.json`) and turns it on ("publishes" it). So the workflow in git is
always the one that runs, and nobody has to click anything in n8n after a deploy.

**Why we checked memory.** Render's free and $7 plans give 512 MB of memory.
- **API:** the old one installed `sentence-transformers`, which pulls in `torch` (an AI library, 520 MB on disk). The new API
  image does not contain it and uses **86 MB** of memory.
- **n8n:** we ran it limited to 512 MB, like on Render. It started, imported the workflow and settled at 426 MB without crashing.

**Files.** New: `render.yaml`, `deploy/n8n/Dockerfile`, `deploy/n8n/start.sh`, `docs/DEPLOY.md`, `requirements-dev.txt`, `.gitattributes`.
Changed: `Dockerfile` (listens on the port Render gives it), `docker-compose.yml` (same images as Render, no Ollama),
`requirements.txt` (only what the running API needs), `.env.example` (new settings, explained one per line).

`requirements.txt` vs `requirements-dev.txt`: the first is what the API needs to run (installed on Render); the second adds
what you need on your own computer to rebuild the search index, run the corpus scripts and run the tests:
`pip install -r requirements-dev.txt`.

### 5.2 Keys: who may call what

**Before.** Anyone who knew the API's address could call every endpoint, and each call can spend the team's Hugging Face credits.

**Now.** Two keys, both generated by Render:

| Key | Used for | Secret? |
|---|---|---|
| `SCANNER_API_KEY` | n8n → API. If this variable is set, every API request except `/health` must send the header `X-API-Key: <key>`, otherwise the answer is "401 Unauthorized". | Yes. Only n8n and the API know it. |
| `EXPO_PUBLIC_WEBHOOK_KEY` | app → n8n. | No: it is inside the web app, anyone can read it. It only stops casual misuse; it never gives direct access to the API. |

On your computer, without `SCANNER_API_KEY` in `.env`, the API stays open as before. File: `app/main.py` (test: `tests/test_main_auth.py`).

### 5.3 RAG search: no heavy library, index shipped with the code

**Before.**
- To turn a question into numbers (an embedding), the API loaded the `bge-small` model on the computer itself, through `torch`.
  Too heavy for Render's free plan.
- The search index lived in a `data/qdrant` folder that must be built by hand (`python -m app.rag.index`) and was not in git, so
  on Render it would simply not exist (the endpoint answered "503 index not built").
- It contained only Haroun's 25 hand-written summaries, without annex entry numbers.

**Now.**
- **Embeddings come from the Hugging Face router** (same `bge-small` model, same `HF_TOKEN`). We checked the router's numbers are
  identical to the local model's (similarity 1.000000 on test sentences), so nothing changes in the results.
- **The index is shipped with the code**: `corpus/index/evidence_structured.jsonl` (the chunks and their numbers). The API loads
  it into memory when it starts; no disk needed on Render.
- **The index now also contains every EU annex entry** from Kreemi's corpus (one chunk per entry, 30 entries) next to Haroun's
  25 summaries: 55 chunks.
- The local model is still used on your computer to rebuild the index (free):
  `EMBEDDING_BACKEND=local python -m app.rag.index`. Commit the updated `corpus/index/` afterwards.

**Example.** Searching "zinc pyrithione, is it allowed" with the shipped index returns Annex II entry 1670 (prohibited) first,
then the SCCS opinion. Time 0.5 s, without `torch` loaded.

**Files.** `app/rag/store.py`, `app/rag/config.py`, `app/rag/index.py`, `app/rag/chunkers.py`, `app/rag/retrieve.py`, `corpus/index/`.

### 5.4 The report: `POST /report/build`

**Before.** There was no endpoint that puts the three agents' answers together. The validator expected a "draft" in the n8n
format that nothing produces.

**Now.** `POST /report/build` receives exactly what the modules return (`product_input` from ingestion, plus the `regulatory`,
`toxicology` and `ethics` answers) and builds the report the app shows:

- **One card per ingredient** (in label order) with its regulatory status and conditions, hazards, and missing information.
- **Every claim points to its evidence, with the actual text.** Example: the claim "zinc pyrithione is prohibited" points to
  `eu_1223_2009_annex_ii#1670`, whose text is the annex entry itself. Evidence comes from: annex entries (Kreemi's CSV files),
  the coverage list (for "no restriction found"), CLP table rows (toxicology), and the ethics agent's evidence.
- **Overview numbers**: how many prohibited, restricted, conditions not met, concentration unknown, not assessed.
- **8 rule checks** (code, no AI). If one of the "error" checks fails, the report's status is `needs_review` instead of `completed`:

| Check | What it verifies | Level |
|---|---|---|
| agents_present | All three agents answered | warning |
| agent_coverage | Each agent answered once for every ingredient | error |
| citations_known | Every cited source is listed in `corpus/sources.csv` | error |
| citation_subject | A cited source is about that ingredient | warning |
| excerpts_available | Every claim's source has real text (catches "MOCK - replace with retrieved text") | error |
| claims_have_evidence | Statuses, hazards and "certified" claims cite a source | error |
| missing_concentration | A concentration limit is never marked met/broken when the concentration is unknown | error |
| no_safety_verdicts | No "safe", "toxic", "avoid", "illegal" in what the user reads | error |

**Example (real).** For the sample `clean_product`, the report correctly fails two checks: the ethics mock's "Mock Certified
Brand" certification is not a registered source and has no text.

**Files.** `app/report/builder.py`, `app/report/checks.py`, `app/report/sources.py` (new); `app/report/schemas.py`,
`app/report/router.py` (changed). Tests: `tests/test_report_build.py`.

### 5.5 The validator agent: `POST /report/validate`

**What it does.** It sends the AI only the positive claims of the report (e.g. "restricted, Annex V/1, limit 0,5 %"), the text
of the sources they cite, and the product type (leave-on / rinse-off). The AI answers, claim by claim: supported, overstated or
unsupported. The answer is added to the report as one more check, `ai_validator`.

**Decisions, each based on a real test:**
- **It is advisory for now** (setting `VALIDATOR_BLOCKING=false`). Its doubts are shown as warnings; the 8 rule checks decide
  `completed` / `needs_review`. Why: on real reports the 7B model wrongly called correct findings "overstated", for example the
  methylisothiazolinone restriction (3 runs out of 3), and it read piroctone olamine's "0,5 % for other products" as the
  rinse-off limit. If it could block reports, the products most worth showing would always be held back.
  Set `VALIDATOR_BLOCKING=true` once a better prompt passes the evaluation.
- **"Nothing found" statements are not sent to it** ("no restriction found", "no certification found"): it flagged them as
  "unsupported" because they cite nothing, but there is nothing to cite.
- **Claims it invents are ignored**: once it judged "The product is cruelty-free", a sentence the report never contained.
- **It sees the product type**, because claims like "rinse-off only, this product is leave-on" depend on it.
- If the AI service is down, the report still comes back, with a warning.

**Prompts.** `prompts/validator/v1.yaml` to `v4.yaml`, each with its observed failures. Results: `eval/validator/results/`.

**Files.** `app/report/agent.py`. Tests: `tests/test_report_build.py`, `tests/test_report_validator.py`.

### 5.6 Ingredient normalization (Muaadh's module)

**Before.** `app/ingestion/known.py` listed 12 ingredients and 13 aliases.
- "Recognised" meant "one of those 12": aqua, glycerin, sodium benzoate, parfum... were all "not recognised".
- The aliases "water → aqua" and "fragrance → parfum" pointed at names that were not in the list, so they did nothing.
- Methylparaben (allowed with a limit) and isopropylparaben (**banned** in the EU) were both turned into "parabens": the agents
  could not tell them apart.
- For an unknown name, "confidence" was its similarity to the nearest wrong ingredient (Benzophenone-4 got 0.93 because it
  looks like Benzophenone-3).
- The list was split on commas only: "Aqua; Glycerin" or one ingredient per line became one single ingredient.
- An OCR typo like "Phenoxyethan0l" (zero instead of O) was rejected.

**Now.**
- **A real dictionary of 22,183 official ingredients** (33,886 names with their synonyms in several languages: water / eau /
  wasser → aqua). It comes from the Open Beauty Facts ingredient list, which is built from the EU CosIng database (open licence,
  ODbL). Built by `scripts/build_inci_dictionary.py` into `app/ingestion/data/inci_dictionary.json.gz` (362 KB).
- "Recognised" now means "a real INCI ingredient". Whether our corpus covers it is each agent's job.
- Splitting handles `,` `;` `. ` bullets and new lines (not inside brackets), removes "Ingredients:" and `*` marks, keeps
  "may contain" colorants.
- Typo tolerance: "Phenoxyethan0l" → phenoxyethanol (confidence 0.95). Numbered names are never swapped (benzophenone-3 stays -3).
- Confidence means "how sure we are of this name": 1.0 exact, 0.9-0.99 for a typo match, 0 when unknown.
- "Needs review" is only set when a name is unknown or uncertain.

**Example (real).** Balea body lotion: **14 of 15 recognised** (was 0), including the label's own typos ("Hybride Oil" →
hybrid oil, "Ethylhexyl Sterate" → ethylhexyl stearate). The one missed, hydrogenated castor oil, is missing from the
dictionary itself; such names come out "not recognised", never wrongly matched.

**Other fixes in `app/ingestion/extract.py`:**
- The barcode must be 8-14 digits. Before, a "barcode" like `../../samples/input/x` could read any JSON file of the project.
- If Open Beauty Facts cannot be reached, the scan says "barcode not found" instead of crashing.
- Many products have no category on Open Beauty Facts; the product name is used instead ("Bodylotion" → leave-on), so the
  leave-on / rinse-off rules can still be checked.

**Files.** New: `app/ingestion/normalize.py`, `scripts/build_inci_dictionary.py`, `app/ingestion/data/inci_dictionary.json.gz`.
Removed: `app/ingestion/known.py`. Tests: `tests/test_normalize.py`, `tests/test_ingestion.py`.

### 5.7 Label OCR (new)

**Before.** No OCR on `main` (see section 2).

**Now.** When the barcode gives no ingredient list, the label photo is read by a vision model:
`Qwen/Qwen3-VL-30B-A3B-Instruct`, through the Hugging Face router with the same `HF_TOKEN` (setting `OCR_MODEL`).

How it works (`app/ingestion/ocr.py`):
1. The photo is turned upright and shrunk to at most 1600 pixels (enough to read small print, fewer credits).
2. The model copies the ingredient list exactly as printed, in order, plus brand, product name and product type if visible.
   It answers in JSON, checked with Pydantic (one retry if the format is wrong). Prompt: `prompts/ocr/v1.yaml`.
3. The names go through normalization (5.6). Names the model was unsure of get confidence 0.7, so the agents mark them
   "unverified" and the report asks for a review.

**Why this model.** PaddleOCR is not available through Hugging Face (it would need a paid server). `Qwen2.5-VL-7B` answered
"at capacity, try again" twice in a row in our test; `Qwen3-VL-30B` (three providers behind it) answered in 3.5 s.
It uses the shared credits, so the team lead should know about it (Omar is telling them); it only runs when the barcode lookup has no ingredients.

**How to call it.**
- `POST /ingestion/scan` (new, JSON, for n8n): `{"barcode": "...", "barcode_image_ref": "...", "label_image_ref": "..."}`.
  Image refs are `data:image/jpeg;base64,...` (what the app sends) or an `https://` link; max 10 MB.
- `POST /ingestion/extract` (file uploads, for testing in `/docs`) now also accepts `label_image`.

**Test on real label photos** (user photos from Open Beauty Facts, compared with the ingredient text typed in the database):

| Product | Time | Result |
|---|---|---|
| Balea body lotion (German label) | 11 s | **15 of 15 identical**; brand and product type ("Körperlotion" → leave-on) read correctly |
| CeraVe foaming cleanser (Swedish label) | 17 s | 23 of 25 the same. The photo kept "PEG-6 Caprylic/Capric Glycerides" as one ingredient where the database text had split it; the photo shows sodium hyaluronate and not sodium hydroxide / tocopherol, which may be a different version of the label |

**Files.** New: `app/ingestion/ocr.py`, `prompts/ocr/v1.yaml`, `tests/test_ocr.py`. Changed: `app/ingestion/extract.py`,
`app/ingestion/router.py`, `app/common/llm.py` (`chat()` accepts a `model` to use for one call; the agents are unaffected).
AI calls used: 2 (+3 during the model choice).

### 5.8 Regulatory agent (Kreemi's module)

#### a) More ingredients covered: 19 → 41

**Before.** The regulatory corpus covered 19 ingredients. Common preservatives found in real products (sodium benzoate,
potassium sorbate, piroctone olamine...) were "not assessed", even though they are in Annex V.

**Now.** 13 annex entries added, copied from the official consolidated regulation already in the repo
(`corpus/raw/eu_1223_2009.pdf`, EUR-Lex version of 18 May 2026). Each substance was also searched in the whole document to make
sure no other entry was missed (that is how benzyl alcohol's second entry, III/45, was found). Kreemi's existing rows were not changed.

| Entry | Substances | Condition |
|---|---|---|
| V/1 | benzoic acid, sodium benzoate | rinse-off (not oral) 2,5 %; oral 1,7 %; leave-on 0,5 % |
| V/4 | sorbic acid and its salts (potassium, sodium, calcium sorbate) | 0,6 % |
| V/12 | methylparaben, ethylparaben and their salts | 0,4 % one ester; 0,8 % mixtures |
| V/13 | dehydroacetic acid, sodium dehydroacetate | 0,6 %; not in sprays |
| V/34 and III/45 | benzyl alcohol | 1,0 % as a preservative; for other uses (e.g. fragrance) it must be named on the label above 0,001 % (leave-on) / 0,01 % (rinse-off) |
| V/35 | piroctone olamine | rinse-off 1,0 %; other products 0,5 % |
| V/50 | chlorphenesin | 0,3 % |
| II/1374-1378 | isopropyl-, isobutyl-, phenyl-, benzyl-, pentylparaben | **prohibited** |

The 22 new ingredients were added to `corpus/regulatory/regulatory_scope.csv` (the list of ingredients the agent covers), and
the ingredient column of the annex rows in `corpus/sources.csv` is now rebuilt from the actual rows.

#### b) Concentration reaches the agent

**Before.** The agent tried to read `concentration_percent`, but the shared ingredient format (`app/common_schemas.py`) had no
such field, so it was silently removed before the agent saw it. A concentration limit could never be checked.

**Now.** `concentration_percent` is an optional field of each ingredient (labels rarely give it, so it is usually empty). When it
is given and the limit is a single number ("1,0 %"), the code compares them itself. Limits with several values (by product type
or for mixtures) are left to the AI. A limit decided by the code cannot be overwritten by the AI.

**Example.** Phenoxyethanol at 0,8 % in a cream → Annex V/29 limit 1,0 % → "satisfied: 0.8 % is within the 1 % limit".

#### c) Matching the product type to the annex wording

**Before.** Two bugs in `app/regulatory/rules.py`:
- For an entry like salicylic acid's "(b) Other products **except** body lotion, eye shadow, mascara...", every word of the
  excluded products was put in one bag, and the product was excluded if it shared **any one word**. So a "body **cream**" was
  excluded because of "body **lotion**", and salicylic acid in body creams, eye creams and body milks came out "condition not met": wrong.
- When the product matched none of the listed types, the answer was "not allowed". A "sunscreen" is neither "face products"
  nor "body products" by name, so homosalate in a sunscreen came out "not allowed", when the truth is "unknown".

**Now.** An excluded product counts only if all its words match ("body lotion" excludes body lotions, not body creams).
"Not allowed" is only given when every option clearly excludes the product (leave-on vs rinse-off, an exclusion list, or a
different body part, e.g. a body spray for a face-only entry). Otherwise the answer is "unknown". Toothpaste and mouthwash
now count as "oral products". 17 test cases, all correct.

#### d) The agent now searches through RAG

**Before.** The setting `RETRIEVAL_BACKEND=http` called an address that does not exist (see section 2), so the agent always
read the CSV files directly (`local`) and the RAG search was never used by an agent.

**Now.** Three ways to search, chosen by `RETRIEVAL_BACKEND`:
- `rag` (used on Render): the RAG search index, inside the same API.
- `http`: the RAG endpoint over the network (`/rag/retrieve`, with the API key), if retrieval is ever deployed separately.
- `local`: read the CSV files directly (tests, offline work).

We checked that `rag` returns exactly the same annex entries as reading the CSV, for all 19 covered ingredients in the samples.

#### e) No crash without a token

**Before.** In live mode, if no `HF_TOKEN` was set, `/regulatory/analyze` crashed (error 500).
**Now.** It answers with the rule-based result and the warning "LLM unavailable".

**Real test (live, 4 AI calls).** Balea body lotion: barcode → normalization → regulatory agent (Qwen + RAG) → report →
validator, in **13 seconds**. Results: sodium benzoate V/1 (leave-on limit 0,5 %), piroctone olamine V/35 (0,5 % for "other
products"), potassium sorbate V/4 (0,6 %), all "conditions unknown" because the label gives no concentration. Qwen claimed
potassium sorbate's limit was "not met" with no concentration known; the safety rule corrected it to "unknown".

**Tests changed and why.** Some of Kreemi's tests checked the old corpus on purpose ("sodium benzoate is not covered",
"3 AI calls"). Sodium benzoate is now covered (Annex V/1), so they were updated, with the reason written next to the change.
The evaluation answer key `eval/regulatory/gold.json` was updated for the same ingredient. New tests: product-type cases,
concentration, new entries, missing token, both search methods.

**Files.** `app/regulatory/rules.py`, `app/regulatory/agent.py`, `app/regulatory/retrieval.py`, `app/common_schemas.py`,
`corpus/regulatory/*.csv`, `corpus/sources.csv`, `eval/regulatory/gold.json`, `tests/test_regulatory.py`, `tests/test_regulatory_agent.py`.

### 5.9 Small fixes that would have broken the deployment

| File | Before | Now | Why |
|---|---|---|---|
| `.gitignore`, `.dockerignore` | `data/` (any folder named "data") | `/data/` (only the one at the project root) | The old rule also hid `app/ingestion/data/inci_dictionary.json.gz`. It would never have reached GitHub or Render, and normalization would have crashed online. Checked: the rebuilt API image contains it. |
| `.gitattributes` (new) | – | Shell scripts and Dockerfiles always use Linux line endings | The n8n start script would not run on Render if committed from Windows with Windows line endings. |
| `frontend/.env.example`, `frontend/src/scan/client.ts` | `EXPO_PUBLIC_API_KEY` | `EXPO_PUBLIC_WEBHOOK_KEY` | Makes clear it is the public app key, not the secret API key. |

---

## 6. What this means for your module

**Muaadh (barcode, OCR, normalization).** `known.py` is replaced by a real dictionary (5.6). OCR now exists in
`app/ingestion/ocr.py` with the team's Hugging Face token instead of Gemini (5.7). New endpoint `/ingestion/scan` for n8n. Your
old tests asserted the old behaviour (aqua not recognised) and were updated. `samples/input/*.json` were hand-written and do not
match what the code produces (e.g. "Water" matched=true at 0.62); they still work as test inputs.

**Haroun (RAG).** Your search now uses the Hugging Face router for embeddings (same model, identical numbers), and the index is
shipped in `corpus/index/` (5.3). The index also contains Kreemi's annex entries as structure-aware chunks, and the regulatory
agent now uses your search (5.8 d). Your evaluation (`eval/rag/`) is not changed yet; known issues: the documented command
`python eval/rag/run_eval.py` fails (path), `metrics.csv` comes from an older run, 11 questions (plan: 10-25).

**Kreemi (regulatory).** 13 annex entries added, 41 ingredients in scope, concentration field, product-type matching fixed,
search through RAG, no crash without a token (5.8). Please re-check the new CSV rows against the PDF if you want a second pair of eyes.

**Hind (toxicology, ethics).** Your modules are unchanged and still the Day-1 mocks: they are next on our list.
The report already replaces the mock's "MOCK - replace with retrieved text" quotes with the real CLP table row when it can.
For everyone: a second model is now used, for OCR only: `Qwen/Qwen3-VL-30B-A3B-Instruct` (label-photo path). The shared client
`app/common/llm.py` got one optional parameter (`model`); nothing else changed in it.

**Lyna (n8n, deployment).** `app/main.py` now checks an API key when `SCANNER_API_KEY` is set (5.2). The n8n image and
`render.yaml` are new (5.1); `docker-compose.yml` no longer starts Ollama. The workflow itself is not changed yet: the plan is to
replace the `/v1/*` mock nodes and the four AI nodes by HTTP calls to `/ingestion/scan`, `/regulatory/analyze`,
`/toxicology/analyze`, `/ethics/analyze`, `/report/build`, `/report/validate`.

---

## 7. Still to do

1. Toxicology and ethics: real agents instead of the mocks (CLP table and SCCS texts through RAG; Open Beauty Facts labels and a certification list).
2. n8n workflow: the HTTP chain above; remove the `/v1/*` mock path, the four AI nodes, `deploy/n8n/nodes/report/*.js` and `scripts/install_report_nodes.py` (made obsolete by `/report/build`).
3. App: show the new report format; send photos as `label_image_ref`.
4. Validator prompt v5 (use the product type, read lettered options correctly), tested on real reports.
5. The five end-to-end scenarios from the plan (barcode found, OCR fallback, unknown ingredient, missing concentration, no cruelty-free evidence), recorded; evaluation and prompt-comparison write-up.
6. Deploy on Render and run the scenarios online.
