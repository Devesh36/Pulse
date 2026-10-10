# One-command project demo — validation, 2026-10-10 UTC

Inside an existing local Compose repository, run `Pulse Repl`, then `/demo`.
Pulse selects the current directory, scans bounded metadata, creates/reuses
private state, identifies the existing Compose project and opens a local
read-only dashboard and monitor. Repeated demos reuse the same session.
Exactly one monitored service becomes the question context automatically;
multiple services are listed for explicit selection. Existing incidents are
summarized; no question, fault or recovery action is injected automatically.

No application script, Compose command, build, pull or label change runs through
this flow. Read-only enrollment requires a complete project/root/service
allowlist and preserves explicit monitoring opt-outs. The API masks recovery
permission without changing its stored value and audits denied approval. The
gateway independently rejects every recovery/fault action, including actions
against containers with development/recovery labels. Normal enrollment and
digest-bound approvals retain their existing behavior.

## Exact checks

Commands ran from `/workspace/Pulse` with
`UV_CACHE_DIR=/workspace/.cache/uv` for Python operations. Cached dependencies and
lab images were reused; no full second stack was started.

| Command | Outcome |
| --- | --- |
| `uv run pytest -q` | PASS: **298 passed, 3 skipped**, including 18 new demo/scope/readiness regressions. The three opt-in infrastructure cases were skipped; actual Docker/HTTP checks ran separately. |
| `uv run ruff check .` | PASS. |
| `uv run ruff format --check .` | PASS: 125 files. |
| `uv run pyright` | PASS: zero errors/warnings. |
| `npm run typecheck --prefix apps/web` | PASS. |
| `npm run format:check --prefix apps/web` | PASS. |
| `NEXT_TELEMETRY_DISABLED=1 VERCEL=0 PULSE_PUBLIC_SITE=0 npm run build --prefix apps/web` | PASS: full local product routes. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | PASS: landing, Docs and not-found only. |
| `uv build --wheel --out-dir /workspace/pulse-demo-wheel` | PASS. |
| `uv pip install --python /workspace/pulse-project-installed/tools/pulse-sre/bin/python --no-deps --reinstall /workspace/pulse-demo-wheel/pulse_sre-0.2.0-py3-none-any.whl` | PASS: local preview installation, no publication. |
| `uv run python examples/incident-lab/scripts/repl-session.py --demo` | PASS: seven real project-demo checks. |
| `PULSE_TEST_CLI=/workspace/pulse-project-installed/bin/pulse uv run python examples/incident-lab/scripts/repl-session.py --demo` | PASS: seven checks using the installed executable. |
| `PULSE_TEST_CLI=/workspace/pulse-project-installed/bin/pulse uv run --with playwright python examples/incident-lab/scripts/repl-session.py --demo --browser` | PASS: eight checks, including authenticated desktop/mobile read-only dashboard and incident evidence. |
| `uv run python examples/incident-lab/scripts/project-session.py` | PASS: six existing real recovery/approval/restart/isolation checks. |
| `uv run --with playwright python /workspace/pulse-repl-browser-check.py` | PASS: public Docs/Phases at seven widths, JS-disabled reading, no overflow or JS errors, no operational API calls, dashboard 404. Owned public server stopped afterwards. |

Development and lab Compose validation passed using
`docker compose -f docker-compose.yml config --quiet` and
`docker compose -f examples/incident-lab/docker-compose.yml config --quiet`.
These ran through a Python subprocess with existing dotenv values injected
privately; resolved configuration and credentials were never printed.
The real scripts also validate their selected fixture Compose configuration.

With `PULSE_DATABASE_URL=sqlite:////tmp/pulse-project-demo-migrations-20261010.db`,
`.venv/bin/alembic upgrade head`, `.venv/bin/alembic check`,
`.venv/bin/alembic downgrade base`, then `.venv/bin/alembic upgrade head` passed.
There are no schema changes or pending migration operations. SQLite emitted
the existing warning about reflecting the PostgreSQL expression search index.
PostgreSQL migrations were not rerun for this schema-free increment.

## Real evidence

Source demo measurements:
`/workspace/pulse-repl-session/20261010T152134Z/result.json`.
Installed demo measurements:
`/workspace/pulse-repl-session/20261010T152226Z/result.json`.
Installed dashboard/browser measurements:
`/workspace/pulse-repl-session/20261010T152445Z/result.json`.

The trusted fixture started **without Pulse labels**. Opening the REPL with no
repository argument from its directory and typing `/demo` discovered it through
the exact Compose project, working directory and service scope. Repeating the
command started no duplicate monitor. Both API permission escalation/approval
and direct gateway recovery were rejected; a pre-existing foreign container
was rejected by the gateway. These are actual HTTP responses, not mocked policy.

Each explicit test question reached `DIAGNOSED` with four successful real tools:
container inspection, resource metrics, logs and restart history. Its report
retained cited observations, low confidence and the unresolved underlying cause.
Reasoning was **deterministic**, with real Docker/HTTP measurements; neither a
mock model nor a live LLM was used. Reports persisted across stop/restart with
one question incident. SIGINT at the prompt preserved monitoring; SIGKILL of
the REPL stopped worker/API/gateway. The gateway recorded **zero executed
actions**, and all **six pre-existing containers** retained identity, state,
start time and restart count. Only the fixture container/network was removed.

Authenticated browser checks at 1440 and 390 pixels verified read-only scope,
disabled recovery, available incident diagnosis/citations, no page overflow or
JavaScript errors. Screenshots are retained with the private run artifacts.
Public website checks covered 1440/1024/768/651/650/390/320 pixels.

Normal recovery compatibility measurements:
`/workspace/pulse-project-session/20261010T152246Z/result.json`. The scoped app
crashed with exit 42, stayed stopped until explicit permission and exact
approval, then reached `RECOVERED` with four verification samples after a
session restart. There was one stopped incident, one separate unhealthy
incident and one executed action; approval replay was rejected. All six
pre-existing container identities/states/start times/restart counts were retained.

## Corrected failures and limits

The first real repeat-run check exposed profile initialization trying to take
the active monitor's lock. Demo now reads the validated existing profile and
preserves its credentials/scope/history; the lock regression and real rerun pass.
The acceptance harness initially sent SIGINT before demo returned to its prompt;
it now waits for an additional context command before testing input cancellation.
The TTY test was updated for the automatically selected repository prompt, and
a test fixture's runtime construction was corrected. Final checks pass with no
unresolved failed or blocked operations.

Live monitoring still needs existing local Docker Compose containers. Source-only
or stopped/unavailable apps are explained; Pulse does not fabricate telemetry or
start arbitrary repository code. Demo readiness requires a fresh completed
gateway poll within the configured evidence age; missing, stale, future or
nonfinite timestamps cannot yield readiness. An empty discovery is explained as
missing application coverage, not healthy recovery. Dashboard login still uses
the private administrator token file. Provider credentials must be configured
before launch for live model reasoning; live LLMs and Windows terminals were not
tested. The separate fault lab remains `/lab demo`, with its existing consent.
The full ineffective-remediation/telemetry-loss evaluation was not rerun; its
verification engine is unchanged and its existing unit regressions passed.

Changed files: REPL and project CLI/session/demo/SDK adapter; API and gateway;
native dashboard JS; demo acceptance runner and regressions; README, getting
started, repository and security guides; landing/Docs content and Phase 4 history.
The preceding REPL commit's exact SHA is backfilled in the public timeline.
