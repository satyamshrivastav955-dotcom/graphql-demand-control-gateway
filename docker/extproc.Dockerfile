# syntax=docker/dockerfile:1
# Sentinel as an Envoy external processor (gRPC on :9001, Prometheus on :9102).
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY backend/requirements.txt backend/requirements-extproc.txt ./
RUN python -m venv /opt/venv && /opt/venv/bin/pip install -r requirements-extproc.txt

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
RUN useradd --system --uid 10001 --no-create-home sentinel
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY sentinel_core ./sentinel_core
COPY backend ./backend
USER sentinel
EXPOSE 9001 9102
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9102/health', timeout=2)"]
CMD ["python", "-m", "backend.integrations.envoy_extproc", "--port", "9001", "--metrics-port", "9102"]
