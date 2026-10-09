# Investigation engine

The existing LangGraph collect/reason graph and PostgreSQL checkpoint saver are retained.
Initial evidence is inspection, current metrics plus a bounded persisted trend, recent
logs, restart history, lab lifecycle events, and HTTP metrics when relevant. The model can
request more scoped, typed tools or return a structured diagnosis/proposal.

Tool arguments cannot contain arbitrary shell commands, file paths, URLs, or PromQL.
Every executed tool records arguments, redacted structured output, success/failure, time,
and duration. Timeouts and cancellation are audited. Logs/tool output are untrusted data,
never executable instructions. `PULSE_TOOL_MAX_OUTPUT_BYTES` bounds each redacted result
(default 65,536 bytes).
Oversized output is recorded as unavailable failed evidence, rather than a partial successful
observation. The model can request a smaller bounded collection.
Only validated evidence IDs survive model output validation;
unsupported findings become unverified possibilities, with low confidence.

Diagnoses preserve the original summary/symptoms/timeline/root-cause finding API and add
incident ID, category, observed evidence references, likely cause, and recommended action.
Findings distinguish observations, supported hypotheses, and unverified possibilities.
Increased memory alone is not called a confirmed leak. Deterministic mode reports low
qualitative confidence and uncertainty; it is not presented as external AI reasoning.

Settings bound iterations, total tool calls, wall-clock duration, model token budget,
concurrent investigations, and pending investigations. Pending work remains `DETECTED`
and is reconsidered by the monitor when queue capacity returns. The concurrency semaphore
is initialized at API startup; restart the single API worker to apply a changed concurrency
limit. Operator cancellation records a failed investigation and preserves checkpoint/audit
history. Interrupted mutations are never replayed.

Mock CI responses are restricted to `mock/evidence` in the lab. They derive structured
responses from supplied real evidence, not evaluator fixtures. An optional LiteLLM live
provider uses function calls, explicit token/time limits, no automatic provider retry,
and deterministic fallback on failure. Reported provider token usage covers successfully
validated responses; failed provider responses may have unknown usage/cost. Live semantic
accuracy is unverified unless that mode was actually executed and manually assessed.
