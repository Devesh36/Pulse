# Run Pulse in your own repository

The installed Python CLI owns your local project dashboard, telemetry polling
and background investigations. Keep `pulse watch` running. Ctrl+C stops Pulse's
API and gateway, leaving your application running. Incident history, verification
progress and reports survive the next session. Node and a separate Pulse Compose
stack are unnecessary for this mode.

This first version inventories different project languages but **live monitoring
requires a running Docker Compose application on the local Docker host**. It
observes opted-in containers, not native processes or business logic. A scan does
not establish the security or transaction correctness of a trading/banking app.

## Install, scan and enroll

Use Python 3.12+, uv and Git, plus Docker Engine/Desktop with Compose v2. This
installs the GitHub main preview, not a published PyPI release:

```bash
uv tool install --force --from git+https://github.com/Devesh36/Pulse.git@main pulse-sre
cd /path/to/your-project
pulse scan
pulse init
```

`scan` reads known metadata manifests and reports languages, frameworks,
Compose services and incomplete coverage. It does not import target code, run
package scripts, read `.env`/source files or perform a security audit. Bounds:
1 MiB per manifest, 5,000 visited files and four directory levels. Compose
aliases, custom tags, `include` and `extends` need manual review; choose a
self-contained file.

`init` saves a private profile and **prints an enrollment command for you to
review and run**. Review its `monitor.compose.json`, then run the printed
`docker compose ... up -d` command to apply opt-in monitoring labels. Compose
may recreate containers. Pulse never applies this override or starts your app.
If you use multiple Compose files, custom profiles/environment files or `-p`,
preserve those options and select an equivalent self-contained configuration.
Use `--compose-file` and `--compose-project` to match your actual app. A project
name alone cannot enroll another repository: the gateway also checks the
canonical Compose working directory and declared service names.

By default the override adds only `pulse.monitor=true`; recovery remains
disabled. After enrolling your running app:

```bash
pulse watch
```

Open the printed URL (default `http://127.0.0.1:8765`). Sign in with `admin_token`
from the printed private `credentials.json` path; keep that file private. The
browser uses an HttpOnly session cookie. Ports 8765/8766 bind only to loopback.
Use `--port 8875` if occupied, or `--no-browser`. Busy ports never cause another
service to stop. Only one watch session can own a repository.

The dashboard shows inventory, telemetry coverage, state/metrics, incidents,
diagnosis, citations, tools, timeline, verification and JSON report downloads.
No discovered services means no runtime coverage. Missing/stale evidence does
not establish health. Reports include timestamps and verdict reasons.

## REPL alternative

```text
Pulse Repl
pulse › open /path/to/your-project
pulse › scan
pulse › init
```

Apply the reviewed enrollment command in your regular shell, then type `/watch`
in the REPL. Monitoring runs in an owned background process while the prompt
accepts commands. `/stop`, `/exit` or EOF stops only that REPL's Pulse processes;
your application, databases and reports remain. Ctrl+C cancels the current input
or request and never retries it. If the REPL disappears, an owner guard stops its
monitoring worker and that worker's API and gateway. A watch started in a different
terminal is never stopped by this REPL.

`incidents`, `report`, `dashboard`,
`permissions`, `approve ID`, `reject ID` and `recheck ID` operate on the selected
project. Quote paths with spaces. `pulse repl PATH` selects one directly.

### Agentic command workflow

Slash prefixes are optional; `/help COMMAND` shows usage and Tab completes command
names in terminals with readline. Command history is not saved. The prompt shows
the selected repository. Stop owned monitoring before switching repositories.

```text
/context
/watch --no-browser
/status
/model
/services
/use demo-api
/ask What evidence explains this service's current behavior?
/logs 50
/incidents
/inspect INCIDENT_UUID
/timeline INCIDENT_UUID
/report
/stop
/exit
```

`/ask` uses the selected monitored service and creates a question investigation
in the existing incident history. Its response is asynchronous: follow the returned
ID with `/inspect` or `/timeline`. Model investigations use existing budgets and
fixed read-only evidence tools, and do not receive source files. With no provider
configured, Pulse uses deterministic evidence and states its limitations. Set
provider environment variables before launching Pulse and use `/watch --model
PROVIDER/MODEL`; `/model` only inspects the active configuration.

`/investigate ID` confirms invalidating old pending proposals before rerunning a
read-only investigation. `/approve ID` still displays the exact expiring action
and asks for approval, defaulting to No. Empty input never repeats a previous
command. `/clear` clears the visible terminal without deleting evidence. Updates
from background monitoring appear after each command; `/status` and `/incidents`
check live progress. The lab stays explicitly available via `/lab status`,
`/lab dashboard` and `/lab stop` even with a selected project.
`demo`, `telemetry`, `reports` and `quality` always operate on
the separate incident lab, not the selected project.

## Background reasoning

Telemetry polls continuously (default every 10 seconds). Deterministic thresholds
create incidents; the configured LLM investigates them in the background using
scoped read-only tools, citations, timeouts, concurrency and token budgets.
Unchanged incidents do not repeatedly trigger model calls. Models cannot execute
shell commands, edit files, use arbitrary URLs or mutate infrastructure.

