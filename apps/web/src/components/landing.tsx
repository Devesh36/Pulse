"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Copy,
  Database,
  FileSearch,
  GitBranch,
  Play,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import styles from "./landing.module.css";

const repository = "https://github.com/Devesh36/Pulse/tree/work";
const installs = {
  uv: "uv tool install --from git+https://github.com/Devesh36/Pulse.git@work pulse-sre\npulse repl",
  brew: "curl -fsSL https://raw.githubusercontent.com/Devesh36/Pulse/work/scripts/install-homebrew.sh | bash\npulse repl",
};
const steps = [
  {
    title: "Detect",
    state: "DETECTED",
    text: "A container exited. Pulse records its state and opens one incident.",
    evidence: "Docker state · exited\nExit code · 42\nIncident · opened once",
  },
  {
    title: "Investigate",
    state: "AWAITING APPROVAL",
    text: "Read-only tools gather the crash log and lifecycle events. The diagnosis links back to evidence.",
    evidence:
      "inspect_container · exit code 42\nget_container_logs · application_crash\nget_recent_service_events · die",
  },
  {
    title: "Approve",
    state: "VERIFYING",
    text: "A person reviews the exact Start proposal. One approval permits one action; replay is rejected.",
    evidence:
      "Proposal · start demo-worker\nApproval · bound to action digest\nExecution · once, then observe",
  },
  {
    title: "Verify",
    state: "RECOVERED",
    text: "Recovery requires fresh, ordered observations across the full stability window.",
    evidence:
      "Docker state · running\nHealth probe · healthy\nEvidence coverage · complete",
  },
];

function Install() {
  const [method, setMethod] = useState<"uv" | "brew">("uv");
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(installs[method]);
      setCopied(true);
      setCopyError(false);
    } catch {
      setCopyError(true);
    }
  }
  return (
    <div className={styles.installBox}>
      <div className={styles.installTop}>
        <div className={styles.methods} aria-label="Installation method">
          <button
            aria-pressed={method === "uv"}
            onClick={() => {
              setMethod("uv");
              setCopied(false);
              setCopyError(false);
            }}
          >
            uv <span>Recommended</span>
          </button>
          <button
            aria-pressed={method === "brew"}
            onClick={() => {
              setMethod("brew");
              setCopied(false);
              setCopyError(false);
            }}
          >
            Homebrew
          </button>
        </div>
        <button
          className={styles.copy}
          onClick={copy}
          aria-label="Copy installation commands"
        >
          {copied ? <Check size={16} /> : <Copy size={16} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre tabIndex={0}>
        <code>{installs[method]}</code>
      </pre>
      <div className={styles.installNote} aria-live="polite">
        {copyError
          ? "Select the commands above to copy them manually."
          : method === "uv"
            ? "Git-based install. Python 3.12+; uv can install Python for you."
            : "Preview formula from the work branch. Requires Homebrew and Git."}
      </div>
    </div>
  );
}

