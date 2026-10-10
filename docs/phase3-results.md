# Phase 3 validation: continuous quality feedback

Validated on 2026-10-10 in the managed Linux cloud checkout. This increment adds
a read-only evaluation feedback loop, not autonomous tuning or new fault categories.
See [usage and comparison rules](continuous-improvement.md).

## Result

All six latest scenario assessments passed their required evidence checks. The
final database review returned **ATTENTION_REQUIRED**: zero failed assessments,
one latency regression flag and three scenarios needing compatible baselines.
Crash detection increased from **3.278 s to 4.619 s** in compatible restoration
suites, exceeding the **1.000 s** review threshold by a measured delta of **1.341 s**.
Both detections still met the original fixture deadline. This is a follow-up
signal to reproduce, not statistical proof from two runs. API failure and
ineffective remediation were STABLE. Memory, slow response and telemetry loss
were INCOMPARABLE because the retained baseline lacked complete context or timing.
No whole-suite improvement is claimed.

The earlier compatible standard crash repeat was STABLE (4.521 s → 3.474 s;
delta −1.047 s, threshold 1.130 s). Both reviews are retained alongside the raw
scenario evidence. An expected NOT_RECOVERED result remains a passing negative
test; INCONCLUSIVE cannot replace observed continuing failure.

## Real lab measurements

The scoped session reused the existing PostgreSQL server with a separate lab
database, a native API on port 8100, and four lab containers. It used cached demo
images rather than another full development stack. Docker state, Prometheus,
HTTP probes, approval/replay rejection and API restarts were real. Investigation
reasoning used **mock/evidence**, with no external LLM calls.

| Standard suite scenario | Detection (s) | Diagnosis (s) | Observed verdict | Evaluation |
|---|---:|---:|---|---|
| container-crash | 4.521 | 0.286 | RECOVERED | PASS |
| memory-pressure | 8.088 | 2.098 | RECOVERED | PASS |
| api-failure | 10.453 | 2.134 | RECOVERED | PASS |
| slow-response | 17.879 | 2.122 | RECOVERED | PASS |
| recovery-verification | 7.939 | 2.100 | NOT_RECOVERED / FAILED incident | PASS |

The full standard suite passed **5/5**, a crash repeat passed **1/1**, and two
restoration suites each passed **4/4**: fourteen successful scenario executions.
Every recorded healthy baseline had zero false positives. Final restoration
suite detection/diagnosis seconds were crash 4.619/0.350, HTTP failure
12.838/2.181, ineffective action 9.897/2.087 and telemetry loss 10.272/2.101.

In the final telemetry-loss case, Prometheus measured selected `demo-api` scrape
`up=0` at **1791618240.512**, while unselected `demo-worker` remained `up=1` at
**1791618240.519**. Selected telemetry returned to `up=1` at **1791618271.434**.
Initial verification was **INCONCLUSIVE**, with ten observations and the reason
that Prometheus/request-count evidence was unavailable and the deadline had
elapsed. Read-only re-verification after restoration returned **RECOVERED**, with
four observations covering the stable recovery window. The original deadline
survived API restart, no duplicate incident appeared, and the audit recorded
exactly one mutation execution. Successful and ineffective remediation cases
were rerun in both restoration suites.

The first telemetry-loss report passed the scenario assertions but lacked
`completed_at`. The new review correctly marked it INSUFFICIENT_EVIDENCE. The
recorder now writes completion time even on failure; a regression covers that
path, and the second real suite produced complete passing evidence. The earlier
incomplete report is preserved rather than retroactively repaired.

Raw JSON, summaries and review snapshots are in these new directories:

- [Standard five-scenario run](../examples/incident-lab/reports/run-136bf12f-e514-4a72-bc37-c42c683531a1/evaluation-summary.json).
- [Compatible crash repeat](../examples/incident-lab/reports/run-232883c5-4d23-4a3f-afa4-0229845732c6/quality-review.md).
- [First restoration suite](../examples/incident-lab/reports/verification-cd77b647-1ef6-46e9-ba51-2b528da7ab2e/summary.json).
- [Corrected restoration suite](../examples/incident-lab/reports/verification-888315b6-1145-43b9-8d4c-de3cd5d8638e/summary.json) and [final review](../examples/incident-lab/reports/verification-888315b6-1145-43b9-8d4c-de3cd5d8638e/quality-review.md).

