"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock3,
  Container,
  ExternalLink,
  FileText,
  Gauge,
  KeyRound,
  LayoutDashboard,
  Loader2,
  LogOut,
  MessageSquare,
  Radio,
  RefreshCw,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  TriangleAlert,
  Workflow,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { IncidentLab } from "@/components/incident-lab";
import {
  active,
  api,
  ApiError,
  bytes,
  date,
  percent,
  send,
  time,
  type Action,
  type Health,
  type OverviewSummary,
  type Incident,
  type Metrics,
  type PulseEvent,
  type RuntimeSettings,
  type Service,
  type Settings,
  type Tool,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type View =
  | "overview"
  | "services"
  | "incidents"
  | "detail"
  | "assistant"
  | "settings"
  | "lab";
const navigation = [
  { href: "/lab", label: "Incident Lab", icon: Workflow, view: "lab" },
  {
    href: "/dashboard",
    label: "Overview",
    icon: LayoutDashboard,
    view: "overview",
  },
  { href: "/services", label: "Services", icon: Container, view: "services" },
  {
    href: "/incidents",
    label: "Incidents",
    icon: TriangleAlert,
    view: "incidents",
  },
  {
    href: "/assistant",
    label: "AI Assistant",
    icon: MessageSquare,
    view: "assistant",
  },
  { href: "/settings", label: "Settings", icon: Settings2, view: "settings" },
];
const stateLabel = (value: string) => value.toLowerCase().replaceAll("_", " ");
function Status({
  value,
  children,
}: {
  value: string;
  children?: React.ReactNode;
}) {
  const good = [
    "running",
    "healthy",
    "RESOLVED",
    "confirmed",
    "connected",
    "executed",
  ].includes(value);
  const bad = [
    "exited",
    "unhealthy",
    "FAILED",
    "failed",
    "critical",
    "unavailable",
  ].includes(value);
  return (
    <span
      className={cn(
        "status",
        good && "status-green",
        bad && "status-red",
        !good && !bad && "status-amber",
      )}
    >
      <span className="status-dot" />
      {children || stateLabel(value)}
    </span>
  );
}
function Empty({
  icon: Icon = Radio,
  title,
  text,
  children,
}: {
  icon?: typeof Radio;
  title: string;
  text: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={22} />
      </div>
      <h3>{title}</h3>
      <p>{text}</p>
      {children}
    </div>
  );
}
function Panel({
  title,
  aside,
  children,
  className,
}: {
  title: string;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("panel", className)}>
      <div className="panel-heading">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
function ErrorBox({ error }: { error: Error | null }) {
  return error ? (
    <div className="error-box" role="alert">
      <TriangleAlert size={16} />
      {error.message}
    </div>
  ) : null;
}
function useCommand() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      path,
      body,
      method,
    }: {
      path: string;
      body?: unknown;
      method?: string;
    }) => send(path, body, method),
    onSuccess: () => client.invalidateQueries(),
  });
}

