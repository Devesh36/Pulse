# Remediation security

The LLM has read-only tools and can only propose typed actions. Allowed mutations are
start/restart and three fault-specific resets. Before approval and again before execution,
Pulse checks the immutable digest, expiry, monitored/remediation permissions, exact
container identity, current state, development/remediation labels, and emergency disable.
Fault resets additionally require `pulse.lab=pulse-lab`, the exact Compose project, and
`demo-api`. The gateway independently checks the project and fixed demo DNS/service mapping.

Approval atomically changes proposal and incident state. Execution claims an approved
row once. The gateway persists the action ID in a separate journal **before** executing;
crash/timeout means an uncertain result and no replay. Explicit approvals, denials,
executions, failures, and reset operations are audited. The lab evaluator has a dedicated
resource-scoped principal; `--approve` is required. Duplicate and anonymous approval attempts
are tested through the real API, not an adapter shortcut.

All demo controls are token protected and internal to the lab network, with no published
fault ports. No model-supplied URL chooses a fault endpoint. Public API/dashboard ports
bind to loopback. Demos are non-root, unprivileged, capability-dropped, CPU/memory limited,
and have no Docker socket or host secret mounts. Only the private gateway mounts the socket;
it runs as root to reach the daemon, drops capabilities, and is not publicly exposed.
The socket still grants host-administration power to a compromised gateway; labels are an
application scope boundary, not protection against an administrator altering Docker labels.

The administrator, gateway, fault-control, and test-principal tokens are distinct locally
generated credentials. `.env` is ignored and mode 0600. Provider secrets are server-side.
Reports contain redacted telemetry and public action digests, not credential files/headers.
Pattern-based redaction cannot guarantee every arbitrary application's secret is detected.
The CA passed to builds is public trust material, not a production credential; TLS and
artifact hashes remain enabled.

Cleanup cannot silently reset an active pending incident through the dashboard. The CLI
explicitly cancels/dismisses investigations, waits for active execution, then cleans the
lab workloads. Teardown deletes only the fixed project's resources and labeled lab image
tags. It never prunes unrelated containers, volumes, or shared images.
