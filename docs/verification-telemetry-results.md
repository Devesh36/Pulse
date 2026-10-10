# Recovery telemetry verification increment — 2026-10-09

The verifier now distinguishes observed recovery, observed continuing failure, and
insufficient/contradictory evidence. INCONCLUSIVE uses the existing FAILED state; it
does not resolve an incident or repeat a remediation. An explicitly requested read-only
recheck can return that same incident to VERIFYING and then RESOLVED. Existing approvals,
expiry, action digests, replay protection, resource restrictions, redaction and audit
records remain in force. No SQL schema change is needed: verification version 2 uses
the existing incident JSON and durable event journal.

See [verification semantics](recovery-verification.md) for the frozen policy, per-source
timestamps/watermarks, condition ledger, complete source coverage, gap handling and
restart behavior. A contradiction invalidates the disputed condition, while independent
still-fresh observed failure remains NOT_RECOVERED.

## Real measurements

The repeatable command below produced
[the four-case summary](../examples/incident-lab/reports/verification-20261009T150148Z/summary.md)
and [raw JSON](../examples/incident-lab/reports/verification-20261009T150148Z/summary.json).
All four cases passed. Reasoning was **mock/evidence** through the real investigation
workflow; Docker state/stats, Prometheus queries, HTTP health probes and remediation
were real. These measurements do not establish live-model accuracy.

| Case | Detection seconds | Verification |
|---|---:|---|
| Container crash | 5.65 | RECOVERED |
| HTTP failure | 12.40 | RECOVERED |
| Ineffective restart | 7.51 | NOT_RECOVERED |
| Selected telemetry loss | 15.62 | INCONCLUSIVE, then RECOVERED after read-only recheck |

Each case followed a 14-second healthy baseline; none produced an unexpected incident.
Only the selected demo-api's `/metrics` path returned 503 during verification. Its
workload and health endpoint continued; Docker remained observable. Direct Prometheus
`up{job="incident-lab",instance="demo-api:8080"}` measured 0 at Unix timestamp
1791558285.716, while demo-worker measured 1 at 1791558285.733. After restoration,
demo-api measured 1 at 1791558316.740. Raw rolling metric values retained by Prometheus
were not accepted as healthy evidence while scraping was down.

The original verification began at 1791558281.6068242 with deadline
1791558312.6068242. Restarting only the native lab API retained that start/deadline,
committed samples and source watermarks, added resume_count=1, and cleared the healthy
streak. Its nine measured samples ended INCONCLUSIVE with this explanation:

> Recovery is inconclusive: prometheus: unavailable; request_count: unavailable;
> deadline: observation_after_deadline. Restore reliable telemetry and request read-only
> re-verification; do not replay the remediation.

The final in-flight observation finished after the deadline and was explicitly rejected;
the deadline was not extended. Restoration required an operator-requested read-only
window. Four new samples confirmed recovery at 1791558328.151494. Required-source spans
were Docker state 7.051s, Docker stats 7.054s, HTTP health 7.093s, Prometheus metric 6.000s
and request count 6.000s, each meeting the configured six seconds. The prior
INCONCLUSIVE attempt remains in history. The same incident/action remained in use;
there was exactly one mutation execution and no duplicate error incident during the
six-second post-recheck observation. Anonymous approval returned 401, wrong digest and
approval replay returned 409, and concurrent recheck returned 409. Reports were accepted
into the API's evaluation history.

The final policy uses interval=2s, stability=6s, grace=15s, HTTP window=10s,
maximum gap=5s and minimum five requests. Original detection deadlines remain 30/60s.

## Commands and results

Commands were run from `/workspace/Pulse`, with `UV_CACHE_DIR=/workspace/.cache/uv`
for uv commands. No credential values were printed or copied into reports.

```bash
uv run --no-sync python examples/incident-lab/scripts/verification-session.py up
uv run --no-sync pulse lab run telemetry-loss --approve --native-api
uv run --no-sync pulse lab report --verification --format markdown
uv run --no-sync python examples/incident-lab/scripts/verification-session.py check
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest -q --tb=short
cd apps/web
npm run format:check
npm run typecheck
npm run build
```

