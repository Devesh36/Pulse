# Evaluation methodology

Evaluator fixtures are individual JSON manifests under `examples/incident-lab/fixtures`.
They specify service, trigger signal, category, expected action/outcome, required real tools,
and fixed detection deadlines. They are loaded only by the host evaluator and never supplied
to the agent. A category assertion alone is insufficient: crash checks exit 42, the retrieved
crash log and real `die` event; memory checks actual utilization; HTTP cases require real
finite Prometheus measurements. Citations must reference successful persisted tool executions.
Affected service identity is compared to the actual discovered container.

Each run measures a 14-second healthy baseline, injects the real fault, records incident
creation time, waits for investigation, validates evidence/action, verifies anonymous and
duplicate approval denial, approves through the dedicated principal, waits for sustained
recovery, records results, and resets. Original runtime settings are restored. The evaluator
uses a two-second poll, two consecutive samples, ten-second metric windows, six-second stable
verification, five minimum HTTP requests, 60% memory detection/40% recovery, 1500/200 ms latency
thresholds, and 20%/5% error thresholds. These are explicit **lab settings**, not claimed
production defaults. Detection deadlines remain 30 seconds for crash and 60 seconds for
other cases; they are not silently increased.

Metrics: detection rate counts newly identified expected incidents; detection latency is
incident timestamp minus injection request start; diagnosis latency uses the persisted
`investigation.diagnosed` event. Root-cause accuracy scores the four primary categories with
numeric/tool evidence checks. Verification accuracy includes the deliberately unsuccessful
restart; remediation recovery rate scores only the four intended positive recoveries.
False-positive count covers measured baseline exposure only. Tool calls/tokens are actual
recorded executions/provider usage; no-provider cost is zero and unavailable live pricing is
null. Targets are separate from measurements. Human approval enforcement is tested per
scenario, not extrapolated to arbitrary infrastructure.

Reports include JSON details, a JSON summary, Markdown summary, persisted backend history,
and the mode (`deterministic-evidence`, `mock-model`, or `live-model`). Model-unavailable
fallback is not accepted as live-model accuracy. Tests of mocked decisions use actual
typed responses but cannot establish live reasoning quality. Even validated evidence IDs
do not mechanically prove every free-text conclusion: manual review remains necessary.

Restarting the API checks that incidents retain their final states. `pulse lab down`
separately verifies resource removal, including project image tags. Report files survive
teardown; the disposable database and metric volumes do not. CI always performs cleanup,
including when a scenario fails. Unexpected baseline incidents stop the evaluation rather
than being ignored. Failures and skipped/unrun checks remain explicit.

The recovery evidence increment uses the normal fifteen-second startup grace in both
evaluation harnesses, while retaining six-second stability and the original 30/60-second
detection deadlines. A measured cold-start run first received complete healthy evidence at
8.21 seconds and correctly remained inconclusive under the previous fourteen-second total
verification budget. Strict deadline/source coverage checks are not relaxed; that failed
evaluation is preserved. See `verification-telemetry-results.md`.
