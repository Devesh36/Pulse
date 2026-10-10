# Recovery evidence evaluation

Reasoning: mock/evidence. Observations: real Docker, HTTP probes and Prometheus.

| Scenario | Result | Verdict |
|---|---|---|
| container-crash | FAIL | INCONCLUSIVE |

Recovery is inconclusive: insufficient uninterrupted fresh observations before the deadline. Restore reliable telemetry and request read-only re-verification; do not replay the remediation.

Evaluation failed: AssertionError: AssertionError: Recovery classification did not match measured fault outcome
