# Incident lab workflow

See [the exact CLI commands](../examples/incident-lab/README.md). `pulse` is installed by
`uv sync --frozen`; use `uv run --no-sync pulse ...` from the existing repository checkout.
Do not create a worktree for this already isolated cloud task.

The fixed `pulse-lab` Compose project has separate PostgreSQL, Prometheus, API, gateway,
API/worker demos, and an optional web service. It has no production credentials. The gateway
filters Docker discovery by exact project, then checks monitoring/development/lab/service
labels on every control operation. The general gateway excludes lab resources unless
explicitly configured for the lab project.

The public scenarios map crash to the worker, memory/errors/delay to the API, and persistent
health failure to the worker. Fault controls are authenticated administrator requests to
`POST /api/v1/lab/faults/{scenario}`; fields bound memory, latency, and error ratio.
`GET /api/v1/lab/status` returns discovered state, not fabricated readiness.

For manual operation, start `pulse lab up --dashboard`, sign in on port 3100 using the
lab's private administrator token, then use **Incident Lab**. Each incident links to
recorded tools, cited findings, proposed actions, and the existing approval controls.
Service remediation permission remains separate from approval. Reset actions, start,
and restart all require approval through the same API and journal.

The CLI evaluator's `--approve` is an explicit test authorization instruction. A separate
lab token authenticates its test principal; it cannot approve an unrelated resource or
use the assistant/session endpoints. Each run verifies anonymous denial, rejects duplicate
approval, waits for final verification, and records the approval actor.

Startup is noninteractive. Repeating it preserves secrets/history. Reset explicitly
cancels/dismisses pending incidents before cleanup; it does not falsify a successful recovery.
Teardown is project-scoped, removes runtime resources and lab-owned image tags, and verifies
that no labeled containers/networks/volumes remain. Reports stay on the host.
