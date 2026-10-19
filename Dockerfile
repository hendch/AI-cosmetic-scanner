FROM python:3.12-slim
WORKDIR /code
# pyzbar (barcode images) needs the zbar system library
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 && rm -rf /var/lib/apt/lists/*
# Runtime dependencies only: no torch. Embeddings and LLM calls go through the HF router.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# PETA brand list for the ethics agent, scraped at build time into /code/data/peta_brands.json (not in git:
# the repo is public). Docker caches this step, so it only reruns when the script or requirements change;
# "Clear build cache & deploy" on Render refreshes the list. If PETA cannot be reached the build continues
# and the agent reports "not verified" with a warning.
COPY scripts/__init__.py scripts/build_peta_brands.py ./scripts/
RUN python -m scripts.build_peta_brands > /tmp/peta.log 2>&1 && tail -n 1 /tmp/peta.log \
    || (tail -n 5 /tmp/peta.log; echo "WARNING: PETA brand list not built; the ethics agent will report not verified")
COPY app ./app
# The agents read the corpus (including the exported RAG index in corpus/index/), prompts and samples at runtime.
COPY corpus ./corpus
COPY prompts ./prompts
COPY samples ./samples
# Render sets PORT (default 10000); docker-compose and local runs use 8000.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
