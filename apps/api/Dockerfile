FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY apps/__init__.py ./apps/__init__.py
COPY apps/api ./apps/api
COPY alembic.ini ./
RUN uv sync --frozen --no-dev && useradd --uid 10001 --create-home pulse
USER pulse
EXPOSE 8000
CMD ["/bin/sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync python -m apps.api.serve --host 0.0.0.0 --port 8000"]
