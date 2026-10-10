# Repository companion validation — 10 October 2026

This increment adds repository inventory, reviewed enrollment, an installed local
project dashboard, terminal-owned monitoring and recovery choices. Live runtime
support is local Docker Compose. It retains the existing incident lifecycle,
approval policy, audit and recovery verifier. No schema migration was added.

## Real observations

The source-checkout acceptance used one cached synthetic lab application and one
small isolated peer. The peer had the same Compose project/service labels but a
different working directory: discovery excluded it and direct gateway inspection
returned 403. Lab-control routes in the project API returned 403. The application
crashed with exit 42; Pulse proposed Start and left it stopped until the operator
enabled recovery permission and approved the exact digest. Enter at the terminal
approval prompt declined. A consumed approval returned 409 on replay.

The session stopped during verification. Its original deadline
`1791621514.7502637` survived restart. Insufficient uninterrupted observations
produced **INCONCLUSIVE**, with five samples. A read-only recheck then returned
**RECOVERED**, with four samples spanning **33.125 seconds** for the configured
30-second stable window. Required evidence was Docker state, Docker metrics and
HTTP health. The last measurements were CPU **4.822%**, memory **49,082,368 bytes**
of **268,435,456 bytes** (**18.285%**) and HTTP **200**. The gateway journal recorded
exactly one mutation. Hard owner-process death stopped both Pulse children;
the app/peer remained running and the resolved report was readable offline.

The existing detector recorded one stopped incident and one unhealthy incident
for the same crash (distinct active keys per symptom). There was no duplicate
stopped incident after restart and only one action executed; the separate health
incident remained pending for operator review. This increment preserves that
existing lifecycle rather than auto-resolving another incident from one verdict.

The authenticated dashboard was checked at 1440 and 390 px. Its report download
matched the real API incident/verdict. No horizontal overflow or JavaScript
errors occurred. An interrupted browser API path showed that displayed evidence
was historical; restoring it resumed refresh. Black/red ECG styling was visually
inspected. Screenshots and private runtime state are retained at
`/workspace/pulse-project-session/20261010T083725Z/`. The
[redacted measured result](../examples/incident-lab/reports/repository-companion-20261010/result.json)
is included in this patch. These measurements used **deterministic evidence
analysis**, not mock or live model calls.

## Existing recovery scenarios

The native scoped incident lab reused the existing PostgreSQL server with its
separate lab database and four cached lab containers. The suite passed **4/4**:

| Scenario | Detection (s) | Verdict |
|---|---:|---|
| container-crash | 3.973 | RECOVERED |
| api-failure | 13.216 | RECOVERED |
| recovery-verification | 10.343 | NOT_RECOVERED |
| telemetry-loss | 10.571 | INCONCLUSIVE → RECOVERED |

Selected `demo-api` Prometheus scrape `up=0` was measured at **1791621799.032**;
unselected `demo-worker` stayed `up=1` at **1791621799.038**. Selected scrape
returned to `up=1` at **1791621829.927**. The missing-evidence window had nine
observations; the restored recheck had four. API restart preserved the original
deadline, exactly one mutation executed and no duplicate incident appeared.
The ineffective action still reported continuing HTTP/Docker health failure,
not inconclusive. All healthy baselines had zero false positives.

These Docker, HTTP, Prometheus, approval and restart observations were real.
Reasoning in this older lab suite used **mock/evidence**. No live LLM accuracy or
whole-suite performance improvement is claimed. The quality review reports
INSUFFICIENT_EVIDENCE: the four comparable scenarios are STABLE; memory/latency
lack compatible new baselines. Raw reports, timelines, evaluations and review:
[verification-0971c084](../examples/incident-lab/reports/verification-0971c084-2907-4b3b-9bac-da4315ac56ef/summary.md).

## Commands and outcomes

Commands ran from `/workspace/Pulse` unless specified. Python commands used
`UV_CACHE_DIR=/workspace/.cache/uv`; this avoids the read-only default cloud cache.

