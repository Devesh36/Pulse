export type Json = Record<string, unknown>;
export interface Snapshot {
  status?: string;
  health?: string;
  restart_count?: number;
  exit_code?: number;
  oom_killed?: boolean;
  image?: string;
  started_at?: string;
  finished_at?: string;
  labels?: Record<string, string>;
}
export interface Metrics {
  cpu_percent?: number;
  memory_percent?: number;
  memory_bytes?: number;
  memory_limit_bytes?: number;
  latency_ms?: number | null;
  error_rate?: number | null;
  available?: boolean;
}
export interface Service {
  id: string;
  container_id: string;
  name: string;
  monitored: boolean;
  remediation_allowed: boolean;
  snapshot: Snapshot;
  last_seen: number;
  metrics: Metrics | null;
}
export interface Finding {
  statement: string;
  classification: string;
  evidence_ids: string[];
  contradicting_evidence_ids: string[];
}
export interface Diagnosis {
  incident_id?: string;
  category?: string;
  likely_root_cause?: string;
  observed_evidence?: string[];
  recommended_remediation?: string;
  summary: string;
  affected_service: string;
  symptoms: string[];
  timeline: string[];
  root_causes: Finding[];
  confidence: string;
  uncertainty: string;
  next_steps: string[];
}
export interface Action {
  id: string;
  kind: string;
  reason: string;
  digest: string;
  status: string;
  expires_at: number;
  outcome?: Json;
}
export interface Tool {
  id: string;
  name: string;
  success: boolean;
  result: Json;
  duration_ms: number;
  at: number;
}
export interface Incident {
  id: string;
  service_id: string;
  kind: string;
  title: string;
  severity: string;
  state: string;
  created_at: number;
  updated_at: number;
  diagnosis?: Diagnosis;
  verification?: {
    outcome: string;
    result?: string;
    samples?: Json[];
    observation_seconds?: number;
    reason?: string;
    required_evidence?: string[];
    deadline_at?: number;
    sample_count?: number;
    resume_count?: number;
  };
  actions?: Action[];
  tools?: Tool[];
}
export interface PulseEvent {
  id: number;
  kind: string;
  at: number;
  incident_id?: string;
  payload: Json;
}
export interface RuntimeSettings {
  interval_seconds: number;
  cpu_threshold: number;
  memory_threshold: number;
  latency_threshold_ms: number;
  error_rate_threshold: number;
  restart_threshold: number;
  window_seconds: number;
  min_samples: number;
  cooldown_seconds: number;
  verification_seconds: number;
  recovery_grace_seconds: number;
  agent_max_iterations: number;
  agent_token_budget: number;
  agent_max_tool_calls: number;
  agent_max_seconds: number;
  agent_max_concurrent: number;
  agent_max_pending: number;
  telemetry_max_age_seconds: number;
  verification_max_gap_seconds?: number | null;
  http_min_requests: number;
  memory_recovery_threshold: number;
  latency_recovery_ms: number;
  error_recovery_rate: number;
  remediation_disabled: boolean;
}
export interface Settings {
  runtime: RuntimeSettings;
  model: string;
  provider_configured: boolean;
  api_base?: string;
  provider_note: string;
}
export interface Health {
  status: string;
  docker: string;
  llm_configured: boolean;
  last_poll?: number;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
    credentials: "same-origin",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status})`,
      response.status,
    );
  }
  return response.json();
}
export const send = <T>(path: string, body?: unknown, method = "POST") =>
  api<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
export function percent(value?: number | null) {
  return value == null ? "—" : `${value.toFixed(1)}%`;
}
export function bytes(value?: number) {
  return value == null ? "—" : `${(value / 1024 / 1024).toFixed(0)} MiB`;
}
export function time(value: number) {
  return new Date(value * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
export function date(value: number) {
  return new Date(value * 1000).toLocaleString();
}
export const active = (i: Incident) =>
  !["RESOLVED", "DISMISSED"].includes(i.state) && i.kind !== "question";

export interface OverviewSummary {
  monitored_services: number;
  healthy_services: number;
  active_incidents: number;
  awaiting_approval: number;
  resolved_last_24h: number;
}