export function Dashboard({
  view,
  incidentId,
}: {
  view: View;
  incidentId?: string;
}) {
  const client = useQueryClient();
  const services = useQuery({
    queryKey: ["services"],
    queryFn: () => api<Service[]>("/services"),
    refetchInterval: 30000,
  });
  const authorized =
    !!services.data &&
    !(services.error instanceof ApiError && services.error.status === 401);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    refetchInterval: 30000,
  });
  const incidents = useQuery({
    queryKey: ["incidents"],
    queryFn: () => api<Incident[]>("/incidents"),
    enabled: authorized,
    refetchInterval: 30000,
  });
  const overview = useQuery({
    queryKey: ["overview"],
    queryFn: () => api<OverviewSummary>("/overview"),
    enabled: authorized,
    refetchInterval: 30000,
  });
  const activity = useQuery({
    queryKey: ["activity"],
    queryFn: () => api<PulseEvent[]>("/activity"),
    enabled: authorized,
  });
  const [stream, setStream] = useState("connecting");
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (!authorized) return;
    const cursor = sessionStorage.getItem("pulse-event-cursor") || "0";
    const source = new EventSource(`/api/v1/events?after=${cursor}`);
    source.onopen = () => setStream("connected");
    source.onerror = () => setStream("reconnecting");
    source.addEventListener("sync", () => client.invalidateQueries());
    source.addEventListener("pulse", (event) => {
      const message = event as MessageEvent;
      if (message.lastEventId)
        sessionStorage.setItem("pulse-event-cursor", message.lastEventId);
      client.invalidateQueries();
    });
    return () => source.close();
  }, [authorized, client]);
  const title =
    view === "detail"
      ? "Investigation"
      : navigation.find((n) => n.view === view)?.label || "Overview";
  const rows = services.data || [];
  const incidentRows = incidents.data || [];
  const issueCount =
    overview.data?.active_incidents ?? incidentRows.filter(active).length;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link href="/dashboard" className="brand">
          <div className="brand-mark">
            <Activity size={24} strokeWidth={2.4} />
          </div>
          <span>
            pulse<span className="brand-period">.</span>
          </span>
          <span className="version">v0.1</span>
        </Link>
        <div className="workspace">
          <div className="workspace-avatar">L</div>
          <div>
            <strong>Local workspace</strong>
            <span>Development environment</span>
          </div>
          <ChevronDown size={14} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {navigation.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "nav-item",
                (view === n.view ||
                  (view === "detail" && n.view === "incidents")) &&
                  "selected",
              )}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.view === "incidents" && issueCount > 0 && (
                <b className="nav-count">{issueCount}</b>
              )}
              {n.view === "assistant" && (
                <Sparkles size={12} className="nav-spark" />
              )}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="agent-card">
            <div>
              <span className="live-dot" />
              <strong>Pulse investigator</strong>
            </div>
            <p>
              {health.data?.llm_configured
                ? "Model-assisted investigation enabled"
                : "Evidence mode · no model configured"}
            </p>
            <Link href="/settings">
              Manage agent <ArrowRight size={13} />
            </Link>
          </div>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="docs-link"
          >
            <FileText size={15} />
            API documentation
            <ExternalLink size={12} />
          </a>
          <div className="operator">
            <div className="operator-avatar">D</div>
            <div>
              <strong>Developer</strong>
              <span>Local administrator</span>
            </div>
            {authorized && (
              <button
                aria-label="Sign out"
                onClick={async () => {
                  await send("/session", undefined, "DELETE");
                  client.clear();
                  window.location.reload();
                }}
              >
                <LogOut size={16} />
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />
            <span>{title}</span>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <Circle size={7} fill="currentColor" />
              Local
            </span>
            <span className="divider" />
            <Status value={authorized ? stream : "offline"}>
              {authorized
                ? stream === "connected"
                  ? "Live updates"
                  : "Reconnecting"
                : "Not connected"}
            </Status>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Refresh data"
              onClick={() => client.invalidateQueries()}
            >
              <RefreshCw size={15} />
            </Button>
          </div>
        </header>
        <main className="content">
          {!authorized ? (
            services.isPending ? (
              <div className="loading">
                <Loader2 className="spin" size={22} />
                Connecting to Pulse…
              </div>
            ) : (
              <Login error={services.error} />
            )
          ) : (
            <>
              <div className="page-title">
                <div>
                  <div className="eyebrow">YOUR INFRASTRUCTURE, UNDERSTOOD</div>
                  <h1>
                    {title}
                    {view === "overview" && <span className="heading-dot" />}
                  </h1>
                  <p>
                    {
                      {
                        lab: "Real failures, cited evidence, deliberate recovery.",
                        overview:
                          "A live view of your services. An investigator for every incident.",
                        services:
                          "Discover, inspect, and control monitoring for your Docker containers.",
                        incidents:
                          "From the first signal to verified recovery. Every step, recorded.",
                        detail:
                          "Operational evidence, diagnosis, and human-controlled recovery.",
                        assistant:
                          "Ask an operational question. Get answers grounded in your infrastructure.",
                        settings:
                          "Define how Pulse monitors, investigates, and requests permission.",
                      }[view]
                    }
                  </p>
                </div>
                {view === "overview" && (
                  <div className="title-actions">
                    <span className="muted small">
                      <Clock3 size={13} />
                      Last poll{" "}
                      {health.data?.last_poll
                        ? time(health.data.last_poll)
                        : "not available"}
                    </span>
                    <Button asChild>
                      <Link href="/services">
                        <Container size={15} />
                        Manage services
                      </Link>
                    </Button>
                  </div>
                )}
              </div>
              {health.data?.docker !== "connected" && (
                <div className="connection-banner">
                  <Radio size={17} />
                  <div>
                    <strong>Waiting for the Docker adapter</strong>
                    <span>
                      Telemetry is unavailable. Start the Compose stack and
                      label your containers <code>pulse.monitor=true</code>.
                    </span>
                  </div>
                  <Status value="unavailable">Disconnected</Status>
                </div>
              )}
              <ErrorBox error={incidents.error} />
              {view === "overview" && (
                <Overview
                  services={rows}
                  incidents={incidentRows}
                  activity={activity.data || []}
                  summary={overview.data}
                />
              )}
              {view === "services" && (
                <Services
                  services={rows}
                  search={search}
                  setSearch={setSearch}
                />
              )}
              {view === "incidents" && (
                <Incidents
                  incidents={incidentRows}
                  services={rows}
                  search={search}
                  setSearch={setSearch}
                />
              )}
              {view === "detail" && incidentId && (
                <IncidentDetail id={incidentId} services={rows} />
              )}
              {view === "lab" && (
                <IncidentLab services={rows} incidents={incidentRows} />
              )}
              {view === "assistant" && <Assistant services={rows} />}
              {view === "settings" && <SettingsPage services={rows} />}
            </>
          )}
          <footer className="footer">
            <span>
              <Activity size={13} />
              Pulse · autonomous investigation, deliberate action
            </span>
            <span>Built for your local environment</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function Login({ error }: { error: Error | null }) {
  const [token, setToken] = useState("");
  const client = useQueryClient();
  const login = useMutation({
    mutationFn: () => send("/session", { token }),
    onSuccess: () => {
      setToken("");
      client.invalidateQueries();
    },
  });
  const unavailable = error instanceof ApiError && error.status !== 401;
  return (
    <div className="login-area">
      <div className="login-art">
        <div className="login-orbit">
          <Activity size={58} strokeWidth={1.5} />
        </div>
        <span className="eyebrow">MEET YOUR LOCAL AI SRE</span>
        <h1>
          Less firefighting.
          <br />
          More understanding.
        </h1>
        <p>
          Pulse follows the evidence from the first signal to recovery. You stay
          in control of every infrastructure change.
        </p>
        <div className="login-features">
          <span>
            <Search size={16} />
            Evidence-backed investigation
          </span>
          <span>
            <ShieldCheck size={16} />
            Explicit approval for every action
          </span>
          <span>
            <CheckCheck size={16} />
            Recovery that is actually verified
          </span>
        </div>
      </div>
      <section className="login-panel">
        <div className="empty-icon">
          <KeyRound size={23} />
        </div>
        <h2>Connect to your workspace</h2>
        <p>
          Enter <code>PULSE_ADMIN_TOKEN</code> from your local <code>.env</code>{" "}
          file. Your session uses an HttpOnly cookie.
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            login.mutate();
          }}
        >
          <label>
            Administrator token
            <input
              type="password"
              autoComplete="current-password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="Your local access token"
              minLength={16}
              required
            />
          </label>
          <Button
            variant="default"
            disabled={login.isPending || token.length < 16}
          >
            {login.isPending ? (
              <Loader2 size={16} className="spin" />
            ) : (
              <ArrowRight size={16} />
            )}
            Connect workspace
          </Button>
        </form>
        <ErrorBox error={login.error} />
        {unavailable && <ErrorBox error={error} />}
        <div className="setup-hint">
          <Terminal size={15} />
          <code>
            uv run python scripts/setup-env.py
            <br />
            docker compose up --build -d
          </code>
        </div>
      </section>
    </div>
  );
}

