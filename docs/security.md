# Threat model and operating assumptions

Pulse V1 is a single-administrator localhost tool for **trusted development containers**, not a public hosting platform or production auto-remediator. Administrative ports bind to `127.0.0.1`. Keep the gateway on the isolated Compose network with no published port. Do not expose it with a reverse proxy.

The installed repository companion uses two terminal-owned native processes:
API/dashboard on loopback and a separately authenticated gateway on the next
port. The native gateway has the operator's existing Docker access; this is not
an OS sandbox or privilege reduction. Its routes check the Compose project,
canonical working directory, service allowlist and existing labels. Do not
expose either port beyond the trusted host. Private project credentials/state
live outside the target repository. Scanning never executes target code or
sources its `.env`. Only explicitly eligible development services can receive
recovery proposals; permission, digest, expiry, audit and replay checks remain.

## Malicious operational evidence / prompt injection

Logs, health output, image names, service metadata, deployment labels, operational questions, and retrieved tool data can contain adversarial instructions. Pulse supplies them as data and instructs the investigator to ignore embedded instructions. The model may still misinterpret them; a prompt is not a security boundary.

The actual boundaries are typed read-only tools, a fixed function allowlist, affected-service checks, monitored-resource authorization, bounded log/health output, timeout/iteration/token limits, and infrastructure actions routed through separate approval/policy code. There is no arbitrary shell, Docker exec, file read, URL-fetch, arbitrary PromQL, container creation, deletion, or configuration-write tool. Evidence IDs are checked against successful tool results; missing references downgrade findings to unverified possibilities. This checks provenance, not truthfulness of model interpretation or application logs.

## Docker privilege

Access to the Docker socket is equivalent to host administration. Only the isolated gateway mounts it. The API and web containers have no socket or Docker filesystem mounts. The gateway runs with the permissions needed for that socket, drops Linux capabilities, and disallows privilege escalation, but a gateway process compromise can still use the socket directly.

Gateway authentication is a distinct secret; discovery/inspection require `pulse.monitor=true`. Start/restart additionally require `pulse.remediate=true` and `pulse.environment=development`, with fresh state checks. It exposes a narrow capability API rather than a generic Docker proxy. Labels are operator configuration and can be forged by anyone who already controls Docker. A compromised API can use its gateway credential within gateway label restrictions; the gateway does not independently prove a human approved an action. This is why both components must remain trusted and isolated.

## Unauthorized changes and replay

API telemetry and privileged routes require the administrator credential or a signed session. Session cookies are HttpOnly, SameSite Strict, and Secure when an HTTPS origin is configured. Browser mutations check exact Origin to prevent CSRF. CORS permits one configured origin. Invalid login attempts are rate limited. Secrets are neither hardcoded nor returned to the UI.

Monitoring permission, remediation permission, gateway labels, and per-action approval are separate controls. Immutable action UUIDs, reviewed content digests, expiration, transactionally consumed approval status, execution compare-and-set, and the durable gateway journal prevent duplicate/replayed actions through normal application APIs. The resource and policy are checked before approval and again before execution. An interrupted or timed-out mutation is never automatically replayed.

The emergency switch prevents new mutations at policy evaluation; the gateway environment switch adds an independent block. Neither undoes an action already dispatched to Docker. Do not interpret a disable toggle as cancellation of an in-flight start/restart.

## Credentials and retained evidence

`/demo` explicitly enrolls the selected repository for read-only observation of
its existing Compose containers without adding labels. The gateway requires a
nonempty project/root/service scope, checks canonical Compose working-directory
labels, preserves explicit monitoring opt-outs and excludes lab resources.
It rejects every recovery and fault-control operation independently of the API;
the API also denies approval and permission escalation and records denied
approval attempts. A demo does not change stored recovery permissions or run
application code. Normal monitoring retains its existing explicit labels and
digest-bound approval requirements.

`.env` has mode `0600`; secrets must stay out of source control. API settings report configured status and a sanitized base URL, never keys. Docker environment variables/mounts are omitted from evidence. Common password, token, API-key, authorization-header, known key-prefix, and URL credential patterns are redacted before evidence persistence or model submission. **Pattern redaction can miss secrets.** Avoid putting credentials or sensitive customer data in monitored application logs.

A configured cloud provider receives redacted questions and operational evidence. Use an approved/local endpoint when evidence must remain local. PostgreSQL volumes retain incident/tool/approval/audit/checkpoint data; samples have a 24-hour retention limit. Backups/retention/encryption/access control for the host and database remain operator responsibilities.

## HTTP and Prometheus

Verification URLs are server-side environment configuration, not model-supplied inputs. Schemes are HTTP/HTTPS, hosts must be allowlisted, credentials in URLs are rejected, deadlines apply, and redirects are disabled. The operator must trust allowed hosts and their DNS. Prometheus expressions come from fixed server-side templates with escaped service labels; broad arbitrary queries cannot be generated by the model. Prometheus itself is loopback-bound and not an Internet-exposed service.

## Failure isolation / limits

One API worker owns the monitoring/investigation tasks. Graceful shutdown cancels work; startup resumes investigations and verification but marks uncertain mutations for review. CPU/memory/restart/health/probe data is collected after mutations across a sustained observation window. Missing telemetry causes inconclusive verification. Checkpoint state and tool results are internal trusted storage, not an import format for arbitrary serialized objects.

The V1 rate limiter is in-memory and does not provide distributed protection. There is no multi-user RBAC, approval quorum, sandboxed model, TLS termination, multi-process ownership, or remote production isolation. Add these before broadening deployment.

Report a security issue privately to the repository maintainer; do not post logs, `.env`, database dumps, or working exploit secrets in public issues.
