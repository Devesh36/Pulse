# Incident lab evaluation

Mode: mock-model

| Scenario | Result | Detection seconds | Verification |
|---|---|---:|---|
| container-crash | PASS | 4.49 | RECOVERED |
| memory-pressure | PASS | 12.58 | RECOVERED |
| api-failure | PASS | 11.42 | RECOVERED |
| slow-response | PASS | 13.66 | RECOVERED |
| recovery-verification | PASS | 11.82 | NOT_RECOVERED |

Measured results:

```json
{
  "scenario_count": 5,
  "passed": 5,
  "detection_rate": 1.0,
  "root_cause_accuracy": 1.0,
  "false_positive_count": 0,
  "remediation_recovery_rate": 1.0,
  "verification_accuracy": 1.0
}
```

Persistence after API restart: True

Deterministic evidence analysis is not live-model reasoning accuracy.
False-positive exposure is limited to the measured healthy baseline durations.
Resource removal is verified by pulse lab down, independently of scenario reset.
