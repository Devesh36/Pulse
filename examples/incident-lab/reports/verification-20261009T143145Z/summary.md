# Recovery evidence evaluation

Reasoning: mock/evidence. Observations: real Docker, HTTP probes and Prometheus.

| Scenario | Result | Verdict |
|---|---|---|
| container-crash | PASS | RECOVERED |

All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.
| api-failure | PASS | RECOVERED |

All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.
| recovery-verification | PASS | NOT_RECOVERED |

Observed continuing failure: docker_health_unhealthy, http_health_failed. Inspect the evidence before proposing another action.
| telemetry-loss | PASS | RECOVERED |

All required sources supplied fresh, ordered, post-action evidence throughout the stable recovery window.

Initial INCONCLUSIVE outcome: Recovery is inconclusive: prometheus: unavailable; request_count: unavailable. Restore reliable telemetry and request read-only re-verification; do not replay the remediation.