| Exact command / check | Result |
|---|---|
| `uv lock` then `uv sync --frozen` | PASS; PyYAML declared explicitly; no unrelated locked dependency version changes. |
| `uv run --no-sync pytest -q --tb=short` | PASS; 246 tests, three opt-in integrations skipped in this run. |
| `uv run pytest -q tests/test_project.py` | PASS; 39 repository regressions. |
| `uv run --no-sync python /workspace/pulse-verification-integrations.py` | PASS; all three opt-in tests (3.44 s): real PostgreSQL isolated schema, disposable Docker container and real Prometheus; lab `alembic check` passed. PostgreSQL incident logic uses fake adapters; it is not the real fault demonstration. |
| `uv run ruff check .` and `uv run ruff format --check .` | PASS. |
| `uv run pyright` | PASS; zero errors/warnings. |
| `npm run typecheck --prefix apps/web` | PASS. |
| `npm run format:check --prefix apps/web` | PASS. |
| `apps/web/node_modules/.bin/prettier --check packages/pulse/project/assets` | PASS. |
| `NEXT_TELEMETRY_DISABLED=1 VERCEL=0 PULSE_PUBLIC_SITE=0 npm run build --prefix apps/web` | PASS; full local Next.js product build. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | PASS; public build contains only landing and Docs. |
| `PORT=3300 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web` then `node apps/web/scripts/check-site.mjs http://127.0.0.1:3300` | PASS; public pages/screenshots load and operational/API routes return 404. Owned test server stopped afterward. |
| `uv run --no-project --with playwright python /workspace/pulse-project-public-check.py` | PASS; seven widths (1440/1024/768/651/650/390/320), seven phase groups, 16 dated entries, 15 exact commit links, keyboard/native details, JS-disabled reading, no overflow/JS errors/operational API calls. |
| `PULSE_DATABASE_URL=sqlite:////tmp/pulse-project-migrations-20261010.db uv run alembic upgrade head` | PASS. |
| Same database environment, `uv run alembic check`, `uv run alembic downgrade base`, then `uv run alembic upgrade head` | PASS; no pending changes. SQLite warns it cannot reflect the PostgreSQL expression search index; migration logic excludes that index on SQLite. |
| `docker compose -f docker-compose.yml config --quiet` and `docker compose -f examples/incident-lab/docker-compose.yml config --quiet` | PASS, with existing local credentials injected privately and no resolved configuration printed. |
| `uv run python examples/incident-lab/scripts/project-session.py` | PASS; six real workflow/isolation checks, small fixture Compose config validated. |
| `uv run --with playwright python examples/incident-lab/scripts/project-session.py --browser` | PASS; seven real checks including dashboard/report browser validation. |
| `uv run python examples/incident-lab/scripts/verification-session.py up` | PASS; scoped native API, cached lab images, separate existing lab database. |
| `uv run --no-sync pulse lab run telemetry-loss --approve --native-api` | PASS; four real scenario executions, including successful/ineffective actions. |
| `uv build --wheel --out-dir /workspace/pulse-project-wheel` | PASS; wheel contains dashboard HTML/JS/CSS, API and migrations; no `.env`. |
| `UV_TOOL_DIR=/workspace/pulse-project-installed/tools UV_TOOL_BIN_DIR=/workspace/pulse-project-installed/bin uv tool install --force --python 3.12 --from /workspace/pulse-project-wheel/pulse_sre-0.2.0-py3-none-any.whl pulse-sre` | PASS; installed isolated Python distribution. |
| From `/tmp`: `/workspace/pulse-project-installed/bin/pulse scan /workspace/Pulse/examples/incident-lab/repository-demo --format json` and `/workspace/pulse-project-installed/bin/Pulse --help` | PASS; installed commands work outside the source checkout. |
| `git diff --check`, private actual-credential scan, remote default-branch read | PASS; no credentials found in new code/report; main remains default and work is absent. |

