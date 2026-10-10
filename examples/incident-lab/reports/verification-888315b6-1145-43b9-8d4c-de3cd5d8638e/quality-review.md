# Pulse quality review

Status: ATTENTION_REQUIRED

| Scenario | Evidence | Comparison |
|---|---|---|
| telemetry-loss | PASS | INCOMPARABLE |
| container-crash | PASS | REGRESSED |
| memory-pressure | PASS | INCOMPARABLE |
| api-failure | PASS | STABLE |
| slow-response | PASS | INCOMPARABLE |
| recovery-verification | PASS | STABLE |

**telemetry-loss**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**container-crash**: A latency increase exceeded max(1 second, 25% of baseline). Reproduce under the same settings before concluding a performance regression.
- detection_latency_seconds: 3.28s → 4.62s (SLOWER).
- time_to_diagnosis_seconds: 0.28s → 0.35s (STABLE).

**memory-pressure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**api-failure**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 12.96s → 12.84s (STABLE).
- time_to_diagnosis_seconds: 2.10s → 2.18s (STABLE).

**slow-response**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**recovery-verification**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 8.88s → 9.90s (STABLE).
- time_to_diagnosis_seconds: 2.10s → 2.09s (STABLE).

Reviews describe recorded lab evaluations, not current service health or live-model accuracy.
Missing scenarios or incompatible baselines prevent a complete-suite improvement claim.
Latency thresholds are review heuristics; two runs do not prove a statistical performance change.
Follow-up work is advisory. No settings, approvals or resources are modified.
