"use client";

import Link from "next/link";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import {
  api,
  date,
  percent,
  send,
  type Incident,
  type Service,
} from "@/lib/api";

interface LabStatus {
  enabled: boolean;
  project: string;
  docker: string;
  scenarios: { id: string; service: string; description: string }[];
}
interface Evaluation {
  id: string;
  at: number;
  scenario: string;
  report: {
    status: string;
    mode: string;
    detection_latency_seconds?: number;
    final_state?: string;
    verification?: { result: string };
  };
}
interface QualityReview {
  status: string;
  summary: { failed: number; regressed: number; needs_evidence: number };
  scenarios: {
    scenario: string;
    status: string;
    comparison: string;
    comparison_reason: string;
    current: {
      id: string;
      at: number;
      mode: string;
      verdict: string | null;
      incident_id: string | null;
    } | null;
    baseline: { id: string; at: number } | null;
    issues: { code: string; explanation: string; follow_up: string }[];
    latency_changes: {
      metric: string;
      baseline_seconds: number;
      current_seconds: number;
      direction: string;
    }[];
  }[];
  limitations: string[];
}

export function IncidentLab({
  services,
  incidents,
}: {
  services: Service[];
  incidents: Incident[];
}) {
  const client = useQueryClient();
  const status = useQuery({
    queryKey: ["lab-status"],
    queryFn: () => api<LabStatus>("/lab/status"),
    refetchInterval: 5000,
  });
  const history = useQuery({
    queryKey: ["lab-evaluations"],
    queryFn: () => api<Evaluation[]>("/lab/evaluations"),
    refetchInterval: 10000,
  });
  const quality = useQuery({
    queryKey: ["lab-quality"],
    queryFn: () => api<QualityReview>("/lab/quality"),
    refetchInterval: 10000,
  });
  const command = useMutation({
    mutationFn: (path: string) => send(path, {}),
    onSuccess: () => client.invalidateQueries(),
  });
  const labServices = services.filter(
    (s) => s.snapshot.labels?.["pulse.lab"] === "pulse-lab",
  );
  const ids = new Set(labServices.map((s) => s.id));
  const labIncidents = incidents.filter((i) => ids.has(i.service_id));
  const current = labIncidents.filter(
    (i) => !["RESOLVED", "DISMISSED"].includes(i.state),
  );
  const details = useQueries({
    queries: current.map((i) => ({
      queryKey: ["incident", i.id],
      queryFn: () => api<Incident>(`/incidents/${i.id}`),
      refetchInterval: 5000,
    })),
  });
  const enabled = status.data?.enabled && status.data.docker === "connected";
  return (
    <div className="lab-grid">
      <section className="panel">
        <div className="panel-heading">
          <h2>Disposable incident laboratory</h2>
          <span className="muted">{status.data?.project || "Connecting"}</span>
        </div>
        <p>
          Inject a bounded failure, inspect observed evidence, and review a
          proposed action before approving recovery.
        </p>
        {!status.data?.enabled && (
          <p className="muted">
            Start the isolated incident lab to enable its controls. Existing
            service monitoring continues independently.
          </p>
        )}
        {(status.error || history.error || command.error) && (
          <p role="alert">
            {(status.error || history.error || command.error)?.message}
          </p>
        )}
        <div className="title-actions">
          <Button
            variant="ghost"
            disabled={
              !enabled ||
              command.isPending ||
              current.some((i) =>
                [
                  "DETECTED",
                  "INVESTIGATING",
                  "DIAGNOSED",
                  "AWAITING_APPROVAL",
                  "REMEDIATING",
                  "VERIFYING",
                ].includes(i.state),
              )
            }
            onClick={() => command.mutate("/lab/reset")}
          >
            Reset lab workloads
          </Button>
        </div>
        {status.data?.scenarios.map((scenario) => (
          <div className="lab-row" key={scenario.id}>
            <div>
              <h3>{scenario.id.replaceAll("-", " ")}</h3>
              <p className="muted">{scenario.description}</p>
              <span className="small">{scenario.service}</span>
            </div>
            <Button
              disabled={!enabled || command.isPending || current.length > 0}
              onClick={() => command.mutate(`/lab/faults/${scenario.id}`)}
            >
              Inject fault
            </Button>
          </div>
        ))}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Observed service metrics</h2>
          <span className="muted">Actual Docker and Prometheus samples</span>
        </div>
        {labServices.map((s) => (
          <div className="lab-row" key={s.id}>
            <div>
              <strong>{s.name}</strong>
              <p>
                {s.snapshot.status} · health {s.snapshot.health}
              </p>
              <p className="small muted">Last observed {date(s.last_seen)}</p>
            </div>
            <div>
              <p>
                Memory{" "}
                {s.metrics?.available
                  ? percent(s.metrics.memory_percent)
                  : "unavailable"}
              </p>
              <p>
                CPU{" "}
                {s.metrics?.available
                  ? percent(s.metrics.cpu_percent)
                  : "unavailable"}
              </p>
              <p>
                p95{" "}
                {s.metrics?.latency_ms == null
                  ? "unavailable"
                  : `${s.metrics.latency_ms.toFixed(0)} ms`}
              </p>
              <p>
                HTTP errors{" "}
                {s.metrics?.error_rate == null
                  ? "unavailable"
                  : percent(s.metrics.error_rate * 100)}
              </p>
            </div>
          </div>
        ))}
        {!labServices.length && (
          <p className="muted">No freshly discovered lab services.</p>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Investigations and approvals</h2>
          <span className="muted">
            Evidence and hypotheses are recorded separately
          </span>
        </div>
        {current.map((i, index) => {
          const detail = details[index]?.data;
          return (
            <div className="lab-row" key={i.id}>
              <div>
                <h3>{i.title}</h3>
                <p>{i.state.replaceAll("_", " ")}</p>
                {detail?.diagnosis && (
                  <>
                    <p>{detail.diagnosis.summary}</p>
                    <p className="muted">
                      Hypothesis:{" "}
                      {detail.diagnosis.likely_root_cause || "Unresolved"}
                    </p>
                  </>
                )}
                <p className="small">
                  {detail?.tools?.length ?? "—"} recorded tool executions ·
                  verification{" "}
                  {detail?.verification?.result ||
                    detail?.verification?.outcome ||
                    "pending"}
                </p>
              </div>
              <Button asChild>
                <Link href={`/incidents/${i.id}`}>
                  Review evidence and approval
                </Link>
              </Button>
            </div>
          );
        })}
        {!current.length && (
          <p className="muted">No active lab investigation.</p>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Continuous improvement</h2>
          <span className="muted">Read-only evaluation review</span>
        </div>
        {quality.isPending && (
          <p className="muted">Loading quality evidence…</p>
        )}
        {quality.error && (
          <p role="alert">
            Quality review unavailable: {quality.error.message}
          </p>
        )}
        {quality.data && (
          <>
            <p>
              <strong>{quality.data.status.replaceAll("_", " ")}</strong> ·{" "}
              {quality.data.summary.failed} failed ·{" "}
              {quality.data.summary.regressed} regression flags ·{" "}
              {quality.data.summary.needs_evidence} need evidence or a
              compatible baseline
            </p>
            {quality.data.scenarios.map((row) => (
              <div className="lab-row" key={row.scenario}>
                <div>
                  <strong>{row.scenario}</strong>
                  <p>
                    {row.status.replaceAll("_", " ")} ·{" "}
                    {row.comparison.replaceAll("_", " ")}
                  </p>
                  <p className="muted">{row.comparison_reason}</p>
                  {row.current && (
                    <p className="muted">
                      Latest {date(row.current.at)} · {row.current.mode} ·{" "}
                      {row.current.verdict || "verdict unavailable"}
                    </p>
                  )}
                  {row.baseline && (
                    <p className="muted">Baseline {date(row.baseline.at)}</p>
                  )}
                  {row.current?.incident_id && (
                    <Link href={`/incidents/${row.current.incident_id}`}>
                      Review incident evidence
                    </Link>
                  )}
                  {row.issues.map((issue) => (
                    <p key={issue.code}>
                      {issue.explanation}{" "}
                      <span className="muted">{issue.follow_up}</span>
                    </p>
                  ))}
                  {row.latency_changes.map((change) => (
                    <p className="muted" key={change.metric}>
                      {change.metric.replaceAll("_", " ")}:{" "}
                      {change.baseline_seconds.toFixed(2)} s →{" "}
                      {change.current_seconds.toFixed(2)} s (
                      {change.direction.toLowerCase()})
                    </p>
                  ))}
                </div>
              </div>
            ))}
            {quality.data.limitations.map((limitation) => (
              <p className="muted" key={limitation}>
                {limitation}
              </p>
            ))}
          </>
        )}
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Evaluation history</h2>
          <span className="muted">Persisted runner results</span>
        </div>
        {history.data?.map((r) => (
          <div className="lab-row" key={r.id}>
            <div>
              <strong>{r.scenario}</strong>
              <p className="muted">
                {date(r.at)} · {r.report.mode}
              </p>
            </div>
            <div>
              <p>
                {r.report.status} ·{" "}
                {r.report.verification?.result || "unverified"}
              </p>
              <p>
                Detection{" "}
                {r.report.detection_latency_seconds == null
                  ? "unmeasured"
                  : `${r.report.detection_latency_seconds.toFixed(2)} s`}
              </p>
            </div>
          </div>
        ))}
        {!history.data?.length && (
          <p className="muted">
            No evaluation measurements have been recorded.
          </p>
        )}
      </section>
    </div>
  );
}