## Commands and checks

Commands below ran from the checkout unless specified. Python commands used
`UV_CACHE_DIR=/workspace/.cache/uv` because the default cloud cache is read-only.
Session-only helper scripts live outside the checkout and are validation harnesses,
not installed product commands.

| Command / check | Final result |
|---|---|
| `uv run --no-sync pytest -q --tb=short` | PASS: 207 passed, 3 optional integrations skipped; 29.16 s. |
| `uv run --no-sync python /workspace/pulse-verification-integrations.py` | PASS: all 3 opt-in tests, 3.53 s; PostgreSQL isolated-schema persistence, disposable real Docker container, real Prometheus query. PostgreSQL test uses fake adapters for its incident logic; this is distinct from the real lab suites. Also passed live isolated-lab `alembic check`. |
| `uv run --no-sync ruff check .` | PASS. |
| `uv run --no-sync ruff format --check .` | PASS. |
| `uv run --no-sync pyright` | PASS: zero errors/warnings. |
| `NEXT_TELEMETRY_DISABLED=1 VERCEL=0 PULSE_PUBLIC_SITE=0 npm run build --prefix apps/web` | PASS: full local dashboard production build. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | PASS: final public build contains only `/` and `/docs`. |
| `npm run typecheck --prefix apps/web` | PASS. Production builds also ran TypeScript checks. |
| `npm run format:check --prefix apps/web` | PASS. |
| `PORT=3200 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web` then `node apps/web/scripts/check-site.mjs http://127.0.0.1:3200` | PASS: landing/Docs/screenshots 200; eight operational paths 404. Owned test server stopped afterward. |
| `uv run --no-project --with playwright python /workspace/pulse-phase3-public-check.py` | PASS: 12 page/viewport combinations, widths 1920/1440/1024/768/390/320; black/red under either OS preference; sampled text contrast minimum 5.07:1; ECG/reduced motion, clipboard/tabs, walkthrough/disclosures/images/navigation; no overflow, JS errors or API requests. Public walkthrough is an illustration, not real telemetry. |
| `uv run --no-project --with playwright --with python-dotenv python /workspace/pulse-phase3-browser-check.py` | PASS: actual authenticated local dashboard at 1440/390 px matches all six API quality rows; no overflow/JS errors; no fault or remediation controls invoked. |
| `uv run --no-sync python /workspace/pulse-phase3-restart-check.py` | PASS: authenticated quality refs/assessments survive an actual native API restart; receipted offline history matches the API; mutation audit IDs unchanged. |
| `uv build --wheel --out-dir /workspace/pulse-phase3-wheel` | PASS: local preview wheel, no publication. |
| `UV_TOOL_DIR=/workspace/pulse-phase3-install/tools UV_TOOL_BIN_DIR=/workspace/pulse-phase3-install/bin uv tool install --force --from /workspace/pulse-phase3-wheel/pulse_sre-0.2.0-py3-none-any.whl pulse-sre` | PASS: isolated installed distribution. |
| `PULSE_HOME=/workspace/pulse-phase3-install/data /workspace/pulse-phase3-install/bin/pulse lab quality --reports-dir /workspace/pulse-phase3-api-history --format json` from `/tmp` | PASS: installed CLI scenarios/summary equal the authenticated API snapshot. |
| `printf 'quality\nexit\n' \| PULSE_HOME=/workspace/pulse-phase3-install/data /workspace/pulse-phase3-install/bin/Pulse Repl` from `/tmp` | PASS: retained-report review works, exits normally and creates no credentials. |
| Local parsing of `.github/workflows/incident-lab.yml` | PASS. Remote GitHub Actions execution unverified. |
| Credential-value scan of all newly generated JSON/Markdown | PASS; values never printed. This checks configured secrets, not arbitrary unknown application secrets. |
| `git diff --check` | PASS. |

All **210 unique collected tests** executed across the two pytest runs. The 51 new
quality regressions use synthetic report fixtures; their results are not real
telemetry. They cover partial/missing evidence, malformed measurements, failure
precedence, expected ineffective actions, changed settings/modes/targets,
replayed/out-of-order runs, latency flags, offline size/deduplication/redaction,
authenticated persistence, receipt ordering, report retention, and read-only
CLI/REPL gates. Existing recovery-window regressions remain in the full suite.