Without a model, Pulse explains actual evidence using its deterministic fallback
and explicitly says no live LLM is running. For a provider, securely configure
`PULSE_LLM_MODEL`, its provider credentials or `PULSE_LLM_API_KEY`, and, if needed,
`PULSE_LLM_API_BASE` in **the Pulse terminal's environment**. Repository `.env`
files are never sourced. The provider receives bounded, redacted runtime evidence
and known inventory facts; it does not continuously review full source code.
Provider/tool failures remain visible limitations. `mock/evidence` is lab-only.

## Choose who fixes an incident

Opt a safe development service into reviewed Start/Restart proposals during
initial enrollment:

```bash
pulse init --recovery-service api --health api=http://127.0.0.1:8080/health
```

Only that service receives `pulse.remediate=true` and
`pulse.environment=development` in the override. Review/apply it yourself; do not
label production as development to bypass policy. Pulse recovery permission
still starts disabled. Enable it explicitly in the dashboard or with its service
UUID, then review an incident's proposed action:

```bash
pulse permissions SERVICE_UUID --allow-recovery
pulse incidents
pulse approve ACTION_UUID
```

Approval prints the exact resource, action, reason, digest and expiry, then asks
`Approve this exact action once? [y/N]`. Enter declines. Noninteractive approval
requires both `--yes` and the exact reviewed `--digest`. Approvals expire and are
one-time. Pulse measures sustained recovery afterward; a successful mutation is
not proof of recovery.

Choose **I'll handle it** in the dashboard or `pulse reject ACTION_UUID` to
reject the proposal. Fix code/configuration yourself: this version offers
advisory recommendations and bounded container Start/Restart, not arbitrary
automatic edits. `pulse recheck INCIDENT_UUID` after inconclusive/failed
verification collects a new window without replaying the action.

## Evidence and persistence

Docker state, health checks, exit/OOM data, bounded logs/events, CPU and memory
drive detection. Explicit `--health SERVICE=URL` loopback HTTP(S) probes must have
no credentials/query parameters; they participate in verification, not independent
probe-failure detection. Add a Docker health check for unhealthy-container
detection.

Prometheus is **unconfigured by default**, instead of reading someone else's
stack. `--prometheus-url http://127.0.0.1:9090` selects one explicitly. Fixed
HTTP latency/error queries currently require the supported
`demo_http_*{service=...}` schema. Arbitrary metrics do not map automatically;
unsupported/missing samples remain unavailable. Generic mappings and non-Compose
runtime support are follow-up work.

Private state: `$XDG_DATA_HOME/pulse/projects/<canonical-path-id>` or
`~/.local/share/pulse/projects/<canonical-path-id>`; `PULSE_HOME` overrides the
base. Each repo has its own SQLite database, gateway idempotency journal,
credentials, profile, logs and redacted reports. New files are private on POSIX.
Repeat init preserves credentials/history. Changed service names fail closed and
require local profile review; no automatic scope expansion. Inventory is an
initial snapshot, not continuous source analysis.

```bash
# Another terminal while watch runs:
pulse incidents --format json
# Also works after watch stops, without Docker/API:
pulse report --format json
pulse report --incident INCIDENT_UUID --format markdown
```

JSON reports retain citations, tools, digests, observations and timeline with
`recorded_at`. They are saved snapshots. The database preserves authoritative
verification progress and its original deadline across sessions. Restart gaps
may make a window inconclusive; recheck requires fresh measurements. Observed
continuing failure is never hidden by missing evidence.

## Repeatable real check

From the Pulse checkout, prepare only the small trusted incident-lab images if
they are not cached, then run:

```bash
docker build -t pulse-lab-demo:latest examples/incident-lab/services
docker pull alpine:3.21
uv run python examples/incident-lab/scripts/project-session.py
```

The script reuses those images, starts one synthetic app and a small isolated
scope peer, injects the existing crash, tests consent/replay, restarts Pulse
during verification and kills its owner to test child cleanup. Only its own
containers/network are removed. It retains private databases, logs and redacted
measurements outside the checkout. No live LLM or second full stack is needed.
See [measured results](repository-companion-results.md).

To validate the interactive command workflow, scoped questions, background
monitoring, cancellation, stop/restart and hard owner death with real evidence:

```bash
uv run python examples/incident-lab/scripts/repl-session.py
# Optional: use an already-installed executable instead of the source entry point
PULSE_TEST_CLI=/path/to/pulse uv run python examples/incident-lab/scripts/repl-session.py
```

This check uses the same cached demo image and one synthetic Compose service.
It executes no recovery, uses deterministic evidence (no live or mock model),
preserves all existing containers and retains private reports outside the checkout.
See [REPL validation and limitations](repl-results.md).

Run this acceptance check separately from other tests that restart existing
containers: its isolation assertions compare every pre-existing container's
identity, state, start time and restart count.