function Overview({
  services,
  incidents,
  activity,
  summary,
}: {
  services: Service[];
  incidents: Incident[];
  activity: PulseEvent[];
  summary?: OverviewSummary;
}) {
  const monitored = services.filter((s) => s.monitored);
  const healthy =
    summary?.healthy_services ??
    monitored.filter(
      (s) =>
        s.snapshot.status === "running" &&
        ["healthy", "none"].includes(s.snapshot.health || "none") &&
        Date.now() / 1000 - s.last_seen < 120,
    ).length;
  const unresolved = incidents.filter(active);
  const resolved = incidents.filter(
    (i) => i.state === "RESOLVED" && Date.now() / 1000 - i.updated_at < 86400,
  ).length;
  const stats = [
    {
      label: "Monitored services",
      value: summary?.monitored_services ?? monitored.length,
      icon: Container,
      foot: `${services.length} containers discovered`,
      tone: "",
    },
    {
      label: "Healthy services",
      value: summary?.healthy_services ?? healthy,
      icon: CheckCheck,
      foot: monitored.length
        ? `${Math.round((healthy / monitored.length) * 100)}% of monitored services`
        : "Waiting for connected services",
      tone: "green",
    },
    {
      label: "Active incidents",
      value: summary?.active_incidents ?? unresolved.length,
      icon: TriangleAlert,
      foot:
        (summary?.awaiting_approval ??
          unresolved.filter((i) => i.state === "AWAITING_APPROVAL").length) +
        " awaiting your approval",
      tone: (summary?.active_incidents ?? unresolved.length) ? "amber" : "",
    },
    {
      label: "Resolved incidents",
      value: summary?.resolved_last_24h ?? resolved,
      icon: ShieldCheck,
      foot: "Verified recovery · last 24 hours",
      tone: "green",
    },
  ];
  return (
    <>
      <div className="stats-grid">
        {stats.map((stat) => (
          <div className={cn("stat-card", stat.tone)} key={stat.label}>
            <div className="stat-label">
              {stat.label}
              <stat.icon size={17} />
            </div>
            <div className="stat-value">
              {stat.value.toString().padStart(2, "0")}
              <span className="stat-mini">
                <span />
                <span />
                <span />
                <span />
                <span />
              </span>
            </div>
            <div className="stat-foot">
              <span className={cn("tiny-dot", stat.tone)} />
              {stat.foot}
            </div>
          </div>
        ))}
      </div>
      <div className="overview-grid">
        <Panel
          title="Resource utilization"
          aside={
            <div className="chart-legend">
              <span>
                <i className="legend-cpu" />
                CPU
              </span>
              <span>
                <i className="legend-memory" />
                Memory
              </span>
              <b>Last 60 samples</b>
            </div>
          }
        >
          <ResourceChart services={monitored} />
        </Panel>
        <Panel
          title="System health"
          aside={<Gauge size={16} className="muted" />}
        >
          <div className="health-summary">
            <div
              className="health-ring"
              style={
                {
                  "--health": `${monitored.length ? (healthy / monitored.length) * 100 : 0}%`,
                } as React.CSSProperties
              }
            >
              <div>
                <strong>
                  {monitored.length
                    ? Math.round((healthy / monitored.length) * 100)
                    : "—"}
                  <small>{monitored.length ? "%" : ""}</small>
                </strong>
                <span>healthy</span>
              </div>
            </div>
            <p>
              {monitored.length
                ? healthy === monitored.length
                  ? "All monitored services operational"
                  : `${monitored.length - healthy} services need attention`
                : "Ready to monitor your first service"}
            </p>
          </div>
          <div className="health-counts">
            <span>
              <i className="tiny-dot green" />
              Healthy<b>{healthy}</b>
            </span>
            <span>
              <i className="tiny-dot amber" />
              Needs attention<b>{monitored.length - healthy}</b>
            </span>
            <span>
              <i className="tiny-dot" />
              Not monitored<b>{services.length - monitored.length}</b>
            </span>
          </div>
        </Panel>
      </div>
      <div className="overview-grid lower">
        <Panel
          title="Active incidents"
          aside={
            <Link href="/incidents" className="text-link">
              View all <ArrowRight size={13} />
            </Link>
          }
        >
          {unresolved.length ? (
            <div className="incident-list">
              {unresolved.slice(0, 5).map((i) => (
                <Link
                  href={`/incidents/${i.id}`}
                  className="incident-row"
                  key={i.id}
                >
                  <div
                    className={cn(
                      "incident-icon",
                      i.severity === "critical" && "critical",
                    )}
                  >
                    <TriangleAlert size={18} />
                  </div>
                  <div className="grow">
                    <h3>{i.title}</h3>
                    <p>
                      <code>{i.id.slice(0, 8)}</code>
                      <span>·</span>
                      {date(i.created_at)}
                    </p>
                  </div>
                  <Status value={i.state} />
                  <ChevronRight size={16} className="muted" />
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              icon={ShieldCheck}
              title="No active incidents"
              text="When a service crosses a threshold, Pulse will investigate and record the evidence here."
            />
          )}
        </Panel>
        <Panel
          title="Agent activity"
          aside={
            <span className="quiet-label">
              <span className="live-dot" />
              Event stream
            </span>
          }
        >
          {activity.length ? (
            <div className="activity-list">
              {activity.slice(0, 6).map((event) => (
                <div className="activity-row" key={event.id}>
                  <div className="activity-icon">
                    {event.kind.startsWith("tool") ? (
                      <Terminal size={14} />
                    ) : event.kind.includes("verification") ? (
                      <Check size={14} />
                    ) : (
                      <Bot size={14} />
                    )}
                  </div>
                  <div>
                    <strong>
                      {event.kind.replaceAll(".", " · ").replaceAll("_", " ")}
                    </strong>
                    <p>
                      {String(
                        event.payload.tool ||
                          event.payload.title ||
                          event.payload.to ||
                          event.payload.outcome ||
                          "Recorded in incident history",
                      )}
                    </p>
                  </div>
                  <time>{time(event.at)}</time>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              icon={Bot}
              title="Your investigator is ready"
              text="Real tool executions and investigation updates will appear as Pulse works."
            />
          )}
        </Panel>
      </div>
      <Panel
        title="Services"
        aside={
          <Link href="/services" className="text-link">
            Manage services <ArrowRight size={13} />
          </Link>
        }
      >
        {services.length ? (
          <ServiceTable services={services.slice(0, 6)} />
        ) : (
          <Empty
            icon={Container}
            title="Connect your first container"
            text="Add pulse.monitor=true to a Docker container, or start the included faulty-app demo. Discovery runs automatically."
          >
            <code className="command-line">
              docker compose --profile demo up -d faulty-app
            </code>
          </Empty>
        )}
      </Panel>
      <div className="assistant-callout">
        <div className="assistant-callout-icon">
          <Sparkles size={23} />
        </div>
        <div>
          <h3>Get to the “why” faster.</h3>
          <p>
            Ask Pulse about a service. It inspects health, metrics, and logs
            before answering.
          </p>
        </div>
        <Button asChild variant="secondary">
          <Link href="/assistant">
            Ask Pulse <ArrowRight size={14} />
          </Link>
        </Button>
      </div>
    </>
  );
}

function ResourceChart({ services }: { services: Service[] }) {
  const results = useQueries({
    queries: services.map((s) => ({
      queryKey: ["metrics", s.id],
      queryFn: () =>
        api<{ at: number; data: Metrics }[]>(
          `/services/${s.id}/metrics?limit=60`,
        ),
    })),
  });
  const points = new Map<
    number,
    { at: number; cpu: number; memory: number; count: number }
  >();
  results.forEach((result) =>
    result.data?.forEach((sample) => {
      if (!sample.data.available) return;
      const at = Math.floor(sample.at / 10) * 10;
      const row = points.get(at) || { at, cpu: 0, memory: 0, count: 0 };
      row.cpu += sample.data.cpu_percent || 0;
      row.memory += sample.data.memory_percent || 0;
      row.count++;
      points.set(at, row);
    }),
  );
  const data = [...points.values()]
    .sort((a, b) => a.at - b.at)
    .map((p) => ({
      ...p,
      cpu: p.cpu / p.count,
      memory: p.memory / p.count,
      label: time(p.at),
    }));
  if (!data.length)
    return (
      <div className="chart-empty">
        <div className="chart-grid" />
        <div>
          <Activity size={28} />
          <h3>Waiting for telemetry</h3>
          <p>Live CPU and memory measurements will appear here.</p>
        </div>
        <div className="chart-axis">
          <span>0%</span>
          <span>Time →</span>
        </div>
      </div>
    );
  return (
    <div className="resource-chart">
      <div className="chart-current">
        <span>
          Avg. CPU <strong>{percent(data.at(-1)?.cpu)}</strong>
        </span>
        <span>
          Avg. memory <strong>{percent(data.at(-1)?.memory)}</strong>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={205}>
        <AreaChart
          data={data}
          margin={{ top: 15, right: 24, bottom: 0, left: -18 }}
        >
          <CartesianGrid
            stroke="#252a32"
            strokeDasharray="3 5"
            vertical={false}
          />
          <XAxis
            dataKey="label"
            stroke="#707887"
            tickLine={false}
            axisLine={false}
            fontSize={10}
            minTickGap={60}
          />
          <YAxis
            stroke="#707887"
            tickLine={false}
            axisLine={false}
            fontSize={10}
            tickFormatter={(v) => `${v}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#1b1f27",
              border: "1px solid #343b46",
              borderRadius: 8,
              color: "#e8eaee",
              fontSize: 12,
            }}
            formatter={(value) => percent(Number(value))}
          />
          <Area
            dataKey="cpu"
            name="CPU"
            stroke="#93a4ff"
            fill="#93a4ff"
            fillOpacity={0.06}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Area
            dataKey="memory"
            name="Memory"
            stroke="#5ed6b2"
            fill="#5ed6b2"
            fillOpacity={0.04}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="chart-note">
        Mean across monitored containers · CPU: 100% per core · Memory: % of
        container limit
      </div>
    </div>
  );
}

function ServiceTable({
  services,
  onSelect,
}: {
  services: Service[];
  onSelect?: (s: Service) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Service</th>
            <th>Status</th>
            <th>CPU usage</th>
            <th>Memory</th>
            <th>Restarts</th>
            <th>Monitoring</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {services.map((service) => (
            <tr key={service.id}>
              <td>
                <div className="service-name">
                  <div className="container-icon">
                    <Container size={16} />
                  </div>
                  <div>
                    {onSelect ? (
                      <button
                        onClick={() => onSelect(service)}
                        className="name-button"
                      >
                        {service.name}
                      </button>
                    ) : (
                      <Link href="/services" className="name-button">
                        {service.name}
                      </Link>
                    )}
                    <code>{service.container_id.slice(0, 12)}</code>
                  </div>
                </div>
              </td>
              <td>
                <Status value={service.snapshot.status || "unknown"} />
              </td>
              <td>
                <div className="metric-cell">
                  <span>{percent(service.metrics?.cpu_percent)}</span>
                  <div className="metric-bar">
                    <i
                      style={{
                        width: `${Math.min(service.metrics?.cpu_percent || 0, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              </td>
              <td>
                <span>{bytes(service.metrics?.memory_bytes)}</span>
                <span className="cell-muted">
                  {percent(service.metrics?.memory_percent)}
                </span>
              </td>
              <td>
                <span className="mono">
                  {service.snapshot.restart_count ?? "—"}
                </span>
              </td>
              <td>
                <span
                  className={cn(
                    "monitoring-label",
                    service.monitored && "enabled",
                  )}
                >
                  <span className="tiny-dot" />
                  {service.monitored ? "Enabled" : "Disabled"}
                </span>
              </td>
              <td>
                {onSelect ? (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Inspect ${service.name}`}
                    onClick={() => onSelect(service)}
                  >
                    <ChevronRight size={16} />
                  </Button>
                ) : (
                  <Link href="/services" aria-label="View services">
                    <ChevronRight size={16} />
                  </Link>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Services({
  services,
  search,
  setSearch,
}: {
  services: Service[];
  search: string;
  setSearch: (s: string) => void;
}) {
  const [selectedId, setSelected] = useState<string>();
  const selected = services.find((s) => s.id === selectedId);
  const filtered = services.filter((s) =>
    s.name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="toolbar">
        <div className="search-box">
          <Search size={16} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search services…"
            aria-label="Search services"
          />
          <kbd>/</kbd>
        </div>
        <span className="muted small">
          {services.length} discovered ·{" "}
          {services.filter((s) => s.monitored).length} monitored
        </span>
      </div>
      <Panel
        title="Docker containers"
        aside={
          <span className="quiet-label">
            Opt in with <code>pulse.monitor=true</code>
          </span>
        }
      >
        {filtered.length ? (
          <ServiceTable
            services={filtered}
            onSelect={(s) => setSelected(s.id)}
          />
        ) : (
          <Empty
            icon={Container}
            title={search ? "No matching services" : "No containers discovered"}
            text={
              search
                ? "Try a different service name."
                : "Start the Docker adapter and add pulse.monitor=true to containers you want Pulse to discover."
            }
          />
        )}
      </Panel>
      {selected && (
        <ServiceInspector
          service={selected}
          close={() => setSelected(undefined)}
        />
      )}
    </>
  );
}

function ServiceInspector({
  service,
  close,
}: {
  service: Service;
  close: () => void;
}) {
  const command = useCommand();
  const logs = useQuery({
    queryKey: ["logs", service.id],
    queryFn: () => api<{ lines: string[] }>(`/services/${service.id}/logs`),
    enabled: service.monitored,
  });
  return (
    <div className="inspector-overlay" onClick={close}>
      <aside className="inspector" onClick={(e) => e.stopPropagation()}>
        <div className="inspector-header">
          <div className="container-icon">
            <Container size={20} />
          </div>
          <div className="grow">
            <h2>{service.name}</h2>
            <code>{service.container_id.slice(0, 12)}</code>
          </div>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Close inspector"
            onClick={close}
          >
            <X size={18} />
          </Button>
        </div>
        <div className="inspector-body">
          <div className="detail-grid">
            <div>
              <span>Status</span>
              <Status value={service.snapshot.status || "unknown"} />
            </div>
            <div>
              <span>Health check</span>
              <strong>
                {service.snapshot.health === "none"
                  ? "Not configured"
                  : service.snapshot.health || "Unknown"}
              </strong>
            </div>
            <div>
              <span>CPU</span>
              <strong>{percent(service.metrics?.cpu_percent)}</strong>
            </div>
            <div>
              <span>Memory</span>
              <strong>{bytes(service.metrics?.memory_bytes)}</strong>
            </div>
            <div>
              <span>Restart count</span>
              <strong>{service.snapshot.restart_count ?? "—"}</strong>
            </div>
            <div>
              <span>Exit code</span>
              <strong>{service.snapshot.exit_code ?? "—"}</strong>
            </div>
          </div>
          <div className="meta-field">
            <span>Image</span>
            <code>{service.snapshot.image}</code>
          </div>
          <div className="meta-field">
            <span>Last seen</span>
            <strong>{date(service.last_seen)}</strong>
          </div>
          <h3 className="section-label">Access permissions</h3>
          <div className="toggle-row">
            <div>
              <strong>Monitor this container</strong>
              <p>Collect health, metrics, and incident evidence.</p>
            </div>
            <input
              type="checkbox"
              className="switch"
              checked={service.monitored}
              disabled={command.isPending}
              aria-label="Monitor this container"
              onChange={(e) =>
                command.mutate({
                  path: `/services/${service.id}/permissions`,
                  method: "PATCH",
                  body: {
                    monitored: e.target.checked,
                    remediation_allowed: e.target.checked
                      ? service.remediation_allowed
                      : false,
                  },
                })
              }
            />
          </div>
          <div className="toggle-row">
            <div>
              <strong>Allow remediation proposals</strong>
              <p>
                Mutations still require your explicit approval and gateway
                labels.
              </p>
            </div>
            <input
              type="checkbox"
              className="switch"
              checked={service.remediation_allowed}
              disabled={!service.monitored || command.isPending}
              aria-label="Allow remediation"
              onChange={(e) =>
                command.mutate({
                  path: `/services/${service.id}/permissions`,
                  method: "PATCH",
                  body: {
                    monitored: service.monitored,
                    remediation_allowed: e.target.checked,
                  },
                })
              }
            />
          </div>
          <ErrorBox error={command.error} />
          <h3 className="section-label">
            Recent container logs
            <Button
              variant="ghost"
              size="icon"
              aria-label="Refresh logs"
              onClick={() => logs.refetch()}
            >
              <RefreshCw size={13} />
            </Button>
          </h3>
          <ErrorBox error={logs.error} />
          <div className="log-view">
            {logs.isPending && service.monitored
              ? "Retrieving Docker logs…"
              : logs.data?.lines.length
                ? logs.data.lines.map((line, i) => (
                    <div key={i}>
                      <span>{String(i + 1).padStart(2, "0")}</span>
                      {line}
                    </div>
                  ))
                : "No log entries available."}
          </div>
          <p className="muted small">
            Logs are untrusted operational evidence. Common secret patterns are
            redacted.
          </p>
        </div>
      </aside>
    </div>
  );
}

function Incidents({
  incidents,
  services,
  search,
  setSearch,
}: {
  incidents: Incident[];
  services: Service[];
  search: string;
  setSearch: (s: string) => void;
}) {
  const [filter, setFilter] = useState("all");
  const rows = incidents.filter(
    (i) =>
      i.kind !== "question" &&
      i.title.toLowerCase().includes(search.toLowerCase()) &&
      (filter === "all" ||
        (filter === "active" && active(i)) ||
        (filter === "resolved" && i.state === "RESOLVED")),
  );
  return (
    <>
      <div className="toolbar">
        <div className="tabs">
          {["all", "active", "resolved"].map((f) => (
            <button
              className={filter === f ? "active" : ""}
              key={f}
              onClick={() => setFilter(f)}
            >
              {f === "all" ? "All incidents" : f[0].toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
        <div className="search-box">
          <Search size={16} />
          <input
            placeholder="Search incidents…"
            aria-label="Search incidents"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <Panel
        title="Incident history"
        aside={<span className="quiet-label">{rows.length} incidents</span>}
      >
        {rows.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Severity</th>
                  <th>Service</th>
                  <th>Lifecycle</th>
                  <th>Detected</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.id}>
                    <td>
                      <Link
                        href={`/incidents/${i.id}`}
                        className="incident-title"
                      >
                        <span>{i.title}</span>
                        <code>
                          {i.id.slice(0, 8)} · {i.kind}
                        </code>
                      </Link>
                    </td>
                    <td>
                      <Status value={i.severity} />
                    </td>
                    <td>
                      {services.find((s) => s.id === i.service_id)?.name ||
                        i.service_id.slice(0, 8)}
                    </td>
                    <td>
                      <Status value={i.state} />
                    </td>
                    <td className="muted small">{date(i.created_at)}</td>
                    <td>
                      <Link
                        href={`/incidents/${i.id}`}
                        aria-label="Open incident"
                      >
                        <ArrowRight size={15} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            icon={ShieldCheck}
            title="No incidents in this view"
            text="Pulse creates deduplicated incidents from actual container health and rolling telemetry thresholds."
          />
        )}
      </Panel>
    </>
  );
}

function IncidentDetail({ id, services }: { id: string; services: Service[] }) {
  const query = useQuery({
    queryKey: ["incident", id],
    queryFn: () => api<Incident>(`/incidents/${id}`),
  });
  const timeline = useQuery({
    queryKey: ["timeline", id],
    queryFn: () => api<PulseEvent[]>(`/incidents/${id}/timeline`),
  });
  const command = useCommand();
  const incident = query.data;
  const service = services.find((s) => s.id === incident?.service_id);
  if (!incident)
    return (
      <>
        <ErrorBox error={query.error} />
        <div className="loading">
          <Loader2 className="spin" />
          Loading investigation…
        </div>
      </>
    );
  const stages = [
    "DETECTED",
    "INVESTIGATING",
    "DIAGNOSED",
    "AWAITING_APPROVAL",
    "REMEDIATING",
    "VERIFYING",
    "RESOLVED",
  ];
  const stage = stages.indexOf(incident.state);
  return (
    <>
      <Link href="/incidents" className="back-link">
        <ArrowLeft size={14} />
        Back to incidents
      </Link>
      <div className="incident-heading">
        <div>
          <span className="eyebrow">
            INCIDENT {id.slice(0, 8).toUpperCase()}
          </span>
          <h2>{incident.title}</h2>
          <div>
            <Status value={incident.severity} />
            <span className="muted small">
              Detected {date(incident.created_at)}
            </span>
          </div>
        </div>
        <div className="title-actions">
          {["FAILED", "DIAGNOSED", "AWAITING_APPROVAL", "DETECTED"].includes(
            incident.state,
          ) && (
            <Button
              disabled={command.isPending}
              onClick={() =>
                command.mutate({ path: `/incidents/${id}/investigate` })
              }
            >
              <RefreshCw size={14} />
              Investigate
            </Button>
          )}
          {["FAILED", "DIAGNOSED", "AWAITING_APPROVAL", "DETECTED"].includes(
            incident.state,
          ) && (
            <Button
              variant="ghost"
              disabled={command.isPending}
              onClick={() =>
                command.mutate({
                  path: `/incidents/${id}/dismiss`,
                  body: { reason: "Dismissed by local operator after review" },
                })
              }
            >
              Dismiss
            </Button>
          )}
          <Status value={incident.state} />
        </div>
      </div>
      <ErrorBox error={command.error} />
      <div className="lifecycle">
        {stages.map((s, index) => (
          <div
            key={s}
            className={cn(
              index < stage && "complete",
              index === stage && "current",
            )}
          >
            <span>{index < stage ? <Check size={12} /> : index + 1}</span>
            {stateLabel(s)}
          </div>
        ))}
      </div>
      <div className="investigation-grid">
        <div className="investigation-main">
          <Panel
            title="Diagnosis"
            aside={
              incident.diagnosis ? (
                <span className="quiet-label">
                  {incident.diagnosis.confidence} confidence · qualitative
                </span>
              ) : (
                <span className="quiet-label">
                  <Bot size={14} />
                  Evidence collection
                </span>
              )
            }
          >
            {incident.diagnosis ? (
              <div className="diagnosis-body">
                <p className="diagnosis-summary">
                  {incident.diagnosis.summary}
                </p>
                {incident.diagnosis.root_causes.map((f, idx) => (
                  <div className="finding" key={idx}>
                    <div
                      className={cn(
                        "finding-icon",
                        f.classification === "observation" && "observation",
                      )}
                    >
                      {f.classification === "observation" ? (
                        <Check size={14} />
                      ) : (
                        <Search size={14} />
                      )}
                    </div>
                    <div>
                      <span className="finding-type">
                        {stateLabel(f.classification)}
                      </span>
                      <p>{f.statement}</p>
                      <div className="evidence-links">
                        {f.evidence_ids.map((eid) => (
                          <a href={`#evidence-${eid}`} key={eid}>
                            <Terminal size={11} />
                            Evidence {eid.slice(0, 8)}
                          </a>
                        ))}
                        {f.contradicting_evidence_ids.map((eid) => (
                          <a href={`#evidence-${eid}`} key={eid}>
                            Contradiction {eid.slice(0, 8)}
                          </a>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}
                <div className="uncertainty">
                  <TriangleAlert size={16} />
                  <p>{incident.diagnosis.uncertainty}</p>
                </div>
                <h3 className="section-label">Recommended next steps</h3>
                <ul className="next-steps">
                  {incident.diagnosis.next_steps.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <Empty
                icon={Workflow}
                title={
                  incident.state === "FAILED"
                    ? "Investigation could not complete"
                    : "Investigation in progress"
                }
                text="Pulse records each tool result below. This view updates as server events arrive."
              />
            )}
          </Panel>
          <Panel
            title="Investigation evidence"
            aside={
              <span className="quiet-label">
                {incident.tools?.length || 0} tool executions
              </span>
            }
          >
            <div className="tool-list">
              {incident.tools?.length ? (
                incident.tools.map((tool) => (
                  <Evidence key={tool.id} tool={tool} />
                ))
              ) : (
                <div className="padded muted">
                  No tool executions recorded yet.
                </div>
              )}
            </div>
          </Panel>
          {!!incident.actions?.length && (
            <Panel
              title="Remediation proposal"
              aside={
                <span className="quiet-label">
                  <ShieldCheck size={14} />
                  Human approval required
                </span>
              }
            >
              <div className="action-list">
                {incident.actions.map((action) => (
                  <ActionCard
                    action={action}
                    key={action.id}
                    enabled={!!service?.remediation_allowed}
                    awaiting={incident.state === "AWAITING_APPROVAL"}
                  />
                ))}
              </div>
            </Panel>
          )}
          {incident.verification && (
            <Panel
              title="Recovery verification"
              aside={
                <Status
                  value={
                    incident.verification.result ||
                    incident.verification.outcome
                  }
                />
              }
            >
              <div className="padded">
                <p>
                  {incident.verification.reason ||
                    "Recovery conditions were not confirmed. Review the samples before investigating again."}
                </p>
                {incident.verification.observation_seconds != null && (
                  <p className="muted small">
                    {incident.verification.sample_count ??
                      incident.verification.samples?.length}{" "}
                    observations over{" "}
                    {incident.verification.observation_seconds.toFixed(1)}{" "}
                    seconds
                  </p>
                )}
                {incident.verification.required_evidence && (
                  <p className="muted small">
                    Required evidence:{" "}
                    {incident.verification.required_evidence.join(", ")}
                  </p>
                )}
                {incident.verification.deadline_at && (
                  <p className="muted small">
                    Observation deadline:{" "}
                    {date(incident.verification.deadline_at)}
                  </p>
                )}
                {incident.state === "FAILED" &&
                  incident.verification.result === "INCONCLUSIVE" && (
                    <Button
                      disabled={command.isPending}
                      onClick={() =>
                        command.mutate({
                          path: `/incidents/${id}/verification/recheck`,
                        })
                      }
                    >
                      Recheck recovery without replaying the action
                    </Button>
                  )}
                <details className="raw-details">
                  <summary>Verification evidence</summary>
                  <pre>{JSON.stringify(incident.verification, null, 2)}</pre>
                </details>
              </div>
            </Panel>
          )}
        </div>
        <div className="investigation-aside">
          <Panel title="Incident context">
            <div className="context-list">
              <div>
                <span>Affected service</span>
                <strong>{service?.name || incident.service_id}</strong>
              </div>
              <div>
                <span>Incident type</span>
                <strong>{incident.kind}</strong>
              </div>
              <div>
                <span>Current state</span>
                <Status value={incident.state} />
              </div>
              <div>
                <span>Remediation access</span>
                <strong>
                  {service?.remediation_allowed
                    ? "Allowed · approval required"
                    : "Disabled for this container"}
                </strong>
              </div>
            </div>
          </Panel>
          <Panel title="Timeline">
            <div className="timeline">
              {timeline.data?.map((event) => (
                <div key={event.id} className="timeline-event">
                  <i />
                  <time>{time(event.at)}</time>
                  <strong>{event.kind.replaceAll(".", " · ")}</strong>
                  <p>
                    {String(
                      event.payload.to ||
                        event.payload.tool ||
                        event.payload.kind ||
                        "",
                    )}
                  </p>
                </div>
              ))}
              {!timeline.data?.length && (
                <p className="muted">No events yet.</p>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}

function Evidence({ tool }: { tool: Tool }) {
  return (
    <details className="evidence" id={`evidence-${tool.id}`}>
      <summary>
        <span className={cn("tool-icon", !tool.success && "failed")}>
          <Terminal size={15} />
        </span>
        <div className="grow">
          <strong>{tool.name}</strong>
          <code>
            {tool.id.slice(0, 8)} · {time(tool.at)}
          </code>
        </div>
        <span className="muted small">{tool.duration_ms.toFixed(0)} ms</span>
        {tool.success ? (
          <Check size={15} className="green-text" />
        ) : (
          <X size={15} className="red-text" />
        )}
        <ChevronDown size={13} />
      </summary>
      <pre>{JSON.stringify(tool.result, null, 2)}</pre>
    </details>
  );
}

function ActionCard({
  action,
  enabled,
  awaiting,
}: {
  action: Action;
  enabled: boolean;
  awaiting: boolean;
}) {
  const command = useCommand();
  const pending = action.status === "proposed";
  const expired = action.expires_at < Date.now() / 1000;
  const mutation = [
    "start",
    "restart",
    "reset_memory",
    "reset_errors",
    "reset_latency",
  ].includes(action.kind);
  return (
    <div className="action-card">
      <div className="action-header">
        <div className="action-icon">
          <RefreshCw size={18} />
        </div>
        <div className="grow">
          <strong>{stateLabel(action.kind)} container</strong>
          <code>{action.id.slice(0, 8)} · immutable action</code>
        </div>
        <Status value={expired && pending ? "expired" : action.status} />
      </div>
      <p>{action.reason}</p>
      {pending && mutation && (
        <>
          <div className="action-policy">
            <ShieldCheck size={14} />
            {!enabled
              ? "Enable remediation permission for this service in Services first."
              : expired
                ? "This proposal expired. Investigate again to generate a new proposal."
                : `Review required · expires ${time(action.expires_at)}`}
          </div>
          <div className="action-buttons">
            <Button
              variant="default"
              disabled={!enabled || expired || !awaiting || command.isPending}
              onClick={() =>
                command.mutate({
                  path: `/remediations/${action.id}/approve`,
                  body: { action_digest: action.digest },
                })
              }
            >
              {command.isPending ? (
                <Loader2 className="spin" size={14} />
              ) : (
                <Check size={14} />
              )}
              Approve & execute
            </Button>
            <Button
              disabled={command.isPending}
              onClick={() =>
                command.mutate({ path: `/remediations/${action.id}/reject` })
              }
            >
              Reject
            </Button>
          </div>
        </>
      )}
      <ErrorBox error={command.error} />
      {action.outcome && (
        <details className="raw-details">
          <summary>Execution outcome</summary>
          <pre>{JSON.stringify(action.outcome, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}

function Assistant({ services }: { services: Service[] }) {
  const [sid, setSid] = useState("");
  const [message, setMessage] = useState("");
  const [investigation, setInvestigation] = useState<string>();
  const available = services.filter((s) => s.monitored);
  const selected = sid || available[0]?.id || "";
  const ask = useMutation({
    mutationFn: () =>
      send<{ incident_id: string }>("/chat", { message, service_id: selected }),
    onSuccess: (data) => setInvestigation(data.incident_id),
  });
  const answer = useQuery({
    queryKey: ["incident", investigation],
    queryFn: () => api<Incident>(`/incidents/${investigation}`),
    enabled: !!investigation,
    refetchInterval: (query) =>
      ["DIAGNOSED", "FAILED"].includes(query.state.data?.state || "")
        ? false
        : 3000,
  });
  const prompts = [
    "Why is this container restarting?",
    "What do the recent logs tell us?",
    "Is this service experiencing memory pressure?",
  ];
  return (
    <div className="assistant-layout">
      <section className="conversation panel">
        <div className="panel-heading">
          <h2>
            <Sparkles size={17} />
            Pulse assistant
          </h2>
          <span className="quiet-label">Read-only tools · real evidence</span>
        </div>
        <div className="conversation-body">
          {!investigation ? (
            <div className="assistant-intro">
              <div className="assistant-avatar">
                <Activity size={32} />
              </div>
              <h2>What needs a closer look?</h2>
              <p>
                Select a monitored service and ask a question.
                <br />
                Pulse retrieves operational evidence before forming an answer.
              </p>
              <div className="prompt-cards">
                {prompts.map((p) => (
                  <button key={p} onClick={() => setMessage(p)}>
                    <Search size={15} />
                    <span>{p}</span>
                    <ArrowRight size={14} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="chat-question">
                <div className="operator-avatar">D</div>
                <p>{message}</p>
              </div>
              <div className="chat-answer">
                <div className="assistant-avatar small-avatar">
                  <Activity size={18} />
                </div>
                <div>
                  {answer.data?.diagnosis ? (
                    <>
                      <p className="diagnosis-summary">
                        {answer.data.diagnosis.summary}
                      </p>
                      {answer.data.diagnosis.root_causes.map((f, idx) => (
                        <div className="chat-finding" key={idx}>
                          <span className="finding-type">
                            {stateLabel(f.classification)}
                          </span>
                          <p>{f.statement}</p>
                        </div>
                      ))}
                      <p className="muted small">
                        {answer.data.diagnosis.uncertainty}
                      </p>
                      <Button asChild>
                        <Link href={`/incidents/${investigation}`}>
                          Open evidence workspace
                          <ArrowRight size={14} />
                        </Link>
                      </Button>
                    </>
                  ) : answer.data?.state === "FAILED" ? (
                    <p>
                      Investigation failed. Review the recorded tool evidence.
                    </p>
                  ) : (
                    <div className="loading inline">
                      <Loader2 size={17} className="spin" />
                      Investigating{" "}
                      {available.find((s) => s.id === selected)?.name}…
                      {answer.data?.tools?.length ? (
                        <span>{answer.data.tools.length} tools executed</span>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
        <div className="composer">
          <ErrorBox error={ask.error || answer.error} />
          <div className="composer-service">
            <Container size={14} />
            <select
              value={selected}
              onChange={(e) => setSid(e.target.value)}
              aria-label="Affected service"
            >
              {available.length ? (
                available.map((s) => (
                  <option value={s.id} key={s.id}>
                    {s.name}
                  </option>
                ))
              ) : (
                <option value="">No monitored services</option>
              )}
            </select>
            <span>
              <ShieldCheck size={12} />
              Scoped investigation
            </span>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask.mutate();
            }}
          >
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Ask about this service’s health, logs, or resource usage…"
              aria-label="Operational question"
              maxLength={2000}
              required
            />
            <Button
              variant="default"
              size="icon"
              aria-label="Investigate question"
              disabled={
                !selected ||
                !message.trim() ||
                ask.isPending ||
                (!!investigation &&
                  !["DIAGNOSED", "FAILED"].includes(answer.data?.state || ""))
              }
            >
              <Send size={17} />
            </Button>
          </form>
          <p>
            Answers cite tool evidence. Infrastructure changes always require
            separate approval.
          </p>
        </div>
      </section>
      <Panel title="How Pulse investigates" className="assistant-explainer">
        <div className="explain-steps">
          {[
            {
              icon: Container,
              title: "Inspect the service",
              text: "Current status, health checks, and exit metadata.",
            },
            {
              icon: Activity,
              title: "Follow the evidence",
              text: "Real resource metrics, recent logs, and observed restarts.",
            },
            {
              icon: Search,
              title: "Explain the findings",
              text: "Evidence-supported hypotheses with explicit uncertainty.",
            },
          ].map((item, idx) => (
            <div key={idx}>
              <item.icon size={18} />
              <strong>{item.title}</strong>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
        <div className="assistant-note">
          <ShieldCheck size={18} />
          <p>
            The assistant has no shell access and cannot execute infrastructure
            mutations.
          </p>
        </div>
      </Panel>
    </div>
  );
}

function SettingsPage({ services }: { services: Service[] }) {
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<Settings>("/settings"),
  });
  const [form, setForm] = useState<RuntimeSettings>();
  const command = useCommand();
  const values = form || query.data?.runtime;
  const fields: {
    key: keyof RuntimeSettings;
    title: string;
    description: string;
    min: number;
    max: number;
    step?: number;
  }[] = [
    {
      key: "interval_seconds",
      title: "Monitoring interval",
      description: "Seconds between real telemetry polls",
      min: 2,
      max: 300,
    },
    {
      key: "window_seconds",
      title: "Rolling window",
      description: "Seconds of telemetry used for detection",
      min: 2,
      max: 3600,
    },
    {
      key: "min_samples",
      title: "Consecutive samples",
      description: "Required threshold violations before an alert",
      min: 1,
      max: 100,
    },
    {
      key: "cooldown_seconds",
      title: "Alert cooldown",
      description: "Seconds before a resolved alert can recur",
      min: 0,
      max: 86400,
    },
    {
      key: "cpu_threshold",
      title: "CPU threshold",
      description: "Percent · 100% represents one fully used core",
      min: 1,
      max: 10000,
    },
    {
      key: "memory_threshold",
      title: "Memory threshold",
      description: "Percent of the container memory limit",
      min: 1,
      max: 100,
    },
    {
      key: "latency_threshold_ms",
      title: "API latency threshold",
      description: "Milliseconds · Prometheus p95",
      min: 1,
      max: 60000,
    },
    {
      key: "error_rate_threshold",
      title: "HTTP error rate",
      description: "Fraction of requests returning 5xx",
      min: 0.01,
      max: 1,
      step: 0.01,
    },
    {
      key: "restart_threshold",
      title: "Restart threshold",
      description: "Restart count increase within the rolling window",
      min: 1,
      max: 50,
    },
    {
      key: "verification_seconds",
      title: "Recovery observation",
      description: "Seconds of sustained verification after an action",
      min: 2,
      max: 600,
    },
    {
      key: "recovery_grace_seconds",
      title: "Startup grace period",
      description: "Seconds allowed for startup before sustained recovery",
      min: 0,
      max: 120,
    },
    {
      key: "agent_max_iterations",
      title: "Investigation iterations",
      description: "Maximum collect/reason cycles",
      min: 1,
      max: 15,
    },
    {
      key: "agent_token_budget",
      title: "Model token budget",
      description: "Combined input/output budget per investigation",
      min: 512,
      max: 64000,
    },
  ];
  if (!values)
    return (
      <>
        <ErrorBox error={query.error} />
        <div className="loading">
          <Loader2 className="spin" />
          Loading configuration…
        </div>
      </>
    );
  return (
    <div className="settings-layout">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          command.mutate({ path: "/settings", body: values, method: "PATCH" });
        }}
      >
        <Panel
          title="Monitoring & detection"
          aside={<Settings2 size={16} className="muted" />}
        >
          <div className="settings-fields">
            {fields.map((field) => (
              <label key={field.key}>
                <div>
                  <strong>{field.title}</strong>
                  <p>{field.description}</p>
                </div>
                <input
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step || 1}
                  required
                  value={values[field.key] as number}
                  onChange={(e) =>
                    setForm({ ...values, [field.key]: Number(e.target.value) })
                  }
                />
              </label>
            ))}
          </div>
          <div className="settings-save">
            <ErrorBox error={command.error} />
            {command.isSuccess && (
              <span className="green-text small">
                <Check size={14} />
                Settings saved
              </span>
            )}
            <Button variant="default" disabled={command.isPending}>
              {command.isPending ? (
                <Loader2 size={14} className="spin" />
              ) : (
                <Check size={14} />
              )}
              Save configuration
            </Button>
          </div>
        </Panel>
      </form>
      <div className="settings-aside">
        <Panel title="Remediation safety">
          <div className="padded">
            <div className="toggle-row">
              <div>
                <strong>Emergency disable</strong>
                <p>Block all new container mutations immediately.</p>
              </div>
              <input
                className="switch danger-switch"
                type="checkbox"
                checked={values.remediation_disabled}
                aria-label="Emergency disable remediation"
                disabled={command.isPending}
                onChange={(e) => {
                  const next = {
                    ...values,
                    remediation_disabled: e.target.checked,
                  };
                  setForm(next);
                  command.mutate({
                    path: "/settings",
                    method: "PATCH",
                    body: { remediation_disabled: next.remediation_disabled },
                  });
                }}
              />
            </div>
            <div className="safety-note">
              <ShieldCheck size={17} />
              <p>
                Every mutation needs an immutable proposal, resource permission,
                explicit approval, and verification.
              </p>
            </div>
            <p className="muted small">
              {services.filter((s) => s.remediation_allowed).length} services
              have remediation permission.
            </p>
            <Button asChild>
              <Link href="/services">
                Manage container permissions
                <ArrowRight size={13} />
              </Link>
            </Button>
          </div>
        </Panel>
        <Panel title="Model provider">
          <div className="padded">
            <div className="provider-status">
              <Bot size={19} />
              <strong>{query.data?.model || "Evidence mode"}</strong>
            </div>
            <Status
              value={
                query.data?.provider_configured ? "connected" : "unconfigured"
              }
            >
              {query.data?.provider_configured
                ? "Provider configured"
                : "No model configured"}
            </Status>
            <p className="muted provider-note">{query.data?.provider_note}</p>
            <div className="code-sample">
              <code>
                PULSE_LLM_MODEL=openai/gpt-4.1-mini
                <br />
                PULSE_LLM_API_KEY=your-key
              </code>
            </div>
            <p className="small muted">
              Also supports Anthropic and OpenAI-compatible local endpoints
              through LiteLLM. Restart the API after changing provider
              configuration.
            </p>
          </div>
        </Panel>
        <Panel title="Access & audit">
          <div className="padded">
            <p className="muted small">
              Local administrator sessions expire after 12 hours. Privileged
              requests, approvals, and mutations are audited in PostgreSQL.
            </p>
            <AuditRecords />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function AuditRecords() {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: ["audit"],
    queryFn: () =>
      api<{ id: number; operation: string; at: number; resource_id: string }[]>(
        "/audit",
      ),
    enabled: open,
  });
  return (
    <>
      <Button onClick={() => setOpen(!open)}>
        <FileText size={14} />
        {open ? "Hide" : "View"} recent audit records
      </Button>
      {open && (
        <>
          <ErrorBox error={query.error} />
          <div className="audit-list">
            {query.data?.length ? (
              query.data.slice(0, 12).map((row) => (
                <div key={row.id}>
                  <strong>{row.operation}</strong>
                  <span>{date(row.at)}</span>
                  <code>{row.resource_id.slice(0, 12)}</code>
                </div>
              ))
            ) : (
              <p className="muted small">No audit records yet.</p>
            )}
          </div>
        </>
      )}
    </>
  );
}
