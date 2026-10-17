# Project structure

One FastAPI app, one module per person. Each person owns their module folder; Lyna (integration) owns the main entry point and deployment.

```
AI-cosmetic-safety/
├── app/
│   ├── common_schemas.py      # shared input format (product + ingredients from barcode/OCR)
│   ├── dev_server.py          # local test server (temporary; the real entry point is Lyna's)
│   ├── toxicology/            # Hind
│   │   ├── schemas.py         # Pydantic output schema
│   │   ├── mock.py            # mock agent (Day 1), replaced by the real agent on Day 2
│   │   └── router.py          # POST /toxicology/analyze
│   ├── ethics/                # Hind, same layout as toxicology/
│   └── <your_module>/         # e.g. regulatory/, retrieval/, ingestion/, report/
├── prompts/
│   ├── toxicology/v1.yaml     # one folder per agent, one file per prompt version
│   └── ethics/v1.yaml
├── samples/
│   ├── input/                 # example inputs (same format as the barcode/OCR output)
│   ├── toxicology/            # example outputs per agent, generated from the mocks
│   └── ethics/
├── corpus/
│   ├── sources.csv            # index of every corpus file (one row per file)
│   ├── toxicology/
│   │   ├── sccs/              # SCCS opinion PDFs
│   │   └── clp/               # CLP classification table
│   └── <your_area>/           # e.g. regulatory/
├── scripts/                   # one-off / data-building scripts (run with python -m scripts.<name>)
├── tests/                     # pytest tests, one file per module
├── docs/
├── requirements.txt
└── .gitignore
```

## Conventions

### Modules
Each module in `app/<module>/` has:
- `schemas.py`: Pydantic models for the module's output.
- `router.py`: a FastAPI `APIRouter` with prefix `/<module>`, e.g. `POST /regulatory/analyze`.
- `mock.py` on Day 1, so n8n can run end to end before the real logic exists.

Lyna's main app includes every module's router. To test locally, add your router to `app/dev_server.py`.

### Shared input
`app/common_schemas.py` holds `ProductInput`, the barcode/OCR output (product, brand, category, labels, ingredients). Agents take it as-is, so n8n passes it through without transforming it. Change it only after agreeing with Muaadh.

### Shared output fields
Agents use the same names for the same things:

| Field | Meaning |
|---|---|
| `ingredient` | Normalized INCI name, lowercase (e.g. `salicylic acid`) |
| `sources` | List of `source_id`s the finding relies on |
| `evidence_confidence` | `high` / `medium` / `low` |
| `missing_information` | e.g. `["concentration"]` |
| `warnings` | Copied from the input, so the report can show them |

### Prompts
- Stored as `prompts/<agent>/v<N>.yaml`, with fields `id`, `version`, `date`, `author`, `description`, `model_params`, `system`, `user` and `known_failures`.
- A new version is a new file. Don't overwrite old versions, since we compare them in the report.

### Corpus and citations
- Every corpus file gets a row in `corpus/sources.csv`.
- The `source_id` is the filename without its extension (e.g. `sccs_phenoxyethanol_2016`).
- Retrieval stores the `source_id` and ingredient name in each chunk's metadata and returns them. Agents cite `source_id`s, and the report checks citations against them.
- Files whose licence doesn't allow redistribution go in `.gitignore` (the repo is public), with their download link in `sources.csv`.

### Samples and tests
- Keep 2–3 example outputs of your module in `samples/<module>/`, so others can build against them.
- Write a test in `tests/` that checks your endpoint returns output matching your schema.

## Running locally

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.dev_server:app --reload      # API docs at http://127.0.0.1:8000/docs
pytest -q
```

Add any new dependencies to `requirements.txt`.