The initial installed offline review exposed an overly strict input-size check:
pretty-printed historical reports exceeded the API's compact upload limit. The
reader now has its own bounded 4 MiB formatted-file limit; the API upload limit
is unchanged. New regressions and final installed/archive checks passed.

Migration and Compose validation commands all passed:

```bash
PULSE_DATABASE_URL=sqlite:////tmp/pulse-phase3-migrations-20261010.db uv run --no-sync alembic upgrade head
PULSE_DATABASE_URL=sqlite:////tmp/pulse-phase3-migrations-20261010.db uv run --no-sync alembic check
PULSE_DATABASE_URL=sqlite:////tmp/pulse-phase3-migrations-20261010.db uv run --no-sync alembic downgrade base
PULSE_DATABASE_URL=sqlite:////tmp/pulse-phase3-migrations-20261010.db uv run --no-sync alembic upgrade head
PULSE_DATABASE_URL=sqlite:////tmp/pulse-phase3-migrations-20261010.db uv run --no-sync alembic check
docker compose --env-file .env -f docker-compose.yml config --quiet
docker compose --project-name pulse-lab --env-file examples/incident-lab/.env -f examples/incident-lab/docker-compose.yml --profile dashboard config --quiet
```

SQLite emitted its existing expression-index reflection warning; checks found no
new upgrades. No schema change or new migration is required for this phase.

Real session commands all passed:

```bash
uv run --no-sync python examples/incident-lab/scripts/verification-session.py up
uv run --no-sync pulse lab evaluate --all --approve --native-api
uv run --no-sync pulse lab run container-crash --approve --native-api
uv run --no-sync pulse lab run telemetry-loss --approve --native-api
# Repeated after fixing completion-time recording:
uv run --no-sync pulse lab run telemetry-loss --approve --native-api
uv run --no-sync python examples/incident-lab/scripts/verification-session.py down
```

These commands use the existing authorized test principal and resource allowlist.
The final teardown checks confirmed unchanged identities, start times and restart
counts for `pulse-web-1`, `pulse-api-1`, `pulse-gateway-1`, `pulse-postgres-1` and
`pulse-prometheus-1`. It stopped only the scoped native API/lab containers and
preserved databases, report archives, credentials and named volumes. Owned web
test servers were stopped; the pre-existing native Next process was retained.
No disk pruning, duplicate full stack, credential change or permission expansion
was needed.

## Changed files and limits

- `packages/pulse/lab/quality.py`: pure bounded assessment/comparison/archive reader and Markdown renderer.
- `apps/api/main.py`: authenticated read-only quality endpoint using existing evaluation rows.
- `packages/pulse/lab/{evaluate,telemetry_loss}.py`: unique report folders, run context/baselines, API receipts, retained failures and completion timestamps.
- `packages/pulse/lab/cli.py`, `packages/pulse/repl.py`: online/offline review, explicit gates, quality menu and recursive latest-summary lookup.
- `apps/web/src/components/{incident-lab,product-docs}.tsx`: local review/evidence links and public command documentation; no theme or broad layout change.
- `.github/workflows/incident-lab.yml`: offline review export/regression gate using the existing weekly/manual workflow and permissions.
- `tests/test_quality.py`, README, `docs/{api,getting-started,continuous-improvement,phase3-results}.md`: regressions and documentation.
- Four new report directories listed above; existing historical reports remain untouched.

The review scores recorded reports, not current service health, independently
attested telemetry, statistical performance or live-model accuracy. Different
database/archive histories can produce different reviews; receipts make ordering
consistent when both contain the same records. Historical reports without
receipts cannot reconstruct exact API recording order. Missing or incompatible
baselines remain visible and strict `--check` cannot pass until those gaps close.
`--fail-on-regression` correctly exits 2 for the measured crash-latency flag;
that attention result is preserved rather than changed to green.

Remote CI and the remote Vercel deployment were not verified or manually deployed.
No release, Homebrew formula or package registry publication was performed; the
isolated installed-wheel checks validate this checkout's preview distribution.
Approvals, replay rejection, incident lifecycle, resource allowlists, redaction and
audit persistence retain their existing enforcement paths.
