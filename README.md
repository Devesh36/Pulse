# Pulse

**An evidence-driven AI SRE for your local Docker environment.**

Pulse discovers opted-in containers, detects operational incidents, investigates with audited read-only tools, proposes a recovery action, requires your approval, and observes the service before declaring recovery. The dashboard contains live backend data; it does not seed fabricated incidents or metrics.

Run the installed CLI in your own repository: `pulse scan`, `pulse init`, then
review/apply the printed enrollment command and keep `pulse watch` open. Its
local project dashboard and investigations share that terminal's lifetime;
Ctrl+C stops only Pulse. History and reports persist. This first version scans
different project types and monitors **running local Docker Compose apps**.
See [repository setup, LLM configuration and recovery choices](docs/repository-companion.md).

## About Pulse

Pulse connects monitoring, investigation, human-approved recovery and verification
in one local workspace. It is built for trusted Docker development environments,
with a Next.js dashboard, Python API, PostgreSQL incident history and Prometheus
telemetry. The guided incident lab lets you try the full workflow on selected demo
resources using real measurements and deterministic reasoning, without a model API key.

The repository companion ships a lightweight dashboard in the Python package,
with a per-repository SQLite database and scoped gateway. It requires no Node
build or separate Pulse stack. The Next.js operational workspace remains
available for the full development/lab workflow; Vercel hosts the public website.

Recovery is reported as **RECOVERED**, **NOT_RECOVERED** or **INCONCLUSIVE**. Missing
telemetry never counts as healthy; a read-only recheck after restoration observes
the service without replaying the action. Monitoring and remediation permissions
are separate, and each Start/Restart still needs an exact, expiring, one-time approval.

### See the product

These are actual captures of the existing local development overview and a retained
incident-lab investigation. They show recorded backend measurements, not a live feed.
The lab diagnosis uses deterministic mock reasoning; no live LLM was evaluated.

![Pulse overview with discovered Docker services and measured resource charts](apps/web/public/screenshots/overview.png)

![Pulse investigation with its recorded lifecycle and evidence-backed diagnosis](apps/web/public/screenshots/investigation.png)

## Documentation

The Next.js website includes a dedicated **Docs** page at `/docs`, linked from the
landing page and available without an API connection. It explains what Pulse does,
how it runs, the first demo, REPL commands, dashboard login, verdicts, data storage
and troubleshooting, with full-size product screenshots. **About** on the landing
page describes the product, architecture and approval model.

- [Install and use Pulse](docs/getting-started.md)
- [Monitor your own repository](docs/repository-companion.md)
- [Deploy the landing page and Docs on Vercel](docs/vercel-landing.md)
- [Architecture](docs/architecture.md) and [API reference](docs/api.md)
- [Recovery verification](docs/recovery-verification.md) and [real telemetry-loss results](docs/verification-telemetry-results.md)
- [Security and approvals](docs/security.md) and [troubleshooting](docs/troubleshooting.md)

The Vercel configuration builds only the public Next.js landing page, Docs and
screenshots. It excludes the dashboard and API routes. The full product continues
to run locally through Docker and the REPL.

## Quick start

Install the preview and open its guided demo:

```bash
uv tool install --from git+https://github.com/Devesh36/Pulse.git@main pulse-sre
pulse repl
```

Choose **1 / Demo**, confirm the scoped lab action, and follow the real crash/recovery
run. `Pulse Repl` is also supported. Type `telemetry` for missing-evidence verification,
`reports` for results, or `stop` to preserve history and stop the lab. Docker with
Compose is required for demos; no LLM API key is needed. Homebrew users can install
the included preview formula: [installation and menu guide](docs/getting-started.md).

After installation, start Docker Desktop/Engine, run `pulse repl`, type `demo` and
confirm `y`. Then type `dashboard` to open http://localhost:3100/lab; sign in with
`PULSE_ADMIN_TOKEN` from the credential file path printed by the REPL. Type `reports`
for measured outcomes, `stop` and confirm `y` to preserve the database and reports,
then `exit` to leave the menu. The first build can take several minutes.

### Development checkout

Requirements: Docker Engine with a working daemon, Docker Compose v2, and `uv` with Python 3.12+. Node 22+ is needed only for frontend development outside Compose.

```bash
cp .env.example .env
uv sync
uv run python scripts/setup-env.py
# Optional: set your model provider in .env before starting.
docker compose --profile demo up --build -d
```

