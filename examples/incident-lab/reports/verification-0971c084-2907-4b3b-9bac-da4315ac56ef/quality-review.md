# Pulse quality review

Status: INSUFFICIENT_EVIDENCE

| Scenario | Evidence | Comparison |
|---|---|---|
| telemetry-loss | PASS | STABLE |
| container-crash | PASS | STABLE |
| memory-pressure | PASS | INCOMPARABLE |
| api-failure | PASS | STABLE |
| slow-response | PASS | INCOMPARABLE |
| recovery-verification | PASS | STABLE |

**telemetry-loss**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 10.27s → 10.57s (STABLE).
- time_to_diagnosis_seconds: 2.10s → 2.16s (STABLE).

**container-crash**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 4.62s → 3.97s (STABLE).
- time_to_diagnosis_seconds: 0.35s → 0.36s (STABLE).

**memory-pressure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**api-failure**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 12.84s → 13.22s (STABLE).
- time_to_diagnosis_seconds: 2.18s → 2.10s (STABLE).

**slow-response**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**recovery-verification**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 9.90s → 10.34s (STABLE).
- time_to_diagnosis_seconds: 2.09s → 2.07s (STABLE).

Reviews describe recorded lab evaluations, not current service health or live-model accuracy.
Missing scenarios or incompatible baselines prevent a complete-suite improvement claim.
Latency thresholds are review heuristics; two runs do not prove a statistical performance change.
Follow-up work is advisory. No settings, approvals or resources are modified.
