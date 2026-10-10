# Phase 3: Continuous quality feedback

Pulse now reviews retained incident-lab evaluations and turns observed failures,
missing evidence and latency changes into concrete follow-up work. This is a
read-only feedback loop: **measure → compare → review → fix → add a regression →
measure again**. It does not tune thresholds, approve actions or modify services.

## Use it

In `pulse repl`, type **quality** or **7** to review saved reports, even after the
lab is stopped. The local **Incident Lab** dashboard has a **Continuous improvement**
section using the same review rules and persisted evaluation history.

```bash
# Authenticated review of database history; the lab API must be running.
pulse lab quality
pulse lab quality --format json

# Offline review: no Docker, API, credential creation or resource mutation.
pulse lab quality --reports-dir examples/incident-lab/reports

# Exit 2 for a current failed evaluation or a regression flag.
pulse lab quality --reports-dir examples/incident-lab/reports --fail-on-regression

# Strict gate: also exit 2 for missing scenarios/evidence or incompatible baselines.
pulse lab quality --reports-dir examples/incident-lab/reports --check
```

Paths above are relative to a development checkout. Installed users can pass their
retained reports directory printed by the REPL. Ordinary review exits 0 when it
successfully produces a review, even if that review needs attention; invalid input
or an unavailable API exits 1. The explicit gate flags use exit 2. No gate authorizes
an incident action. CLI JSON and Markdown, the REPL and the dashboard use the same
Python comparison rules.

## Evidence and comparisons

Each new evaluation records a unique run ID, complete runtime settings, suite
version, reasoning mode, scenario targets, source timestamps and healthy baseline.
Normal evaluations write unique `run-<uuid>` directories, while telemetry-restoration
runs use `verification-<uuid>`. Earlier reports and databases are preserved.
Summary lookup finds the latest saved report, including new run directories.
New scenario archives also include the API's recording timestamp and record ID,
so offline reviews use the same ordering and references as database reviews.

A passing quality assessment requires a completed evaluation, measured detection
and diagnosis timing, required diagnosis tools/citations, recorded verification
samples/requirements/reason, correct expected verdict/state, approval and replay
checks, and at least fourteen seconds of healthy baseline with no false positives.
The telemetry-loss case additionally requires its initial INCONCLUSIVE result,
restart deadline preservation, no duplicate incident and one mutation execution.
An expected ineffective action is a passing test when it returns NOT_RECOVERED;
INCONCLUSIVE cannot substitute for that observed continuing failure.

The latest two records **per scenario** are compared only when suite, complete
settings, targets and reasoning mode match, run IDs differ and timestamps are
ordered. An old report without this context is retained but cannot establish an
improvement. Replayed or out-of-order runs, contradictory scenario identity,
malformed measurements, partial evidence and changed settings remain explicit.
Copies of the same offline report are deduplicated; conflicting copies block review.
Offline inputs are bounded to 4 MiB per formatted JSON file and 1,000 files. This
allows retained historical reports and pretty-printed exports; the API's existing
500,000-character upload limit remains unchanged.

The review reports PASS, FAILED, INSUFFICIENT_EVIDENCE or NOT_RUN, separately from
STABLE, IMPROVED, REGRESSED, PERSISTING_FAILURE, NO_BASELINE, INCOMPARABLE or
INCONCLUSIVE comparison results. Current failures always require attention, even
when their baseline or other evidence is unavailable. Each issue includes a fixed,
actionable explanation; arbitrary report errors, credentials and raw tool payloads
are not echoed by the quality review.

A latency change is flagged when its magnitude exceeds **max(1 second, 25% of
baseline)**. This is a review heuristic, not statistical proof from two samples.
Repeat a compatible run before concluding a performance change. Detection must
still meet the original fixture deadline; Pulse does not relax it to pass a review.

## Continuous operation

The existing weekly/manual GitHub incident-lab workflow now exports the review
alongside its evaluation artifact and fails on observed failures/regression flags.
Missing baselines remain visible instead of failing that non-strict gate. To require
complete compatible coverage, use `--check`. The workflow retains its existing
permissions and performs its existing explicitly scoped lab evaluations; the quality
step itself runs offline. Remote workflow success is separate from local validation.

No new database table or migration is needed: API reviews read the existing
`LabEvaluation` records, limited to two records per known scenario. They survive API
restarts without replacing incident, approval or audit history. The authenticated
endpoint is `GET /api/v1/lab/quality`. Read requests create no approvals or audits.

## Limits and subsequent increments

See [Phase 3 validation results](phase3-results.md) for commands, measured telemetry,
the detected latency flag and remaining baseline gaps.

These reviews describe **recorded evaluations**, not current production health.
They score authenticated, redacted reports; they do not independently attest that
every uploaded report originated from real telemetry.
Real Docker/Prometheus observations remain distinct from mock/deterministic reasoning.
No live-model accuracy, automatic learning, statistical benchmarking or unlimited
background remediation is claimed. Database and offline views agree when they contain
the same receipted reports; unavailable or different histories remain explicit.
Earlier archives without receipts use their completion timestamp (or file timestamp
when unavailable), and cannot reconstruct the exact database recording order.

Next candidates are repeated-run latency distributions, endpoint-specific diagnosis
and operator-reviewed incident postmortems. Each should have its own evidence,
regression tests and bounded rollout; this phase implements the quality feedback
foundation rather than claiming those capabilities are complete.
