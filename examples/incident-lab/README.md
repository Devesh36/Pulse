# Pulse incident laboratory

Disposable, labeled services exercise real Docker, PostgreSQL, Prometheus, LangGraph,
policy-controlled approvals, and post-action recovery. Run commands from the repository root:

```bash
uv sync --frozen
uv run --no-sync pulse lab up
uv run --no-sync pulse lab status
uv run --no-sync pulse lab run container-crash --approve
uv run --no-sync pulse lab run memory-pressure --approve
uv run --no-sync pulse lab run api-failure --approve
uv run --no-sync pulse lab run slow-response --approve
uv run --no-sync pulse lab run recovery-verification --approve
uv run --no-sync pulse lab evaluate --all --approve
uv run --no-sync pulse lab report --format json
uv run --no-sync pulse lab report --format markdown
uv run --no-sync pulse lab reset
uv run --no-sync pulse lab down
```

`--approve` explicitly authorizes the selected lab test action through a dedicated,
resource-scoped test principal and the real approval API. It does not authorize other
containers. Without it the CLI refuses to run a mutating evaluation. For human review,
start with `--dashboard`, sign in with the private lab administrator token, inject a
fault on **Incident Lab**, inspect its evidence, enable the affected service's remediation
permission, and approve the immutable proposal on its investigation page. Never share `.env`.

The API binds to loopback port 8100, Prometheus to 8109, and optional dashboard to 3100.
Fault endpoints are **not published**; only the private gateway reaches them, with a
separate lab token. The worker and API use 256 MiB memory limits and 0.5 CPU limits.
Allocations grow in 8 MiB steps and stop at 176 MiB. Synthetic orders/search traffic is bounded.
A persistent worker health fault survives restart in its own disposable volume; its
ineffective restart must produce `NOT_RECOVERED`, never `RESOLVED`.

Local `.env` credentials are generated with mode 0600 and preserved on repeated startup.
The cloud HTTPS proxy CA, when supplied through `SSL_CERT_FILE`, is passed as a public
build trust bundle; TLS and package hashes remain verified. Docker `vfs` uses substantial
disk space: demo images have a separate hash-locked dependency set and backend installs
omit package caches. Only the fixed lab images are built; no other project is started/stopped.

`reset` preserves reports/history, cancels or dismisses pending investigations explicitly,
waits for active execution to finish, starts the lab demos, and clears their workloads.
A direct dashboard cleanup reset cannot bypass a pending approval or active verification.
`down` deletes this **disposable project's** containers, networks, volumes, and tagged
build images. It destroys lab database/metric/journal history, while host report files remain.
Shared base images and build caches may remain. It never runs global Docker pruning.

Reports are in `reports/`. Hidden assertions are in `fixtures/`, loaded by the evaluator
only; the API image does not copy them and investigation tools cannot read host files.
The public scenario catalog is not used to supply diagnoses. The agent sees actual
inspection, metrics, logs, and lifecycle events.

Modes:

- Empty `PULSE_LLM_MODEL`: deterministic evidence analysis through the real LangGraph workflow.
- `PULSE_LLM_MODEL=mock/evidence`: explicit mocked model responses for deterministic CI,
  still using actual tools and telemetry; the reported mode is `mock-model`.
- A configured LiteLLM model/key/base: use `--live-model`. This refuses to claim live
  accuracy when the provider falls back without verified model token usage. Put credentials
  securely in the local lab `.env` or process environment, never reports or shell history.

For the mock CI mode, prefix both startup and evaluation with `PULSE_LLM_MODEL=mock/evidence`.
See [incident-lab documentation](../../docs/incident-lab.md) and
[evaluation methodology](../../docs/evaluation-methodology.md).

## Recovery evidence loss evaluation

This supplements the existing HTTP error scenario; it introduces no new application fault
category. `/metrics` alone returns 503 on the selected authorized demo while its workload,
health endpoint, peer service and development stack continue running. The run checks crash
recovery, HTTP recovery, an ineffective restart, telemetry loss, API restart, restored
telemetry and explicit read-only re-verification. Reasoning uses mock/evidence; telemetry is real.

For the limited cloud host, reuse the existing development PostgreSQL and prepared gateway
image, start four scoped lab containers and a native API:

```bash
uv run --no-sync python examples/incident-lab/scripts/verification-session.py up
uv run --no-sync pulse lab run telemetry-loss --approve --native-api
uv run --no-sync python examples/incident-lab/scripts/verification-session.py check
uv run --no-sync python examples/incident-lab/scripts/verification-session.py down
```

This helper requires the existing credential files and PostgreSQL development service. It
creates only the isolated `pulse_verification_lab` database and lab resources; it does not
change credentials, publish the gateway, restart development containers or delete databases.
Gateway code is staged as readable public source copies without changing checkout permissions.
`down` preserves the isolated database, named lab volumes and timestamped reports.
For an ordinary running isolated lab configured with `mock/evidence`, omit `--native-api`;
only that lab's API is restarted.

Reports are written under `reports/verification-<UTC timestamp>/summary.{json,md}` and
per-case JSON files, and persisted in lab evaluation history. Existing reports are preserved.
Export the latest verdicts and actionable explanations with
`uv run --no-sync pulse lab report --verification --format markdown` (or `--format json`).
The fixed verification policy uses a six-second stability window, fifteen-second startup
grace, ten-second HTTP window, five-second maximum telemetry gap and minimum five requests.
Detection deadlines remain 30 seconds for crash and 60 seconds for HTTP/health cases.
The full five-fault `evaluate --all` command remains unchanged; the supplementary telemetry
scenario runs explicitly with the command above.
