# Troubleshooting

## Docker adapter is disconnected

Run `docker version` and `docker compose version`. Both the daemon and Compose v2 must work. Check `docker context ls`; macOS may have a stale Desktop context when Docker Desktop is absent. Pulse does not install or repair virtualization software.

On the implementation host, Docker Desktop was missing, Compose plugin links pointed into the missing app, and Colima failed with “limactl is running under rosetta.” Install/repair a native Docker Desktop or native Colima/Lima installation and select its running Docker context before trying the real demo. No real Docker acceptance success is claimed in that environment.

Inspect `docker compose logs gateway api` locally. The gateway requires its unique token and access to the selected daemon's socket. Override `DOCKER_SOCKET_PATH` for a nonstandard Unix socket. Do not make the gateway publicly reachable to solve connectivity.

## No services / no samples

Only containers with `pulse.monitor=true` are discoverable. Recreate a Compose container after adding labels; labels are immutable during its lifetime. Check the **Services** inspector to confirm monitoring has not been turned off. Stale services may remain in history; current availability and `last_seen` must be checked before acting.

Unrestricted container metadata, environment variables, and all-host resource enumeration are deliberately absent. Memory percentages need a meaningful container memory limit.

## API fails at startup

Run `uv run python scripts/setup-env.py`. Administrator and adapter secrets must be distinct and at least 16 characters. The database must be reachable and migrated. Compose runs `alembic upgrade head` before API startup; native development must run it explicitly.

If changing PostgreSQL's password after the volume exists, changing `.env` alone does not rotate the database user. Preserve data and rotate credentials through PostgreSQL, or deliberately recreate only a disposable development database. Do not use `down -v` when incident history is needed.

## Frontend says API is unreachable

The web server proxies to `PULSE_API_URL` (default `http://127.0.0.1:8000`; Compose uses `http://api:8000`). Ensure the API is listening. A healthy frontend does not imply connected Docker telemetry. Authenticate with the current local administrator token. Changing the token invalidates existing sessions.

Use `localhost:3000` when `PULSE_WEB_ORIGIN=http://localhost:3000`. Cookie-authenticated mutations at `127.0.0.1:3000` are a different Origin; either use localhost or update the exact configured origin and restart the API. This is a deliberate CSRF check.

## Model uses evidence fallback

Check model name, API key, provider account access, endpoint connectivity, and function-calling support. Set `PULSE_LLM_MODEL`, `PULSE_LLM_API_KEY`, and optionally `PULSE_LLM_API_BASE`; recreate the API after changes. An empty model selects deterministic evidence mode. Invalid output, unavailable tools/provider, timeouts, and exhausted budgets also preserve evidence and label fallback explicitly.

Do not expose a local model endpoint publicly. The API container's `localhost` is the container itself; use a reachable approved host address or internal container DNS.

## Latency/errors never trigger

The included app emits real `demo_http_requests_total` and `demo_http_duration_seconds` metrics for the work endpoint. Confirm the demo target is up in Prometheus, that there are multiple scrapes, and that actual requests are being made. The demo has a real self-request workload.

Queries use the `com.docker.compose.service` label as the metric service name. Other applications need matching instrumentation or a server-side query adapter. Empty/NaN results mean unavailable evidence, not a measured zero. Thresholds require the configured consecutive observations. Rolling rates/p95 may take a window to fall after reset/restart; verification accounts for aging.

## Approval rejected / verification failed

Enable service remediation permission separately, ensure development/remediation labels are present, and approve the latest unexpired action digest. Recreated containers have a new identity; old proposals cannot target them. Duplicate approval is a conflict. Emergency disable prevents policy approval/execution.

Start applies only to a stopped container; restart only to a running one. A state change between diagnosis and execution may require a fresh investigation. Reinvestigation invalidates older pending proposals. Advisory diagnostic/configuration recommendations have no automatic infrastructure mutation.

Recovery must remain healthy for the observation window after startup grace. Increased restarts, persistent high resource usage, unhealthy checks, bad probe responses, or missing telemetry prevent confirmation. An action that times out or is interrupted may have changed Docker; inspect actual state before requesting a new proposal. Automatic retries are intentionally absent.

## Tests

`uv run pytest -q` uses isolated test databases/adapters and mocked model decisions. PostgreSQL/Docker integrations skip unless their opt-in variables are set. `scripts/e2e.py` requires a running full Compose demo. Distinguish a skipped or adapter-backed test from a real acceptance result.
