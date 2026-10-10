# Pulse quality review

Status: INSUFFICIENT_EVIDENCE

| Scenario | Evidence | Comparison |
|---|---|---|
| telemetry-loss | INSUFFICIENT_EVIDENCE | INCOMPARABLE |
| container-crash | PASS | STABLE |
| memory-pressure | PASS | INCOMPARABLE |
| api-failure | PASS | INCOMPARABLE |
| slow-response | PASS | INCOMPARABLE |
| recovery-verification | PASS | INCOMPARABLE |

**telemetry-loss**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.
- Evaluation settings or suite version are unavailable. Run the current evaluator to record comparable settings; preserve this historical report.
- No evaluation run identity was recorded. Run the current evaluator; do not infer a baseline from file names.
- Evaluation timestamps are missing, reversed or in the future. Check the evaluator clock and record a completed, ordered run.
- An expected or observed verification verdict is unavailable. Record the scenario's expected outcome and completed verification evidence.
- A required latency measurement is unavailable or invalid. Record measured detection and diagnosis timestamps; never substitute zero.
- A configured detection deadline is unavailable. Record the scenario fixture's original detection deadline.
- Healthy baseline exposure or false-positive measurements are missing. Record at least fourteen seconds of healthy baseline exposure before injecting a fault.

**container-crash**: Both compatible evaluations passed; no latency change exceeded the review threshold.
- detection_latency_seconds: 4.52s → 3.47s (STABLE).
- time_to_diagnosis_seconds: 0.29s → 0.32s (STABLE).

**memory-pressure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**api-failure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**slow-response**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**recovery-verification**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

Reviews describe recorded lab evaluations, not current service health or live-model accuracy.
Missing scenarios or incompatible baselines prevent a complete-suite improvement claim.
Latency thresholds are review heuristics; two runs do not prove a statistical performance change.
Follow-up work is advisory. No settings, approvals or resources are modified.
