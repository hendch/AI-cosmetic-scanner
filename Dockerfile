FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# Real entry point: app.main includes every module's router.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
