FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Keep dependency installation cache-friendly: requirements change less often than source code.
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Browser dependencies are only needed when RAG_URL_PARSER_BACKEND=crawl4ai.
# Default build stays lighter for the standard/basic RAG URL parser.
ARG INSTALL_BROWSER_DEPS=false
RUN if [ "$INSTALL_BROWSER_DEPS" = "true" ]; then \
      python -m playwright install --with-deps chromium && \
      (python -m patchright install --with-deps chromium || true); \
    fi

COPY apps/api /app

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
