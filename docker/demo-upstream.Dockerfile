# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install fastapi==0.141.1 uvicorn==0.52.1 graphql-core==3.2.12 \
    && useradd --system --uid 10001 --no-create-home demo
WORKDIR /app
COPY demo ./demo
USER demo
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2)"]
CMD ["uvicorn", "demo.upstream.app:app", "--host", "0.0.0.0", "--port", "8001"]
