FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /bin/
WORKDIR /app
ENV UV_NO_CACHE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY alembic.ini ./
RUN --mount=type=secret,id=cloud_ca \
    set -eu; if [ -s /run/secrets/cloud_ca ]; then cp /run/secrets/cloud_ca /etc/ssl/certs/ca-certificates.crt; chmod 644 /etc/ssl/certs/ca-certificates.crt; fi; \
    uv sync --frozen --no-dev && \
    useradd --uid 10001 --create-home pulse && chmod -R a+rX /app
USER pulse
EXPOSE 8000
CMD ["/bin/sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync python -m apps.api.serve --host 0.0.0.0 --port 8000"]
