# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
# The optional mount supports cloud sessions with an HTTPS proxy CA.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --no-audit --no-fund --strict-ssl=true
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.lock ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.lock
COPY --chown=10001:10001 server.py cad_core.py ./
COPY --chown=10001:10001 legacy/static/ ./legacy/static/
COPY --from=frontend --chown=10001:10001 /build/dist/ ./frontend/dist/
ENV PYTHONUNBUFFERED=1 XDG_CACHE_HOME=/tmp/.cache PORT=10000
USER 10001:10001
EXPOSE 10000
CMD ["sh", "-c", "exec python -m uvicorn server:app --host 0.0.0.0 --port \"${PORT:-10000}\" --workers 1"]
