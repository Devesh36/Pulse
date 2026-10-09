# Contributing to Pulse

Use Python 3.12+, uv, and Node 22+. Follow README setup before running integrations. Keep tests isolated from production infrastructure.

Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -q`, `npm run typecheck --prefix apps/web`, and `npm run build --prefix apps/web` before submitting changes. Include a targeted test for policy, lifecycle, or investigation behavior changes. Mock model calls; mark real integrations opt-in.

Keep telemetry detection deterministic. Keep model access read-only and scoped to monitored resources. Infrastructure mutations belong in the restricted gateway behind policy validation, one-time human approval, an audit trail, and recovery verification. Do not add generic shell, exec, file reads, container creation/deletion, or arbitrary URL/PromQL tools.

Preserve evidence IDs, distinguish observations from hypotheses, and state uncertainty. Never use a successful mutation response as proof of recovery. Never seed fake operational data in the dashboard. Use explicit test doubles only in tests.

Schema changes require a new frozen Alembic revision, including PostgreSQL upgrade validation. Existing migrations must not import live ORM metadata. Keep credentials out of logs, API responses, example files, screenshots, commits, and fixtures.

Open a focused pull request describing the problem, resulting behavior, test evidence, and any remaining limitations. Update documentation when installation, capabilities, or safety assumptions change. This project uses the MIT license; contributions are under that license.
