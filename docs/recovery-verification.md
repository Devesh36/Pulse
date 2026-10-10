# Recovery verification

Verification version 2 persists its frozen policy, original wall-clock deadline, required
sources, accepted source watermarks, per-condition evidence, healthy source spans, observation
samples, and reason in the existing incident JSON. No database schema change is required.
Each sample and its supporting `verification.sample` event commit together. Completion and
VERIFYING → RESOLVED/FAILED commit atomically with the final verdict and completion event.
The current JSON retains the latest 300 samples; every sample remains in the event history.

Required evidence includes fresh Docker state and Docker metrics; HTTP error/latency incidents
also require the corresponding Prometheus measurement and minimum request volume. An
allowlisted configured health probe is required when present. Docker stats use the daemon's
actual `read` timestamp, rather than receipt time. Prometheus queries and source checks share
one pinned evaluation time. The oldest relevant source-series timestamp and scrape `up`
state are checked; retained rolling values cannot establish health after a failed scrape.

Sources must identify the correct container/service/metric, have valid finite values,
be post-action (and post-recheck when applicable), remain within the freshness budget,
and advance strictly beyond their persisted watermark. Missing fields, unavailable sources,
timeouts, duplicates, out-of-order/future timestamps, wrong resources, insufficient traffic,
and contradictory health evidence cannot contribute to a healthy streak. Component calls
run independently with bounded timeouts, retaining successful results when another fails.
Every sample records required/received evidence, accepted timestamps, rejection reasons,
condition evidence and contradictions. A source or observation gap resets the streak.

Recovery requires at least two complete observations, the configured stable duration, and
that duration of advancement from **every required source**. Rapidly delivered buffered
samples cannot satisfy a recovery window by receipt time alone. The default maximum gap is
twice the sampling interval plus one second; `verification_max_gap_seconds` can override it.
An observation after the persisted deadline cannot establish recovery.

| Result | Meaning | Incident state |
|---|---|---|
| RECOVERED | All required sources demonstrate sustained fresh recovery | RESOLVED |
| NOT_RECOVERED | Trustworthy, still-fresh condition evidence demonstrates continuing failure | FAILED |
| INCONCLUSIVE | Required evidence or continuous source coverage is insufficient or contradictory | FAILED |
| VERIFICATION_FAILED | Verification policy itself failed | FAILED |

Unknown data does not erase still-fresh observed failure. Later trustworthy healthy evidence
supersedes the corresponding earlier failure; expired failure evidence remains in history
without being represented as current failure. Contradictions invalidate their affected
conditions and always prevent confirmation. A healthy final sample without a full window
remains inconclusive. Legacy `outcome` values remain confirmed/failed/inconclusive, with
running used during progress; the explicit result and explanation are also returned.

API startup resumes VERIFYING observations from committed progress and the original deadline.
Unobserved restart time resets source coverage/stability, never extends the deadline, and never
replays the action. A recorded completed action interrupted before VERIFYING resumes only
observations. Unknown interrupted mutations remain failed/inconclusive without execution replay.
Missing execution baselines produce explicit durable inconclusive outcomes.

After restoring telemetry, an operator can POST
`/api/v1/incidents/{id}/verification/recheck`. Only a FAILED/INCONCLUSIVE incident with a
matching, unmodified recorded executed action and monitored resource is eligible. This adds
one guarded FAILED → VERIFYING edge using the existing states; observed failures cannot use
it. It opens an expressly requested read-only observation window, preserves the prior attempt,
and can resolve the same incident after sustained recovery. It does not change approval,
expiry, action digest or execution status and never invokes mutation. Concurrent requests
are rejected. FAILED retains its unique active incident key until recovery/dismissal.

The API, incident dashboard and evaluation reports share the same result/reason/evidence.
The dashboard offers the read-only recheck only for an inconclusive failed incident.
See [the focused real evaluation](verification-telemetry-results.md).