Python lint/format/type checks passed (zero Pyright errors/warnings). The final ordinary
pytest run passed **132 tests**, with **3 optional integrations skipped** because their
opt-in environment variables were absent. Regressions cover missing/stale/duplicate/
out-of-order/partial/wrong-resource/future evidence, Prometheus source availability and
traffic, contradictory conditions, failure freshness, slowly advancing buffered samples,
gaps, timeouts, after-deadline observations, committed progress, process restart,
missing baselines and read-only restoration without approval/mutation replay.
Frontend formatting, TypeScript and production build passed. Native production Next.js
served the dashboard and proxied authenticated API data with matching result, reason,
required evidence, restart marker and prior INCONCLUSIVE history. Browser interaction
and visual screenshots were not run.

Migration and Compose checks passed:

```bash
PULSE_DATABASE_URL=sqlite:////tmp/pulse-verification-migrations-final.db uv run --no-sync alembic upgrade head
PULSE_DATABASE_URL=sqlite:////tmp/pulse-verification-migrations-final.db uv run --no-sync alembic check
PULSE_DATABASE_URL=sqlite:////tmp/pulse-verification-migrations-final.db uv run --no-sync alembic downgrade base
PULSE_DATABASE_URL=sqlite:////tmp/pulse-verification-migrations-final.db uv run --no-sync alembic upgrade head
PULSE_DATABASE_URL=sqlite:////tmp/pulse-verification-migrations-final.db uv run --no-sync alembic check
docker compose --env-file .env -f docker-compose.yml config --quiet
docker compose --project-name pulse-lab --env-file examples/incident-lab/.env -f examples/incident-lab/docker-compose.yml --profile dashboard config --quiet
```

SQLite emits its existing warning that it cannot reflect the PostgreSQL search expression
index; both checks found no new upgrade operations. Isolated PostgreSQL migration/check
also passed. No production schema or existing report/database was removed.

## Compatibility and opt-in integrations

The existing five-case evaluator also passed with the final verifier. Reports are in
[the compatibility summary](../examples/incident-lab/reports/recovery-compat-20261009T145704Z/evaluation-summary.md).
Crash, memory pressure, HTTP failure and latency all returned RECOVERED; ineffective
remediation returned NOT_RECOVERED. Detection times were respectively 4.49s, 12.58s,
11.42s, 13.66s and 11.82s. All five healthy baselines had zero unexpected incidents.
Final states survived an additional native API restart. These are mock reasoning with
real tools and telemetry, not live-model measurements.

The native session's [compatibility driver](/workspace/pulse-verification-compat.py)
redirected only the evaluator's API-restart command to the scoped native helper and
wrote to a new report directory. It called the unchanged five-case evaluator; it did
not restart a development container or overwrite the original reports.

```bash
uv run --no-sync python /workspace/pulse-verification-compat.py
uv run --no-sync python /workspace/pulse-verification-integrations.py
uv run --no-sync python /workspace/pulse-verification-web-check.py
```

The [integration driver](/workspace/pulse-verification-integrations.py) supplies
PULSE_TEST_POSTGRES_URL (existing pulse_test database with a temporary isolated schema),
PULSE_TEST_DOCKER=1 and PULSE_TEST_PROMETHEUS_URL=http://127.0.0.1:8109 in memory from
existing configuration, then executes exactly:

```bash
.venv/bin/pytest tests/test_integrations.py -q --tb=short
.venv/bin/alembic check
```

All **three integrations passed in 3.95 seconds**, and the isolated lab PostgreSQL
migration check found no new upgrade operations. PostgreSQL is real in the persistence
integration, while its adapter/Prometheus inputs are controlled fixtures. The Docker
integration uses a newly created disposable Alpine container that it removes; the
Prometheus integration queries the real healthy lab. Together with the ordinary run,
all **135 collected tests executed successfully** across the two runs. The three default
skips were therefore explicitly exercised, rather than remaining untested.
The [frontend proxy driver](/workspace/pulse-verification-web-check.py) checks production
HTML, anonymous denial, cookie login and matching canonical result/reason/evidence/
history/restart fields. It passed; this is not a browser interaction test.

## Earlier failures retained

The initial small-session startup failed because sandbox checkout files were mode 0600
and unreadable through a bind mount in the restricted gateway. The helper now stages
readable public source copies, mounts them read-only, and leaves checkout permissions
and secrets untouched.

[The initial cold-start evaluation](../examples/incident-lab/reports/verification-20261009T142353Z/summary.json)
correctly remained INCONCLUSIVE under the earlier 14-second total verification budget:
the first complete healthy sample arrived at 8.21 seconds, too late for full six-second
coverage. Both evaluators now use the normal 15-second startup grace. Freshness, source
coverage, stable duration and detection deadlines were not weakened.

