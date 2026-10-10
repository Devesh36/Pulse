# Phase 2 baseline and gaps

Baseline inspected on 2026-10-09 at commit `3b04a551cfb5d487afcf12c1cff0ac338ce8c841`.
`UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pytest -q`: **66 passed, 2 skipped** (21.09 s).
The skipped tests opt into PostgreSQL and Docker. Both passed separately during onboarding,
as did the original real-Docker crash acceptance, frontend build, and authenticated dashboard proxy.

## Reuse

- FastAPI REST/SSE and signed administrator sessions with origin checks.
- SQLAlchemy/PostgreSQL, Alembic, incident lifecycle, unique active-incident keys,
  persisted evidence, audits, proposals, and LangGraph checkpoints.
- Deterministic Docker/Prometheus detection and evidence analysis; optional LiteLLM tools.
- Private Docker gateway with label checks, bounded logs, and durable action claims.
- Immutable expiring proposals, separate service permissions, explicit approval API,
  fresh resource revalidation, emergency disable, and sustained recovery observations.
- Next.js dashboard and the instrumented original fault demo.

## Extend

- A separate `pulse-lab` project, demo API/worker, bounded gradual memory injection,
  persistent ineffective-restart condition, and token-protected internal controls.
- Real bounded Docker lifecycle events and strict project/resource scope.
- Minimum HTTP traffic requirements, stale measurement rejection, source timestamps,
  post-action metric windows, distinct recovery thresholds, and explicit verification outcomes.
- Lab-only reset actions through the existing approval/journal path.
- Investigation duration/tool/concurrency bounds and richer cited hypotheses.
- Hidden evaluator manifests, five-scenario runner, real measurement reports,
  baseline false positives, negative verification, and cleanup validation.
- Authenticated lab APIs/dashboard, deterministic CI, migration checks, and documentation.

## Environment findings and compatibility

Cloud checkout files are mode 0600; non-root images need readable **image copies**.
The HTTPS proxy CA must be supplied to container package installers without disabling TLS.
This Docker daemon does not publish ports on internal-only networks; use a separate bridge
for the documented loopback access, keeping the socket gateway internal. Container HTTP clients
must bypass the environment proxy for lab service DNS names. These are setup constraints,
not evidence that application telemetry is healthy.

Preserve existing endpoints, states, and legacy verification `outcome` values. Add explicit
verification result codes and diagnosis fields rather than breaking dashboard/test consumers.
Extend JSON evidence/proposal payloads without a parallel persistence system. Add an Alembic
migration only for new evaluation records. No shell tool, arbitrary PromQL, arbitrary fault URL,
privileged demo, or implicit approval is introduced. Only the private gateway mounts Docker's
socket; that remains a host-administration capability and is not a sandbox against gateway compromise.
