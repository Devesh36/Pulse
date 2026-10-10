# Recovery evidence evaluation

Reasoning: mock/evidence. Observations: real Docker, HTTP probes and Prometheus.

| Scenario | Result | Verdict |
|---|---|---|
| container-crash | PASS | RECOVERED |
| api-failure | PASS | RECOVERED |
| recovery-verification | PASS | NOT_RECOVERED |
| telemetry-loss | PASS | INCONCLUSIVE → RECOVERED |

**container-crash**: All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.

**api-failure**: All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.

**recovery-verification**: Observed continuing failure: http_health_failed, docker_health_unhealthy. Inspect the evidence before proposing another action.

**telemetry-loss**: All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.

Initial INCONCLUSIVE outcome: Recovery is inconclusive: prometheus: unavailable; request_count: unavailable; deadline: observation_after_deadline. Restore reliable telemetry and request read-only re-verification; do not replay the remediation.