Open **http://localhost:3000** for the product landing page, then **Open workspace**
(http://localhost:3000/dashboard). Sign in with `PULSE_ADMIN_TOKEN` from your local `.env` (do not share it). API health: http://localhost:8000/api/v1/health; interactive API docs: http://localhost:8000/docs. Prometheus is bound to http://localhost:9090. All published ports bind to localhost; the Docker gateway has **no published port**.

The website's product guide is **http://localhost:3000/docs**. The separate API
schema reference remains on port 8000 at `/docs`.

`setup-env.py` generates distinct administrator, Docker adapter, demo, and database secrets without printing them, preserves existing settings, and writes `.env` with mode `0600`. Compose rejects empty required secrets. Do not commit `.env`.

To run without the fault demo, omit `--profile demo`. To stop, run `docker compose --profile demo down`. Named volumes preserve PostgreSQL, Prometheus, and the gateway's one-time execution journal. **`down -v` destroys that history.**

## Phase 2 incident laboratory

Run the five real fault scenarios in a separate disposable `pulse-lab` project:

```bash
uv sync --frozen
uv run --no-sync pulse lab up --dashboard
uv run --no-sync pulse lab evaluate --all --approve
uv run --no-sync pulse lab report --format markdown
uv run --no-sync pulse lab down
```

`--approve` explicitly authorizes only the evaluator's scoped lab actions through the real
approval API. For manual approvals, use the **Incident Lab** dashboard on loopback port 3100.
Fault endpoints stay internal; the lab creates distinct local credentials and bounded
workloads. Teardown deletes the disposable lab history while retaining host reports.
See [run instructions](examples/incident-lab/README.md), [evaluation methodology](docs/evaluation-methodology.md),
and [actual Phase 2 results](docs/phase2-results.md). Deterministic/mock results are not live-model accuracy.

## Phase 3: continuous quality feedback

Type **quality / 7** in `pulse repl` to review retained measurements without starting
or changing the lab. The local Incident Lab dashboard shows current evaluation
failures, compatible-baseline comparisons and actionable follow-up steps.

```bash
pulse lab quality
pulse lab quality --reports-dir examples/incident-lab/reports --format json
pulse lab quality --reports-dir examples/incident-lab/reports --fail-on-regression
```

New runs preserve prior reports in unique folders and record settings, reasoning
mode, timestamps and run identity. Missing evidence, replayed runs or changed settings
cannot establish improvement. Expected ineffective remediation remains a valid
NOT_RECOVERED test; missing evidence cannot conceal an observed failure. The weekly
lab workflow exports a read-only quality review with its artifact. See
[comparison rules, gates and the improvement loop](docs/continuous-improvement.md).
Local checks and measured outcomes are recorded in [Phase 3 results](docs/phase3-results.md).

## What is implemented

- Label-scoped Docker discovery; container state, health-check output, exit/OOM metadata, restart counts, deployment labels, bounded logs, real CPU and memory measurements.
- Deterministic incident detection for unexpected stops, restart activity, unhealthy containers, sustained CPU/memory threshold violations, Prometheus p95 HTTP latency, and 5xx rate. Rolling windows, configurable consecutive samples, unique active-incident keys, and cooldowns prevent alert spam.
- Validated incident lifecycle with persisted detection evidence, timeline, diagnosis, tool results, approval records, action outcomes, verification samples, and operator/worker audits.
- A real LangGraph collect/reason workflow with PostgreSQL checkpoints and pending writes. LiteLLM function calling supports additional evidence collection, typed diagnoses, iteration/input-output token budgets, timeouts, and explicit provider-failure handling.
- Ten typed investigation tools, scoped to monitored resources, with timeout handling, secret-pattern redaction, bounded output, and execution audits.
- Immutable, expiring start/restart proposals; separate monitoring/remediation permissions; one-time explicit approvals; fresh policy/resource validation before mutation; a durable gateway idempotency journal. No automatic infrastructure changes.
- Sustained recovery observation: running state, health, restart stability, available metrics, incident-specific thresholds, and configured HTTP probes. Startup grace and Prometheus window aging are accounted for; insufficient evidence is **inconclusive**, never resolved.
- Authenticated REST/SSE, cursor replay and state synchronization, restricted CORS, HttpOnly signed sessions with CSRF origin checks, rate limiting, JSON worker logging, graceful task shutdown, and interrupted-operation handling.
- Responsive dark Next.js dashboard: overview charts, service inspection/logs/access controls, incident history, investigation workspace, evidence citations, approval/rejection, assistant, settings, audit records.
- A genuine instrumented fault application with crash, bounded memory allocation, delayed responses, and HTTP-error scenarios.
- Alembic migrations and PostgreSQL full-text/structured incident similarity lookup. SQLite is supported for isolated tests and local dashboard development.

## Opt containers in

Add labels to your development application's Compose service and recreate that container:

```yaml
labels:
  pulse.monitor: "true"
  # Only add these two if it is safe to offer start/restart actions:
  pulse.remediate: "true"
  pulse.environment: development
  # Optional exact container names, comma-separated:
  pulse.dependencies: my-database,my-cache
```

The gateway discovers only `pulse.monitor=true`. Discovered containers initially have monitoring enabled because the label is an explicit opt-in. You can turn it off in **Services → inspect container**. Remediation permission starts **disabled** and must separately be enabled there. Even with permission and labels, each action still requires explicit approval.

Containers recreated by Compose have a new identity and require new remediation permission. Pulse never silently transfers an approval to a replacement container. Docker environment variables, mounted files, and unrestricted labels are not exposed to the investigator.

Docker CPU follows the Engine convention: **100% is one fully used CPU core**, so values can exceed 100%. Memory uses the working set after subtracting `inactive_file`, as a percentage of the container's configured limit. Set a memory limit for meaningful comparisons.

## Configure AI

Edit `.env`, then restart/recreate the API. Secrets are server-side and are never returned by settings endpoints.

```dotenv
# OpenAI example
PULSE_LLM_MODEL=openai/gpt-4.1-mini
PULSE_LLM_API_KEY=your-key
PULSE_LLM_API_BASE=
```

For Anthropic use a LiteLLM `anthropic/<model>` identifier and that provider's key. For an OpenAI-compatible local model:

```dotenv
PULSE_LLM_MODEL=openai/your-local-model
PULSE_LLM_API_BASE=http://host.docker.internal:11434/v1
PULSE_LLM_API_KEY=local
```

Use a model available to your account that supports function calling. Provider capability/availability errors preserve the evidence and fall back to deterministic analysis. The local endpoint must be reachable from the API container; on Linux you may need a `host-gateway` mapping.

**No model is required for the demo.** With an empty `PULSE_LLM_MODEL`, Pulse collects actual evidence and produces an explicitly labeled deterministic diagnosis with low qualitative confidence. This is not represented as an LLM diagnosis. Model-enabled investigations send redacted operational evidence to the configured provider; select a local model if that evidence must stay on your machine.

Monitoring thresholds, interval, budgets, cooldown, verification window, startup grace, and the emergency remediation disable switch are editable in **Settings** and persist in the database. Provider credentials require environment configuration and an API restart.

## Run the fault scenarios

Keep injections restricted to the included development demo. Its control endpoints require the separate `PULSE_DEMO_TOKEN` and a server-side demo-enabled flag.

```bash
# A: exits with code 42; logs record the injected application crash.
uv run python scripts/demo.py crash
# Review the incident, enable demo remediation permission, then approve Start.

# B: allocates a bounded 160 MiB inside a 256 MiB container.
# Set the memory threshold to 60% in Settings for a reliable demonstration.
uv run python scripts/demo.py memory

# C: introduces 2-second response latency while real self-requests are instrumented.
uv run python scripts/demo.py latency

# Optional: genuine 5xx responses.
uv run python scripts/demo.py errors

# Reset a running demo, or approve Restart to clear process-local fault state.
uv run python scripts/demo.py reset
```

Latency/error detection requires Prometheus scrapes, two or more scrape observations, and the configured rolling window/consecutive samples. Expect approximately 30–90 seconds with defaults. A stopped app cannot accept `/reset`; approve its Start proposal or use `docker compose --profile demo start faulty-app` manually. The memory scenario does not intentionally OOM the machine; allocation is capped.

### Real acceptance demonstration

Start the full demo stack first, then:

```bash
uv run python scripts/e2e.py
```

**Running this command explicitly approves a Start of the included demo container** after inspecting its crash diagnosis; it does not approve other services. The script injects a real crash, waits for a newly detected stopped-container incident, checks exit code 42 and the crash log in tool evidence, approves the immutable action, checks duplicate approval rejection, and waits for confirmed sustained recovery. It restores the prior monitoring settings and service permissions and leaves the incident/audit history for inspection. Start from a healthy demo without a pending stopped incident; repeat within the cooldown only after changing the cooldown in Settings.

The script raises an error if any part cannot be confirmed. Tests using `FakeAdapter` are explicitly separate and are not evidence of a real-Docker acceptance run.

## Development and tests

```bash
uv sync
uv run python scripts/setup-env.py
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
npm ci --prefix apps/web
npm run typecheck --prefix apps/web
npm run format:check --prefix apps/web
npm run build --prefix apps/web
```

Optional real integrations (isolated PostgreSQL schemas and disposable Docker containers are cleaned up):

```bash
PULSE_TEST_POSTGRES_URL=postgresql+psycopg://user:password@localhost/testdb uv run pytest tests/test_integrations.py -q
PULSE_TEST_DOCKER=1 uv run pytest tests/test_integrations.py -q
```

The PostgreSQL test user needs permission to create a schema in a **test database**. Never point these tests at production. The Docker test pulls `alpine:3.21` and operates only on its explicitly labeled disposable container. External model calls are mocked in tests.

For hot reload while preserving the same isolated infrastructure and localhost bindings:

```bash
docker compose -f docker-compose.yml -f infrastructure/docker-compose.dev.yml --profile demo up --build
```

The override mounts Python packages/API and frontend source read-only, runs Uvicorn and Next.js with reload, and keeps the gateway private. Tests still run on the host through uv. For frontend-only native development, stop the Compose web service and run `npm run dev --prefix apps/web`; it proxies to the localhost API. Run **one API worker**; the monitoring/investigation worker runs inside that process.

Without Docker, you can launch the real dashboard with an empty database to inspect disconnected behavior:

```bash
PULSE_DATABASE_URL=sqlite:///./pulse.db uv run alembic upgrade head
PULSE_DATABASE_URL=sqlite:///./pulse.db uv run python -m apps.api.serve
npm run dev --prefix apps/web
```

No services or incidents are fabricated in this mode.

## Architecture and safety

```text
Next.js → authenticated FastAPI → PostgreSQL (telemetry, incident memory, checkpoints, audit)
                         ├─ deterministic monitor → LangGraph → read-only tool registry → LiteLLM
                         ├─ approved actions → policy + fresh resource check → private Docker gateway
                         ├─ verification → Docker telemetry + Prometheus + allowlisted HTTP probes
                         └─ authorized SSE → dashboard state synchronization
Private Docker gateway → Docker Engine socket (only component holding Docker privileges)
Demo application's actual request metrics → Prometheus
```

The Python distribution lives in `packages/pulse/{core,db,tools,agents}`; HTTP entry points live in `apps/api`, the dashboard in `apps/web`. See [architecture](docs/architecture.md), [API](docs/api.md), [threat model](docs/security.md), and [troubleshooting](docs/troubleshooting.md).

The Docker socket is effectively host administration access. The gateway holds it, runs only on an internal network, requires a separate token, limits resources by labels, and provides only bounded read operations and start/restart. This reduces exposure; it **does not make a compromised gateway harmless**. Use Pulse only for trusted local development infrastructure. The LLM cannot access the socket, generate shell commands, apply configuration changes, or bypass approvals.

## Verification status and limitations

Detailed results: [verification record](docs/verification.md).

Verified during implementation: backend tests including real PostgreSQL persistence/checkpoints and recovery against an isolated test adapter; migration/schema agreement; frontend production compilation and TypeScript checks; Compose configuration validation; API/dashboard startup.

The original MVP validation record above predates the cloud incident lab. Current
real Docker, PostgreSQL and Prometheus measurements are in the [Phase 2 results](docs/phase2-results.md),
[telemetry verification results](docs/verification-telemetry-results.md), and
[installed CLI/REPL validation](docs/onboarding-results.md). Mock reasoning and
fixture-backed checks are identified separately from real telemetry.

Other deliberate MVP limits:

- Single administrator and single API worker. No multi-tenant RBAC, HA worker scheduling, or Kubernetes.
- Prometheus HTTP latency/error queries support the included `demo_http_*` instrument schema and service labels. Instrument other apps equivalently or extend the fixed query templates. Arbitrary PromQL is intentionally unavailable to the model.
- Restarts/dependencies/change history are inferred only from observed samples and explicit/deployment labels, not a complete Docker event archive or source-control deployment feed.
- Qualitative confidence and valid evidence references do not guarantee a model's interpretation is correct. Inspect the linked evidence.
- Secret redaction is pattern-based, not a guarantee of removing every application secret. Logs may contain sensitive information and are retained in incident history.
- Samples are retained 24 hours; incident/audit/checkpoint events remain until operator-managed archival. No automatic audit retention/export UI.
- Diagnostics are collected during investigations; `collect_diagnostics` and configuration recommendations are advisory proposals, with no separate one-click execution control. No automated config editing.
- No real external provider calls were made during tests; provider access and model compatibility must be validated with your configuration.

Next milestones: validate your chosen live provider, add application metric adapters
and richer deployment/event feeds, then introduce multi-user authorization and
out-of-process worker ownership before considering remote infrastructure.

## License

MIT. See [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
