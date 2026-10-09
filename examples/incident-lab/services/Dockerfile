FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /bin/uv
ENV UV_NO_CACHE=1 PYTHONUNBUFFERED=1 SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
WORKDIR /app
COPY --chmod=0644 requirements.lock /app/requirements.lock
RUN --mount=type=secret,id=cloud_ca \
    set -eu; if [ -s /run/secrets/cloud_ca ]; then cp /run/secrets/cloud_ca /etc/ssl/certs/ca-certificates.crt; chmod 644 /etc/ssl/certs/ca-certificates.crt; fi; \
    uv pip sync --system --require-hashes /app/requirements.lock && \
    useradd --uid 10002 --create-home demo && mkdir /data && chown demo:demo /data
COPY --chmod=0644 demo-api/app.py /app/app.py
USER demo
CMD ["python", "/app/app.py"]