[A later reporting attempt](../examples/incident-lab/reports/verification-20261009T143802Z/summary.json)
measured all four correct outcomes but failed persistence with HTTP 413: duplicating full
completed progress in the report timeline produced 517,591 bytes. Reports now retain
timeline references/verdict fields alongside the raw supporting samples/tool evidence;
the full event journal remains in the database. The existing 500KB API limit remains.
These failed attempts and successful reports are preserved; they are not counted as
passing evaluations.

## Limits and resource preservation

The session reused the existing PostgreSQL server with an isolated retained
`pulse_verification_lab` database, four scoped lab containers, an existing gateway image
with staged source, and a native loopback API. It did not create a duplicate development
stack. Development container identities, start times and restart counts were checked
against the original snapshot. This increment was not deployed into those containers.
No credentials, infrastructure permissions, releases, remote branches or onboarding
environment configuration were changed or published.

Prometheus scrape loss/restoration and API restart were real. Duplicate/out-of-order
observations, partial tools and contradictory evidence were exercised by controlled
regressions; a real Docker daemon outage was not injected. No live LLM or remote CI run
was attempted. Sampling establishes coverage only within the configured maximum gap;
it cannot prove health at unobserved instants. The existing single API worker and host
clock assumptions remain.

Use the focused session's cleanup command below; it preserves the database, named
volumes and timestamped reports. Ordinary `pulse lab down` has broader disposable-lab
cleanup semantics and was not used to delete retained data in this increment.

```bash
uv run --no-sync python examples/incident-lab/scripts/verification-session.py down
```

## Changed files and review artifact

This increment changes the following 25 source/document/test files relative to the
pre-existing uncommitted Phase 2 work, which was preserved:

```text
apps/api/gateway.py
apps/api/main.py
apps/web/src/components/dashboard.tsx
apps/web/src/lib/api.ts
docs/evaluation-methodology.md
docs/phase2-results.md
docs/recovery-verification.md
docs/verification-telemetry-results.md
examples/incident-lab/README.md
examples/incident-lab/scripts/verification-session.py
examples/incident-lab/services/demo-api/app.py
packages/pulse/core/remediation.py
packages/pulse/core/runtime.py
packages/pulse/core/schemas.py
packages/pulse/core/verification.py
packages/pulse/lab/catalog.py
packages/pulse/lab/cli.py
packages/pulse/lab/evaluate.py
packages/pulse/lab/telemetry_loss.py
packages/pulse/tools/docker_adapter.py
packages/pulse/tools/prometheus.py
tests/conftest.py
tests/test_integrations.py
tests/test_tools.py
tests/test_verification.py
```

The focused patch is `/workspace/pulse-recovery-verification.patch`. It excludes generated
report payloads and all credentials/caches; raw reports remain available at the linked
paths and in database evaluation history. No files were staged, committed or pushed.

## Final clean-start verification

```bash
uv run --no-sync python /workspace/pulse-verification-repeatability.py
uv run --no-sync pulse lab report --verification --format json
uv run --no-sync pulse lab report --verification --format markdown
git diff --check
git apply --reverse --check /workspace/pulse-recovery-verification.patch
```

The [repeatability driver](/workspace/pulse-verification-repeatability.py) invoked the
helper's scoped down/up/down operations and passed: exact stored verification/history/
action survived container recreation and native API restart; the incident stayed
RESOLVED with one mutation execution; original development container identities, start
times and restart counts matched; both credential-file hashes stayed unchanged.
Lab readiness now excludes stale discoveries while retaining their database records.
No test API PID or lab project container remains, and the temporary native frontend
was stopped. Named lab telemetry/journal volumes and the isolated database remain.
All seven pre-existing report files were preserved byte-for-byte. The final Markdown
was rendered from the unchanged measured JSON, with both canonical verdict explanations.
The final CLI exports passed consistency checks. No checks remain blocked.

Final retained PostgreSQL measurements: 44 incident rows and 29 evaluation rows in
`pulse_verification_lab`. Four named fault-state, gateway-journal and Prometheus volumes
remain. Disk usage after cleanup was 23GB used / 7.3GB available on the 32GB host.
A final actual token/password/provider-key scan passed across 67 report/document files.
