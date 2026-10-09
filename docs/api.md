# API

OpenAPI: `GET /openapi.json`; interactive docs: http://localhost:8000/docs. All operational endpoints use `/api/v1`.

Authenticate using `Authorization: Bearer <PULSE_ADMIN_TOKEN>`, or POST `/api/v1/session` with `{"token":"..."}` to receive a signed HttpOnly `pulse_session` cookie valid for 12 hours. Browser mutations using cookies must include the configured exact Origin (`http://localhost:3000` by default). CLI Bearer requests do not require Origin. DELETE `/api/v1/session` signs out.

GET `/api/v1/health` is public and reports API status, Docker connectivity, last successful poll time, and whether a model is configured. It does not claim Docker is available just because the API starts. All telemetry, logs, incidents, settings, audit, chat, and SSE routes require authentication.

GET `/overview` returns database-wide monitored/healthy service counts, active incidents, pending approvals, and verified recoveries in the last 24 hours. Counts are independent of the newest-100 incident listing limit.

## Services

- GET `/services`: discovered containers, current snapshot, operator permissions, latest collected sample.
- GET `/services/{id}`: persisted service metadata.
- PATCH `/services/{id}/permissions`: full `{"monitored":true,"remediation_allowed":false}`. Remediation requires monitoring. This does not approve any action.
- GET `/services/{id}/metrics?limit=120`: collected samples in chronological order; monitoring required; limit 1–360.
- GET `/services/{id}/logs?limit=100`: fresh, bounded, redacted Docker logs via the audited tool registry; monitoring required; limit 1–300.

Service IDs are database UUIDs; Docker container IDs remain in snapshots. Tools reject a resource different from their affected service. The gateway validates Docker IDs and revalidates its label allowlist.

## Incidents

- GET `/incidents`: newest 100 incidents and operational question investigations.
- GET `/incidents/{id}`: metadata, diagnosis, action proposals/outcomes, evidence/tool executions, verification result.
- GET `/incidents/{id}/timeline`: persisted chronological events.
- GET `/incidents/{id}/similar?q=optional-text`: structured service/type match plus PostgreSQL full-text search when a query is supplied. SQLite development falls back to structured attributes.
- POST `/incidents/{id}/investigate`: accepted only in DETECTED, FAILED, DIAGNOSED, or AWAITING_APPROVAL; invalidates pending proposals; asynchronously starts an investigation.
- POST `/incidents/{id}/dismiss`: `{"reason":"reviewed and dismissed"}`; disallowed during active investigation/execution/verification.

Lifecycle: DETECTED → INVESTIGATING → DIAGNOSED → AWAITING_APPROVAL → REMEDIATING → VERIFYING → RESOLVED. Invalid transitions return a conflict/error. FAILED permits reinvestigation/dismissal. Dismissal records a reason and does not claim recovery.

Diagnoses separate `observation`, `supported_hypothesis`, and `unverified_possibility`. Findings link to evidence UUIDs. Low/medium/high confidence is an uncalibrated qualitative label. Verification includes `confirmed`, `failed`, or `inconclusive` and the actual sample sequence.

## Remediation

- POST `/remediations/{id}/approve`: `{"action_digest":"64-character sha256 from proposal"}`. Returns 202 after consuming one approval and scheduling execution, not after declaring recovery.
- POST `/remediations/{id}/reject`: consumes only a still-pending proposal and audits rejection. Inspect/reinvestigate/dismiss the incident as needed.

Every mutation is revalidated again immediately before execution. Expiration, permission revocation, changed identity/status, an emergency disable, prior approval/execution, or a mismatched digest prevents execution. Gateway timeouts or worker crashes are not automatically retried. Fetch incident detail/timeline for the result. Start/restart are the only V1 infrastructure mutations.

## Assistant and configuration

POST `/chat` takes `{"message":"Why is this service restarting?","service_id":"uuid"}` and returns an investigation UUID. The worker retrieves genuine evidence; poll incident detail or subscribe to SSE. Operational questions do not automatically propose or execute remediation.

GET `/settings` returns runtime thresholds/budgets, model name, configured status, and sanitized provider base URL. No API keys are returned. PATCH `/settings` accepts a complete runtime Settings object or a validated subset of its fields; omitted fields retain their stored values. Provider secrets/model routing are environment-managed and require restart.

GET `/activity` returns the latest 30 non-telemetry events. GET `/audit` returns the latest 100 operator/worker audit records. Authenticated GET `/metrics` exposes real per-container CPU/memory gauges for Prometheus, omitting stale samples.

## SSE

GET `/events?after=0`, authenticated with the same session or Bearer credential. Browser EventSource uses the same-origin Next.js proxy and its HttpOnly cookie.

- `event: sync` asks the client to fetch authoritative REST state on connection/reconnection.
- `event: pulse` contains a persisted event with its increasing `id`, kind, payload, incident UUID, and timestamp.
- `id:` is the replay cursor. Send `Last-Event-ID` or `after` to replay later events.
- Heartbeat comments keep idle connections alive; they do not represent investigation progress.

The dashboard stores its last cursor for the browser session and invalidates relevant cached state on actual events. Backend events cover detection, transitions, evidence/tool completion, diagnosis, proposals, settings/permission changes, and recovery observations/results. State fetches provide reconnection synchronization; periodic REST refetch is a fallback.

Validation failures use 422; missing resources 404; unauthenticated requests 401; denied resource/origin operations 403; stale/duplicate approvals 409; unavailable Docker logs/revalidation 503; rate limits 429. API rate limiting is process-local (180 requests/minute/IP and 5 login attempts/minute/IP), designed for the localhost installation.
