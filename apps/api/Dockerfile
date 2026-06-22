FROM python:3.12-slim

WORKDIR /app
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Nécessaire uniquement quand RAG_URL_PARSER_BACKEND=crawl4ai.
# Le backend par défaut reste basic.
RUN python -m playwright install --with-deps chromium \
    && (python -m patchright install --with-deps chromium || true)

COPY apps/api /app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]