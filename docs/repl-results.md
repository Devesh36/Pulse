# Interactive REPL validation — 2026-10-10 UTC

Pulse now accepts grouped slash commands and plain command names, with scoped
project/service context, read-only questions, evidence inspection, bounded logs,
completion and detailed help. `/watch` runs the existing project monitor in a
terminal-owned worker. `/stop`, EOF and `/exit` stop that owned worker; a parent
guard handles hard terminal death. Approval still goes through the original
expiring, digest-bound, replay-protected API and restricted gateway.

## Commands and outcomes

Commands ran from `/workspace/Pulse`. Python commands used
`UV_CACHE_DIR=/workspace/.cache/uv`; dependencies and cached lab images were reused.

| Exact command | Outcome |
| --- | --- |
| `uv run ruff check .` | PASS. |
| `uv run ruff format --check .` | PASS; 122 files formatted in the final check. |
| `uv run pytest -q` | PASS; **280 passed, 3 skipped**. Includes 34 new REPL cases and an actual POSIX TTY/readline subprocess check. The three skips are opt-in PostgreSQL, Docker and Prometheus integrations; real Docker/HTTP acceptance checks ran separately below. |
| `uv run pyright` | PASS; zero errors/warnings. |
| `npm run typecheck --prefix apps/web` | PASS. |
| `npm run format:check --prefix apps/web` | PASS. |
| `NEXT_TELEMETRY_DISABLED=1 VERCEL=0 PULSE_PUBLIC_SITE=0 npm run build --prefix apps/web` | PASS; full local product routes. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | PASS; only landing page, Docs and not-found route. |
| `uv build --wheel --out-dir /workspace/pulse-repl-wheel` | PASS; preview wheel includes REPL, owner worker and dashboard assets. |
| `uv pip install --python /workspace/pulse-project-installed/tools/pulse-sre/bin/python --no-deps --reinstall /workspace/pulse-repl-wheel/pulse_sre-0.2.0-py3-none-any.whl` | PASS; existing isolated installation upgraded locally without dependency duplication. No package publication. |
| `uv run python examples/incident-lab/scripts/repl-session.py` | PASS; six real REPL/ownership/isolation checks. |
| `PULSE_TEST_CLI=/workspace/pulse-project-installed/bin/pulse uv run python examples/incident-lab/scripts/repl-session.py` | PASS; same six checks through the installed executable, rerun against the final wheel. |
| `uv run python examples/incident-lab/scripts/project-session.py` | PASS; six existing real recovery/approval/restart/isolation checks. |
| `uv run --with playwright python /workspace/pulse-repl-browser-check.py` | PASS; updated Docs and Phases at seven widths (1440/1024/768/651/650/390/320), JS-disabled command reference, dashboard 404, no page overflow, JavaScript errors or operational API calls. Owned public server on port 3338 stopped afterwards. |

Compose checks ran `docker compose -f docker-compose.yml config --quiet` and
`docker compose -f examples/incident-lab/docker-compose.yml config --quiet` through
a Python subprocess with existing dotenv values injected privately. Both passed;
no resolved configuration or credential values were printed. The real acceptance
scripts also validate their selected fixture and enrollment override with
`docker compose … config --quiet`.

Migration checks used `PULSE_DATABASE_URL=sqlite:////tmp/pulse-repl-migrations-20261010.db`
with `.venv/bin/alembic upgrade head`, `.venv/bin/alembic check`,
`.venv/bin/alembic downgrade base`, then `.venv/bin/alembic upgrade head`. All
passed; no pending migration operations. SQLite emits the existing warning about
reflection of the PostgreSQL expression search index. This increment changes no
schema. PostgreSQL migrations were not rerun for this increment.

## Real measurements

Source REPL run: `/workspace/pulse-repl-session/20261010T121823Z/result.json`.
The user question reached `DIAGNOSED` with four successful real evidence calls:
`inspect_container`, `get_container_metrics`, `get_container_logs` and
`get_container_restart_history`. The inspected container was running/healthy,
exit code 0, restart count 0; one observed metric sample recorded CPU 4.0% and
memory 18.1% of its limit. The report explicitly retained low confidence and
an unresolved underlying cause. This was **deterministic reasoning on real
Docker/HTTP evidence**, with neither a mock model nor a live LLM.

The final installed REPL run retained measurements at
`/workspace/pulse-repl-session/20261010T122249Z/result.json`:

- The prompt accepted questions, logs, incident inspection and malformed arguments
  while its monitor remained active.
- `/stop` stopped its API/gateway while the REPL and application stayed alive.
- Restart retained the same question and evidence, with one question investigation.
- Ctrl+C at the prompt left monitoring active and did not replay a command.
- SIGKILL of the REPL caused its worker, API and gateway to stop. Application
  identity, start time and restart count were unchanged. The gateway recorded
  **zero executed actions**.
- All **six pre-existing containers** retained identity, state, start time and
  restart count. The script removed only its one fixture container/network,
  preserving databases, reports and the development stack.

Existing recovery acceptance retained its results at
`/workspace/pulse-project-session/20261010T121941Z/result.json`. The real fixture
exited with code 42 and remained stopped until explicit permission and exact
approval. The default terminal approval was decline. After approval and a
verification restart, four verification samples produced `RECOVERED` with
fresh, ordered, post-action evidence. There was exactly **one stopped incident**,
one separate unhealthy incident and **one executed gateway action**; replay
returned 409. The same pre-existing container isolation checks passed.

## Corrected checks and limits

Initial static typing exposed missing mixin declarations; they were corrected
and the full check passed. An initial actual terminal check exposed Python 3.12
`cmd.Cmd` using a GNU Tab binding on this host's libedit backend. Pulse now binds
Tab correctly for libedit and GNU readline, restores the previous completer, and
disables automatic history storage. Backend unit tests and the actual TTY
regression pass. No unresolved failed or blocked checks remain.

Updates from background monitoring display after commands; an idle prompt does
not redraw itself. `/status` and `/incidents` query live progress. Questions are
asynchronous; follow their returned ID with `/inspect` or `/timeline`. Live LLM
calls, Windows TTY behavior and model changes during an active session were not
tested. Completion depends on optional platform readline support; commands still
work without it. Live monitoring remains limited to explicitly enrolled local
Docker Compose applications. The ineffective-remediation and telemetry-loss lab
suite was not rerun here; its verification engine is unchanged and existing
missing/stale/contradictory-evidence unit regressions passed in the full suite.

Changed source: `packages/pulse/repl.py`, `packages/pulse/repl_project.py`,
`packages/pulse/project/repl_worker.py`, `packages/pulse/project/cli.py`.
Regression/acceptance files: `tests/test_repl.py`,
`examples/incident-lab/scripts/repl-session.py`. Documentation:
`README.md`, `docs/repository-companion.md`, this report,
`apps/web/src/components/product-docs.tsx` and
`apps/web/src/lib/product-history.ts` (including the preceding exact commit link).
