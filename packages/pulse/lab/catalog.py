"""Public scenario controls. Evaluation assertions are kept in separate fixtures."""

SCENARIOS = {
    "telemetry-loss": {
        "service": "demo-api",
        "control": "errors",
        "description": "Existing HTTP failure recovery with selected metrics unavailable, API restart, and read-only re-verification.",
    },
    "container-crash": {
        "service": "demo-worker",
        "control": "crash",
        "description": "A synthetic worker exits unexpectedly.",
    },
    "memory-pressure": {
        "service": "demo-api",
        "control": "memory",
        "description": "A bounded workload gradually consumes container memory.",
    },
    "api-failure": {
        "service": "demo-api",
        "control": "errors",
        "description": "Synthetic orders requests return controlled HTTP errors.",
    },
    "slow-response": {
        "service": "demo-api",
        "control": "latency",
        "description": "Search requests experience a bounded response delay.",
    },
    "recovery-verification": {
        "service": "demo-worker",
        "control": "sticky",
        "description": "A persistent health failure tests ineffective remediation.",
    },
}
