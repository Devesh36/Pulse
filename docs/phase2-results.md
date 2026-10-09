# Pulse Phase 2 completion report

Subsequent recovery evidence improvements are recorded in [the focused verification report](verification-telemetry-results.md).

Validated on 2026-10-09. All five real fault-to-report scenarios pass. The implementation
is a working incident laboratory; incomplete and unverified capabilities are listed below.

## A. Implemented features

- Isolated, labeled Compose laboratory with bounded non-root API/worker workloads,
  protected controls, PostgreSQL, Prometheus, private Docker gateway, and optional dashboard.
- Real process crash, gradual memory allocation, HTTP errors, delayed responses, and
  persistent health failure that survives an ineffective restart.
- Actual Docker inspect/stats/logs/events and application counters/histograms; rolling
  detection, deduplication, stale sample handling, source timestamps, minimum request counts.
- Existing LangGraph investigations with real tools, cited structured hypotheses,
  persistent checkpoints, budgets, concurrency/backpressure limits, cancellation, and audits.
- Scoped proposals/reset actions, expiring digest-bound approvals, fresh policy revalidation,
  durable idempotency journal, emergency disable, execution audit, and approval actor identity.
- Shared post-action recovery verification with stability windows, separate thresholds,
  and RECOVERED / NOT_RECOVERED / INCONCLUSIVE / VERIFICATION_FAILED outcomes.
- Five hidden ground-truth manifests, actual evaluation measurements, healthy baselines,
  anonymous/replay approval denial, API restart persistence, JSON/Markdown reports.
- Lab dashboard displaying backend status/metrics, scenarios, evidence/investigation links,
  existing manual approval controls, verification, and persisted evaluation history.
- Fast/integration/full-lab CI workflows, Pyright, migration validation, tests and documentation.

## B. Architecture

Instrumented workloads feed Prometheus; the deterministic monitor reads fixed PromQL and
actual Docker observations through a private project-scoped gateway. PostgreSQL persists
samples, incidents, tool evidence, diagnoses, proposals, execution and evaluation records.
LangGraph collects audited read-only evidence and proposes actions. The operator or expressly
authorized test principal approves an immutable proposal; policy and gateway revalidate
resource scope and claim execution once. The shared verifier observes fresh post-action
health/metrics before resolving the incident. Next.js uses the same authenticated APIs.
Host-side evaluator manifests never enter investigator context or the API image.

## C. Repository changes

- `examples/incident-lab/`: Compose, workloads, hashed dependency lock, scrape configuration,
  fixtures, guide, and measured reports.
- `packages/pulse/lab/`: working CLI, public catalog, hidden-fixture evaluator.
- `packages/pulse/core/`, `tools/`, `agents/`: telemetry freshness, queue/budget bounds,
  richer evidence, lab actions, verification, actual events, redaction and tool output cap.
- `packages/pulse/db/`, `apps/api/`: evaluation migration/model, scoped lab API/test principal,
  cancellation, approval actor, stale metric handling, trusted container builds.
- `apps/web/`: lab route/component, reset action approval, styles and API types.
- `.github/workflows/`, `tests/test_phase2.py`, `tests/test_integrations.py`,
  `pyrightconfig.json`, dependencies, README and eight Phase 2 documentation files.

## D. Run instructions

```bash
uv sync --frozen
uv run python scripts/setup-env.py
docker compose up -d --build

uv run pulse lab up --dashboard
uv run pulse lab status
uv run pulse lab run container-crash --approve
uv run pulse lab run memory-pressure --approve
uv run pulse lab run api-failure --approve
uv run pulse lab run slow-response --approve
uv run pulse lab run recovery-verification --approve
uv run pulse lab evaluate --all --approve
uv run pulse lab report --format json
uv run pulse lab report --format markdown
uv run pulse lab reset
uv run pulse lab down
```

`--approve` explicitly authorizes the evaluator through the real scoped approval API.
Interactive users inject from the dashboard and review/approve the incident proposal.
An unset model uses deterministic evidence analysis; CI uses `PULSE_LLM_MODEL=mock/evidence`.
Optional live provider configuration is documented in the lab README. The cloud CLI passes
the trusted CA as a build secret without disabling TLS. Docker vfs on this 32 GB cloud disk
needed disposable build-cache cleanup; the initial combined dashboard launch ran out of
space after its images built. This is an environment limitation, not a successful launch.
The Docker dashboard subsequently started from those built images after clearing unused
build cache and temporarily pausing the original development containers, without deleting
their images or persistent volumes. Its production HTML, authentication and live API proxy
checks passed. Updated reusable cloud setup/start instructions were saved as a draft;
the draft still requires review, saving and publishing in environment settings.

## E. Test results

- Baseline: **66 passed, 2 skipped**; original real Docker crash acceptance also passed.
- Final suite: **88 passed, 3 skipped, 0 failed**, 22.31 seconds. The skipped tests opt into
  PostgreSQL, Docker and Prometheus.
- All three opt-in integrations executed separately: **3 passed, 0 failed, 0 skipped**,
  4.14 seconds. All **91 unique collected tests** executed across these runs.
