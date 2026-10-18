FROM python:3.12-slim
WORKDIR /code
# pyzbar (barcode images) needs the zbar system library
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 && rm -rf /var/lib/apt/lists/*
# Runtime dependencies only: no torch. Embeddings and LLM calls go through the HF router.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# The agents read the corpus (including the exported RAG index in corpus/index/), prompts and samples at runtime.
COPY corpus ./corpus
COPY prompts ./prompts
COPY samples ./samples
# Render sets PORT (default 10000); docker-compose and local runs use 8000.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
