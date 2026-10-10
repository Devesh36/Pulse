# Pulse quality review

Status: INSUFFICIENT_EVIDENCE

| Scenario | Evidence | Comparison |
|---|---|---|
| telemetry-loss | INSUFFICIENT_EVIDENCE | INCOMPARABLE |
| container-crash | PASS | INCOMPARABLE |
| memory-pressure | PASS | INCOMPARABLE |
| api-failure | PASS | INCOMPARABLE |
| slow-response | PASS | INCOMPARABLE |
| recovery-verification | PASS | INCOMPARABLE |

**telemetry-loss**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.
- Evaluation timestamps are missing, reversed or in the future. Check the evaluator clock and record a completed, ordered run.

**container-crash**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**memory-pressure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**api-failure**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**slow-response**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

**recovery-verification**: Settings, suite, targets or reasoning mode differ, or run identity/time ordering is unavailable. Record a new compatible baseline.

Reviews describe recorded lab evaluations, not current service health or live-model accuracy.
Missing scenarios or incompatible baselines prevent a complete-suite improvement claim.
Latency thresholds are review heuristics; two runs do not prove a statistical performance change.
Follow-up work is advisory. No settings, approvals or resources are modified.
