FROM python:3.12-slim
WORKDIR /code
# pyzbar (barcode images) needs the zbar system library
RUN apt-get update && apt-get install -y --no-install-recommends libzbar0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# The agents read the corpus, prompts and samples at runtime.
COPY corpus ./corpus
COPY prompts ./prompts
COPY samples ./samples
# Real entry point: app.main includes every module's router.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