From `/tmp`, the serial installed-distribution acceptance command
`/workspace/pulse-project-installed/tools/pulse-sre/bin/python /workspace/Pulse/examples/incident-lab/scripts/project-session.py`
passed all six real checks. It ran the actual installed API, migrations, gateway,
CLI and bundled dashboard outside the checkout's Python environment. Retained
private state: `/workspace/pulse-project-session/20261010T084418Z/`; the
[redacted installed result](../examples/incident-lab/reports/repository-companion-20261010/installed-result.json)
is included alongside the source/browser result.

`uv run python examples/incident-lab/scripts/verification-session.py check` and
`uv run python examples/incident-lab/scripts/verification-session.py down` passed
the original development-container identity/start/restart checks. The latter
stopped only the owned native lab API and four lab containers, retaining
databases, named volumes, credentials and all old/new reports. The separate
project acceptance removed only its own fixture/peer/network and retained its
project state. Approximately 27 GiB remained available; no duplicate full stack
or Docker-wide cleanup was used.

## Corrected attempts and limits

The initial suite found an old no-argument REPL compatibility issue; the adapter
now preserves that invocation. The real run caught double-opening an already
handshaken HTTP client and a port probe that rejected sockets in TIME_WAIT.
Both were corrected, covered by tests/real repeat runs and passed afterward.
An initial model-context unit fixture omitted `limitations`; the fixture was
corrected. A test command accidentally run from `/tmp` found no pytest; the
repository command was rerun successfully. `pulse lab verification-suite` was an
invalid guessed command; the supported `pulse lab run telemetry-loss --approve
--native-api` was used and passed.

The first installed-wheel acceptance overlapped the separate authorized lab
fault suite. Its final broad identity assertion failed because the other suite
deliberately restarted a lab container. The selected app, peer, measured
recovery, approval replay, parent cleanup and offline report checks passed; this
attempt does **not** establish isolation. Failed attempt data remains outside
the checkout. The serial repeat is the final installed acceptance.

The lab helper's initial isolation snapshot also contained two temporary
resources owned by a concurrent repository check. Only those two records were
saved separately/excluded after their authorized cleanup; all five original
development container records were retained and checked. No original stack,
database, report, credential or infrastructure permission was replaced.

No live provider was called; model payload/budget behavior uses mocked provider
tests. Generic Prometheus mappings, non-Compose processes, source fixes/security
audits, Windows/macOS sessions and native Homebrew installation remain untested
or outside this increment. Prometheus is optional/explicit and currently uses
fixed supported metric names. A changed service allowlist requires profile
review. Existing credential-pattern redaction cannot promise to catch all secret
formats. The native gateway retains the operator's Docker privilege.

## Changed files

- `packages/pulse/project/`: scanner, private profile/state, terminal-owned
  process session/guard/server, CLI, web routes and bundled dashboard assets.
- `packages/pulse/cli.py`, `repl.py`: installed command dispatch and repository
  selection/commands while preserving lab demos.
- `packages/pulse/core/config.py`, `runtime.py`: native dotenv isolation and
  explicitly unavailable unconfigured Prometheus.
- `packages/pulse/tools/docker_adapter.py`, `prometheus.py`: directory/service
  boundaries and unavailable-sample adapter.
- `packages/pulse/agents/investigator.py`: known inventory facts in bounded model
  context; existing read-only tool policy unchanged.
- `apps/api/main.py`, `gateway.py`: authenticated action review, project routes,
  gateway scope and owner-lifetime guard.
- `pyproject.toml`, `uv.lock`, `tests/test_project.py`: PyYAML and regressions.
- `examples/incident-lab/repository-demo/compose.yaml`,
  `scripts/project-session.py`: repeatable small real fixture/acceptance driver.
- New measured report folders above; existing reports preserved.
- `README.md`, `docs/repository-companion.md`, this results file,
  `docs/getting-started.md`, `architecture.md`, `api.md`, `security.md`,
  `product-history.md`: workflow, topology, boundaries and evidence.
- `apps/web/src/components/landing.tsx`, `product-docs.tsx`,
  `product-phases.tsx`, `src/lib/product-history.ts`: public usage documentation,
  Phase 4 entry and preceding exact commit link. No Vercel routing change.
