"use strict";
const $ = (id) => document.getElementById(id);
let readOnly = false;
let timer,
  selected,
  report,
  pending,
  busy = false;
async function api(path, method = "GET", body) {
  const response = await fetch(`/api/v1${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    if (response.status === 401) {
      clearInterval(timer);
      $("workspace").hidden = true;
      $("login").hidden = false;
    }
    throw new Error(
      response.status === 401
        ? "Sign in with this project’s administrator token."
        : `Request failed (${response.status}). Review the incident and current permissions before retrying.`,
    );
  }
  return response.json();
}
function text(tag, value, className) {
  const el = document.createElement(tag);
  el.textContent = value;
  if (className) el.className = className;
  return el;
}
function button(label, action, disabled = false) {
  const el = text("button", label);
  el.disabled = disabled;
  el.addEventListener("click", async () => {
    if (busy) return;
    busy = true;
    el.disabled = true;
    try {
      await action();
      $("error").hidden = true;
      await refresh();
    } catch (error) {
      showError(error);
    } finally {
      busy = false;
      el.disabled = disabled;
    }
  });
  return el;
}
function showError(error) {
  $("error").textContent = error.message;
  $("error").hidden = false;
}
function jsonDetails(label, data) {
  const el = document.createElement("details");
  el.append(text("summary", label), text("pre", JSON.stringify(data, null, 2)));
  return el;
}
async function detail(id) {
  selected = id;
  const [incident, timeline] = await Promise.all([
    api(`/incidents/${id}`),
    api(`/incidents/${id}/timeline`),
  ]);
  report = { ...incident, timeline };
  const container = $("detail");
  container.replaceChildren(
    text("h3", incident.title),
    text("p", `${incident.state} · ${incident.kind}`, "badge"),
  );
  if (incident.diagnosis)
    container.append(
      jsonDetails("Diagnosis and citations", incident.diagnosis),
    );
  container.append(
    jsonDetails("Detection evidence", incident.detection),
    jsonDetails("Tool evidence", incident.tools),
    jsonDetails("Timeline", timeline),
  );
  if (incident.verification) {
    container.append(
      text(
        "h3",
        `Verification: ${incident.verification.result || "in progress"}`,
      ),
      text(
        "p",
        incident.verification.reason || "Collecting required observations.",
      ),
      jsonDetails("Verification measurements", incident.verification),
    );
    if (
      ["INCONCLUSIVE", "VERIFICATION_FAILED"].includes(
        incident.verification.result,
      )
    )
      container.append(
        button("Recheck evidence (read-only)", () =>
          api(`/incidents/${id}/verification/recheck`, "POST", {}),
        ),
      );
  }
  for (const action of incident.actions || []) {
    container.append(
      text("h3", `${action.kind} · ${action.status}`),
      text("p", action.reason),
    );
    if (action.status === "proposed") {
      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(
        button(
          "Review Pulse’s proposed fix",
          async () => {
            pending = action;
            $("proposal").textContent = JSON.stringify(
              {
                action: action.kind,
                container: action.container_id,
                reason: action.reason,
                digest: action.digest,
                expires: new Date(action.expires_at * 1000).toISOString(),
              },
              null,
              2,
            );
            $("review").showModal();
          },
          readOnly ||
            incident.state !== "AWAITING_APPROVAL" ||
            action.expires_at * 1000 <= Date.now(),
        ),
        button("I’ll handle it · reject proposal", () =>
          api(`/remediations/${action.id}/reject`, "POST", {}),
        ),
      );
      container.append(actions);
    }
  }
  $("incident-detail").hidden = false;
}
async function refresh() {
  const [project, health, services, incidents, settings] = await Promise.all([
    api("/project"),
    api("/health"),
    api("/services"),
    api("/incidents"),
    api("/settings"),
  ]);
  $("project-name").textContent = project.inventory.name;
  readOnly = Boolean(project.read_only);
  $("project-info").textContent =
    `${project.inventory.languages.join(" · ") || "Project metadata"} · ${project.inventory.frameworks.join(" · ") || "No framework inferred"}`;
  $("scope").textContent =
    `Repository: ${project.root} · Compose project: ${project.compose_project} · Declared services: ${project.services.join(", ")}`;
  $("reasoning").textContent = settings.provider_configured
    ? `Background investigations: ${settings.model}. Telemetry polling continues while the terminal is alive.`
    : settings.model === "mock/evidence"
      ? "Mock reasoning configured. Telemetry is real; this does not evaluate a live model."
      : "Deterministic evidence analysis. No live LLM configured; supply PULSE_LLM_MODEL and provider credentials to use one.";
  $("session-state").textContent =
    `Gateway: ${health.docker} · Last completed poll: ${health.last_poll ? new Date(health.last_poll * 1000).toLocaleString() : "no completed observation"}`;
  $("coverage").textContent =
    `${services.length} enrolled services discovered. ${project.prometheus_configured ? "Prometheus uses the supported demo metric schema; inspect metric availability." : "Prometheus is not configured: application latency/error-rate detection is unavailable."}`;
  $("setup").textContent = services.length
    ? "Services below were observed through the selected repository’s scoped gateway."
    : project.read_only
      ? "No scoped Compose containers observed. Start your application yourself; missing telemetry does not prove health."
      : `No opted-in services observed. Review ${project.override_file}, then apply it with your Compose file before expecting runtime coverage.`;
  if (project.read_only) {
    $("scope").textContent +=
      " · Read-only project demo: recovery is disabled and application labels are unchanged.";
  }
  const rows = $("services");
  rows.replaceChildren();
  for (const service of services) {
    const el = text("div", "", "row");
    const fresh =
      Date.now() / 1000 - service.last_seen <=
      settings.runtime.telemetry_max_age_seconds;
    el.append(
      text("h3", service.name),
      text(
        "p",
        fresh
          ? `Observed state: ${service.snapshot.status} · Docker health: ${service.snapshot.health}`
          : "State unavailable: last Docker observation is stale",
        "badge",
      ),
    );
    const metrics = service.metrics;
    el.append(
      text(
        "p",
        metrics && metrics.available
          ? `CPU ${Number(metrics.cpu_percent).toFixed(1)}% · Memory ${Number(metrics.memory_percent).toFixed(1)}%`
          : "Resource metrics unavailable; no healthy value is inferred.",
      ),
    );
    const labels = service.snapshot.labels || {};
    const eligible =
      !readOnly &&
      labels["pulse.remediate"] === "true" &&
      labels["pulse.environment"] === "development";
    el.append(
      text(
        "p",
        eligible
          ? `Approved recovery permission: ${service.remediation_allowed ? "enabled" : "disabled"}. Each action still needs its own approval.`
          : readOnly
            ? "Read-only project demo: recovery is disabled."
            : "Recovery is advisory. Explicit development/recovery labels are required for Pulse to change this service.",
      ),
    );
    if (eligible)
      el.append(
        button(
          service.remediation_allowed
            ? "Disable recovery permission"
            : "Allow reviewed recovery for this service",
          () =>
            api(`/services/${service.id}/permissions`, "PATCH", {
              monitored: service.monitored,
              remediation_allowed: !service.remediation_allowed,
            }),
        ),
      );
    rows.append(el);
  }
  const items = $("incidents");
  items.replaceChildren();
  if (!incidents.length)
    items.append(
      text(
        "p",
        "No recorded incidents. This alone does not establish application health.",
      ),
    );
  for (const incident of incidents) {
    const el = text("div", "", "row");
    el.append(
      text("h3", incident.title),
      text(
        "p",
        `${incident.state} · ${new Date(incident.created_at * 1000).toLocaleString()}`,
        "badge",
      ),
      button("Open report & recovery choices", () => detail(incident.id)),
    );
    items.append(el);
  }
  if (selected) await detail(selected);
}
async function start() {
  await refresh();
  $("workspace").hidden = false;
  $("login").hidden = true;
  $("logout").hidden = false;
  clearInterval(timer);
  timer = setInterval(() => {
    if (!busy)
      refresh().catch((error) => {
        $("session-state").textContent =
          "Monitoring unavailable: Pulse’s terminal session or telemetry connection stopped. Displayed evidence is historical.";
        showError(error);
      });
  }, 5000);
}
$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/session", "POST", { token: $("token").value });
    $("token").value = "";
    $("error").hidden = true;
    await start();
  } catch (error) {
    $("token").value = "";
    showError(error);
  }
});
$("logout").addEventListener("click", async () => {
  try {
    await api("/session", "DELETE");
    clearInterval(timer);
    $("workspace").hidden = true;
    $("login").hidden = false;
    $("logout").hidden = true;
    selected = report = null;
  } catch (error) {
    showError(error);
  }
});
$("review").addEventListener("close", async () => {
  if ($("review").returnValue !== "approve" || !pending) return;
  const action = pending;
  pending = null;
  busy = true;
  try {
    await api(`/remediations/${action.id}/approve`, "POST", {
      action_digest: action.digest,
    });
    await refresh();
  } catch (error) {
    showError(error);
  } finally {
    busy = false;
  }
});
$("download").addEventListener("click", () => {
  if (!report) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(report, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `pulse-incident-${report.id}.json`;
  link.click();
  URL.revokeObjectURL(url);
});
start().catch((error) => {
  if (!error.message.startsWith("Sign in")) showError(error);
});