- Ruff lint/format and Pyright passed; zero type errors.
- Frontend formatting, TypeScript checking and production build passed.
- Native and Docker production dashboard HTML/authentication/cookie/API proxy/status/history passed.
  Browser interactions were not tested and no screenshot was generated.
- Original and lab/dashboard Compose configurations validated. Workflow YAML parsed locally.
- SQLite upgrade/check/downgrade/re-upgrade passed; live PostgreSQL `alembic check` found
  no new upgrade operations.
- Five real scenarios passed in deterministic evidence and mock-model evaluation.

Measured current mock run: crash 1.55 s, memory 7.41 s, HTTP failure 10.31 s, latency 12.08 s, negative verification 5.81 s detection. **5/5 detected; 4/4 primary categories correct;
0 baseline false positives; 4/4 positive recoveries; 5/5 verification decisions correct.**
The five healthy baselines each lasted 14 seconds. Every scenario rejected anonymous and
duplicate approval and recorded the lab-test approval actor. The ineffective restart correctly
returned NOT_RECOVERED and did not resolve its incident. States survived an API restart.
No-provider token usage/cost is zero; live pricing is unknown. Exact current measurements,
actual tool evidence, samples and pre/post-action state are retained in
`examples/incident-lab/reports/evaluation-summary.{json,md}` and five scenario JSON files.

`pulse lab down` verified removal of project containers, networks, volumes and build image
tags. Shared upstream images and host reports remain. The original Pulse stack was preserved.
The failed disk-exhausted dashboard attempt was also cleaned up. A successful teardown does
not erase earlier failed attempts from this report.
After final lab teardown, the original development stack was restored using the newly
validated backend/dashboard images. Its PostgreSQL migration applied at API startup; API,
authenticated web proxy, Docker discovery, original demo health, and both Prometheus targets
passed the readiness check. Only superseded build images from this setup were retired.

## F. Security review

The model cannot execute shell commands, supply arbitrary URLs/PromQL or mutate Docker.
Identity, permissions, development labels, exact project and fixed demo service are checked
at independent API/policy/gateway boundaries. Approval binds the digest and expiry; rejected,
expired or duplicate proposals cannot execute. Every tool execution, including cancellation,
is audited. Oversized redacted output is unavailable failed evidence, not partially successful.

Demo containers have bounded resources, dropped capabilities, no privileges, published fault
ports, Docker socket or host secret mounts. Public ports bind loopback; the gateway is private.
Distinct local credentials are random, ignored, mode 0600. Actual report contents were scanned
against local credential values. Provider keys stay server-side. Cleanup requires explicit
cancellation/dismissal before resetting active incidents.

Remaining risks: a compromised Docker-socket gateway has host-administration power; Docker
labels are application policy, not a hostile-host sandbox. Pattern redaction cannot detect
every application's arbitrary secret. See `remediation-security.md`.

## G. Known limitations / incomplete or unverified requirements

- **Unverified:** optional live LLM evaluation. No provider credentials were used; mock and
  deterministic success cannot establish live reasoning quality or cost.
- **Partial:** HTTP incident detection aggregates by service. Endpoint labels/logs exist;
  endpoint-specific grouping and dependency-aware causal analysis remain incomplete.
- **Unverified end-to-end:** INCONCLUSIVE and VERIFICATION_FAILED have unit coverage;
  real infrastructure evaluation exercised RECOVERED and NOT_RECOVERED.
- **Partial:** numeric evidence, citations, service and category are checked mechanically.
  Free-text hypotheses still require documented manual review.
- **Partial:** the worker runs real bounded instrumented background traffic, rather than a
  distributed queue/broker. Durable job and queue-backlog diagnosis are not implemented.
- **Partial:** scenario cleanup resets the disposable workloads together. Dedicated per-scenario
  reset CLI commands are not provided; approved fault-specific reset actions are supported.
- **Unverified:** remote GitHub Actions and browser interaction execution. Local equivalent
  checks passed; no remote workflow success or screenshot is claimed.
- **Partial:** read-only checkpoint progress is inspectable; interrupted mutations are not
  automatically resumed or replayed.
- No OpenTelemetry, Kubernetes, production scaling/TLS termination or arbitrary application
  instrumentation added. Metrics use the demo schema; the API uses one worker.
- Baseline and latency results describe these controlled runs, not production reliability.
- Cloud Docker vfs duplicates layers and exhausted this disk during simultaneous development
  stack/dashboard launch. Docker dashboard checks subsequently passed with the original
  development containers paused and unused build cache removed. Adequate disk space remains
  required; simultaneous stacks were not supported by this host's disk capacity.

## H. Next development milestones

1. Live-provider evaluation with reviewed semantic scoring, token pricing and repeated runs.
2. Endpoint/dependency grouping and OpenTelemetry trace correlation.
3. Real telemetry-loss/inconclusive verification, provider outage, recovery timeout,
   crash-interruption and browser approval tests in CI.
4. Stronger host isolation or an external least-privilege executor, production identity and TLS.
5. Queue-worker telemetry, per-scenario reset, read-only checkpoint resume, data retention,
   and larger baseline/latency studies.
