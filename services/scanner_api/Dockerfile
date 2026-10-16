FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Teammates: replace mock_service:app with the real app (e.g. main:app) here.
CMD ["uvicorn", "mock_service:app", "--host", "0.0.0.0", "--port", "8000"]
