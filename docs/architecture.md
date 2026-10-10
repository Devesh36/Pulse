# Architecture

Pulse is a modular monorepo with one API/worker process and a separate privileged capability gateway.

- `apps/api/main.py`: authenticated REST/SSE, administrator session handling, resource checks, validation, and rate limits.
- `packages/pulse/core`: configuration, typed policy schemas, deterministic detector, task lifecycle, action authorization, and sustained verification.
- `packages/pulse/db`: SQLAlchemy records, validated atomic lifecycle transitions, similarity queries, frozen Alembic migration.
- `packages/pulse/tools`: HTTP Docker client, private SDK adapter, fixed Prometheus query templates, audited investigation tool registry.
- `packages/pulse/agents`: LangGraph collect/reason graph, LiteLLM function calling, explicit evidence analysis fallback, database checkpoint saver.
- `apps/api/gateway.py`: isolated Docker capabilities with separate authentication and a persistent SQLite action-claim journal.
- `apps/web`: Next.js App Router, same-origin streaming API proxy, TanStack Query cache invalidated by genuine server events, Recharts, Lucide, shadcn-style Radix/CVA button component.
- `examples/faulty-app`: authenticated demo fault controls and actual request instrumentation.

## Incident data flow

The optional `packages/pulse/project` companion inventories known repository
manifests and stores a private path-bound profile. `pulse watch` runs the existing
API/runtime and a directory/service-scoped gateway as owned local processes. Its
authenticated HTML/CSS/JS dashboard ships in the Python wheel, requiring no
Next.js build. It uses a per-project SQLite database and gateway journal. Closing
the owner stops only Pulse; watch never starts/stops application containers or
executes/edits target code. Live monitoring requires a running opted-in local
Compose app. The same lifecycle, approvals, checkpointing and verification below
apply, with bounded model calls triggered by detected incidents.

1. The gateway discovers only containers labeled `pulse.monitor=true`. API runtime upserts their identity/snapshot; operator monitoring choice persists.
2. Monitored containers get a timestamped sample of status, Engine metrics, and fixed-template Prometheus measurements. Samples older than 24 hours are removed.
3. The deterministic detector evaluates current health/status and consecutive threshold observations in a rolling window. A unique nullable `active_key` handles race-safe deduplication. Terminal incidents release the key; cooldown uses the previous update timestamp.
4. The worker transitions DETECTED → INVESTIGATING and invokes LangGraph. Initial evidence includes inspect, metrics, logs, and observed restart history, plus incident-specific Prometheus data.
5. The model can request further read-only tools or call `finish_investigation`. Tool arguments, affected resource authorization, deadlines, result bounds, redaction, and auditing apply outside the model. Checkpoints and pending writes persist after graph steps.
6. Validated diagnoses cite successful tool executions. Invalid references are removed and unsupported findings become unverified possibilities. Confidence remains qualitative. Provider errors/budgets preserve evidence and use clearly labeled deterministic analysis.
7. A proposed start/restart action receives an immutable UUID, content digest, and 15-minute expiry. The incident becomes AWAITING_APPROVAL. Nonmutating recommendations remain advisory.
8. Approval requires administrator authentication, a matching reviewed digest, current monitored/remediation permissions, development labels, valid resource identity/status, no emergency disable, and unexpired contents. An atomic conditional update consumes approval once and moves the incident to REMEDIATING.
9. The execution worker rechecks policy against a fresh snapshot, atomically claims execution, and calls the private gateway. The gateway separately authenticates and checks labels/state, then durably consumes the action UUID before dispatching exactly one start/restart. It exposes no generic Docker proxy.
10. Execution success moves to VERIFYING. Healthy consecutive observations must span the configured window, with at least two samples. Startup grace bounds settling; latency/error incidents additionally allow the Prometheus rolling window to age. Recovery is confirmed, failed, or inconclusive, with all samples retained.

A successful Docker command is never enough to enter RESOLVED. Every lifecycle transition checks the prior state. FAILED stays deduplicated until reinvestigated or dismissed. DISMISSED and RESOLVED are terminal; new incidents can occur after cooldown.

## Persistence and restart behavior

PostgreSQL stores services, samples, incidents, tool executions, actions, settings, stream events, audits, checkpoints, and pending graph writes. Approval and incident execution claims share one transaction. The gateway's durable journal is a separate named volume so its idempotency record survives API/database restarts.

An interrupted investigation resumes its checkpoint. An interrupted verification starts a fresh sustained observation window against the saved post-action baseline. An interrupted mutation is marked failed/inconclusive, and its execution claim is never replayed. This favors avoiding duplicate infrastructure changes over unattended retry. The operator must inspect current state and request a new proposal.

Only **one API worker/replica** is supported. Async task ownership is in that process; database compare-and-set operations prevent repeated actions, but there is no multi-process worker scheduler or leader election. Sync SQLAlchemy operations are short database transactions; network/docker/model calls are asynchronous or executed in worker threads. This is suitable for the local MVP, not a high-throughput hosted service.

## Integration boundaries

The model has no network client, shell, socket, environment access, or filesystem tool. Prometheus queries are chosen from a fixed metric enum and constructed with a JSON-escaped service matcher; arbitrary PromQL is unavailable. Dependencies are an exact-name allowlisted lookup from `pulse.dependencies`. Restart history is observed samples, not a reconstructed complete event stream.

Other applications need equivalent Prometheus instrumentation (`demo_http_requests_total{service,status}` and `demo_http_duration_seconds_bucket{service,le}`) or a code-level metric adapter extension. Verification HTTP probes are environment configured, host allowlisted, timeout bounded, and never follow redirects.

Semantic memory, remote provider-specific observability, Kubernetes, HA workers, and multi-user roles can be added at these boundaries later. They are absent from V1.