function Walkthrough() {
  const [step, setStep] = useState(0);
  const [missing, setMissing] = useState(false);
  const current = steps[step];
  const inconclusive = step === 3 && missing;
  return (
    <div className={styles.walkthrough}>
      <div className={styles.windowBar}>
        <span className={styles.windowDots}>
          <i />
          <i />
          <i />
        </span>
        <span>
          <Terminal size={13} /> pulse / incident workspace
        </span>
        <span className={styles.example}>Example data</span>
      </div>
      <div className={styles.tourBody}>
        <div className={styles.tourHeader}>
          <span className={styles.tourService}>
            <span /> demo-worker
          </span>
          <span
            className={`${styles.verdict} ${inconclusive ? styles.warning : ""}`}
          >
            {inconclusive ? "INCONCLUSIVE" : current.state}
          </span>
        </div>
        <h3>
          {inconclusive
            ? "No evidence. No recovery claim."
            : step === 3
              ? "Recovery backed by observations."
              : "Container exited unexpectedly."}
        </h3>
        <p className={styles.tourText} aria-live="polite">
          {inconclusive
            ? "Required telemetry is missing. Restore reliable observations, then request a read-only recheck. The action is never replayed."
            : current.text}
        </p>
        <div className={styles.tourContent}>
          <div className={styles.stepList}>
            {steps.map((item, index) => (
              <button
                key={item.title}
                className={index === step ? styles.selectedStep : ""}
                onClick={() => setStep(index)}
                aria-current={index === step ? "step" : undefined}
              >
                <span>{index < step ? <Check size={13} /> : index + 1}</span>
                {item.title}
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
          <div className={styles.evidence}>
            <div>
              <FileSearch size={14} /> Supporting evidence
            </div>
            <pre>
              {inconclusive
                ? "Docker state · running\nRequired telemetry · unavailable\nRecovery verdict · inconclusive"
                : current.evidence}
            </pre>
            <span>
              {inconclusive
                ? "Read-only recheck available after restoration"
                : "Every conclusion points to an observation"}
            </span>
          </div>
        </div>
        <div className={styles.tourFooter}>
          <label>
            <input
              type="checkbox"
              checked={missing}
              onChange={(event) => {
                setMissing(event.target.checked);
                setStep(3);
              }}
            />{" "}
            Hide required telemetry
          </label>
          <button onClick={() => setStep((step + 1) % steps.length)}>
            {step === 3 ? "Replay walkthrough" : "Next step"}
            <ArrowRight size={14} />
          </button>
        </div>
      </div>
      <div className={styles.exampleNote}>
        Interactive illustration. Run <code>pulse repl</code> for real Docker
        and Prometheus measurements.
      </div>
    </div>
  );
}

export function Landing() {
  return (
    <main className={styles.page}>
      <div className={styles.gridGlow} aria-hidden="true" />
      <nav className={styles.nav} aria-label="Product navigation">
        <Link href="/" className={styles.brand}>
          <Activity size={27} strokeWidth={2.2} />
          pulse<span>.</span>
        </Link>
        <div className={styles.navLinks}>
          <a href="#how-it-works">How it works</a>
          <a href="#demo">Demo</a>
          <a href={repository}>
            GitHub <GitBranch size={13} />
          </a>
        </div>
        <Link href="/dashboard" className={styles.workspaceLink}>
          Open workspace <ArrowRight size={15} />
        </Link>
      </nav>
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}>
            <span /> LOCAL INFRASTRUCTURE. HUMAN CONTROL.
          </div>
          <h1>
            When things break,
            <br />
            <em>follow the evidence.</em>
          </h1>
          <p>
            Pulse investigates your Docker incidents, explains what happened,
            and helps you recover—with your approval and a verification trail.
          </p>
          <div className={styles.heroActions}>
            <a href="#get-started" className={styles.primary}>
              Start with Pulse <ArrowRight size={17} />
            </a>
            <a href="#demo" className={styles.secondary}>
              <Play size={15} /> See how it works
            </a>
          </div>
          <div className={styles.heroNotes}>
            <span>
              <CheckCircle2 size={14} /> Open source
            </span>
            <span>
              <CheckCircle2 size={14} /> Runs locally
            </span>
            <span>
              <CheckCircle2 size={14} /> No API key needed for the demo
            </span>
          </div>
        </div>
        <div className={styles.heroVisual}>
          <div className={styles.visualCaption}>
            <Activity size={14} /> FROM SIGNAL TO VERIFIED RECOVERY
          </div>
          <div className={styles.signal} aria-hidden="true">
            <svg viewBox="0 0 480 110">
              <defs>
                <linearGradient id="pulse-signal">
                  <stop stopColor="#42575d" />
                  <stop offset=".5" stopColor="#8ceccb" />
                  <stop offset="1" stopColor="#42575d" />
                </linearGradient>
              </defs>
              <path
                d="M0 64H125l12-13 11 13h17l16-45 22 76 20-50 13 19h244"
                fill="none"
                stroke="url(#pulse-signal)"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
            <span className={styles.signalDot} />
          </div>
          <div className={styles.visualStack}>
            <div>
              <span className={styles.iconSquare}>
                <TriangleAlert size={20} />
              </span>
              <span>
                <strong>Incident detected</strong>
                <small>State, metrics, logs, lifecycle events</small>
              </span>
              <span className={styles.stackTag}>Observe</span>
            </div>
            <div>
              <span className={styles.iconSquare}>
                <FileSearch size={20} />
              </span>
              <span>
                <strong>Cause explained</strong>
                <small>Read-only investigation with citations</small>
              </span>
              <span className={styles.stackTag}>Explain</span>
            </div>
            <div>
              <span className={styles.iconSquare}>
                <ShieldCheck size={20} />
              </span>
              <span>
                <strong>You approve the action</strong>
                <small>Exact resource. Expiring approval. Once.</small>
              </span>
              <span className={styles.stackTag}>Control</span>
            </div>
          </div>
          <div className={styles.visualFooter}>
            <CheckCircle2 size={16} /> Recovery is observed, never assumed.
          </div>
        </div>
      </section>
      <div className={styles.principles}>
        <span>
          <Database size={17} /> Real telemetry
        </span>
        <span>
          <FileSearch size={17} /> Traceable conclusions
        </span>
        <span>
          <ShieldCheck size={17} /> Explicit approvals
        </span>
        <span>
          <Waypoints size={17} /> Durable incident history
        </span>
      </div>
      <section className={styles.section} id="how-it-works">
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>
            A SMALLER PATH THROUGH THE INCIDENT
          </div>
          <h2>
            Less guessing.
            <br />A clear next step.
          </h2>
          <p>
            One workspace connects the signal, the explanation, the action, and
            the evidence that it worked.
          </p>
        </div>
        <div className={styles.features}>
          {[
            {
              icon: Activity,
              title: "Know what changed",
              text: "Detect stopped containers, unhealthy services, resource pressure, latency and HTTP errors from actual observations.",
            },
            {
              icon: FileSearch,
              title: "Inspect the reasoning",
              text: "See the tool results behind each diagnosis. Investigations stay within monitored resources and read-only tools.",
            },
            {
              icon: ShieldCheck,
              title: "Stay in control",
              text: "Review a proposed recovery before it runs. Approvals expire, bind to the exact action, and cannot be replayed.",
            },
          ].map(({ icon: Icon, title, text }, index) => (
            <article key={title}>
              <span className={styles.featureNumber}>0{index + 1}</span>
              <Icon size={27} />
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>
      <section className={`${styles.section} ${styles.demoSection}`} id="demo">
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>TAKE A LOOK INSIDE</div>
          <h2>From crash to clarity.</h2>
          <p>
            Step through an example. Then hide its telemetry and see why missing
            evidence changes the verdict.
          </p>
        </div>
        <Walkthrough />
      </section>
      <section className={`${styles.section} ${styles.verificationSection}`}>
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>HONEST ABOUT WHAT IT KNOWS</div>
          <h2>Silence isn’t a healthy signal.</h2>
          <p>
            Fresh, relevant evidence must span the recovery window. Missing
            samples, gaps, stale data and contradictions cannot count as
            healthy.
          </p>
        </div>
        <div className={styles.outcomes}>
          <article>
            <span className={styles.outcomeDot} />
            <h3>Recovered</h3>
            <p>Required sources confirm sustained recovery.</p>
          </article>
          <article>
            <span className={`${styles.outcomeDot} ${styles.failedDot}`} />
            <h3>Not recovered</h3>
            <p>Trustworthy observations show continuing failure.</p>
          </article>
          <article>
            <span className={`${styles.outcomeDot} ${styles.unknownDot}`} />
            <h3>Inconclusive</h3>
            <p>
              Evidence is insufficient. Restore telemetry and recheck without
              replaying the action.
            </p>
          </article>
        </div>
      </section>
      <section
        className={`${styles.section} ${styles.startSection}`}
        id="get-started"
      >
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>MEET YOUR NEXT INCIDENT PREPARED</div>
          <h2>Install. Open. Try a demo.</h2>
          <p>
            Open the REPL, type <code>demo</code>, and follow a real
            crash-and-recovery run. Docker with Compose is required for the lab;
            the dashboard opens on localhost.
          </p>
          <div className={styles.replHint}>
            <Terminal size={18} />
            <span>
              <code>pulse repl</code>
              <br />
              Then choose <strong>1 · Demo</strong>.
            </span>
          </div>
        </div>
        <Install />
      </section>
      <footer className={styles.footer}>
        <Link href="/" className={styles.brand}>
          <Activity size={23} />
          pulse<span>.</span>
        </Link>
        <p>Evidence before action.</p>
        <div>
          <a href="https://github.com/Devesh36/Pulse/blob/work/docs/getting-started.md">
            Getting started
          </a>
          <a href={repository}>
            Source code <ArrowRight size={13} />
          </a>
          <span>MIT licensed</span>
        </div>
      </footer>
    </main>
  );
}
