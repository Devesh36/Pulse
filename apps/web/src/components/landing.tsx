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
  BookOpen,
  Play,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  Waypoints,
} from "lucide-react";
import styles from "./landing.module.css";
import { ProductNav } from "./product-nav";
import { ProductScreenshots } from "./product-screenshots";

const repository = "https://github.com/Devesh36/Pulse/tree/main";
const pulseTrace =
  "M0 66H70q8-12 16 0h28l7 9 9-52 11 73 9-30h18q12-24 24 0h59q8-12 16 0h28l7 9 9-52 11 73 9-30h18q12-24 24 0H480";
const installs = {
  uv: "uv tool install --from git+https://github.com/Devesh36/Pulse.git@main pulse-sre\npulse repl",
  brew: "curl -fsSL https://raw.githubusercontent.com/Devesh36/Pulse/main/scripts/install-homebrew.sh | bash\npulse repl",
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

export function Install() {
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
            : "Preview formula from the main branch. Requires Homebrew and Git."}
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

export function Landing({ siteOnly = false }: { siteOnly?: boolean }) {
  return (
    <main className={styles.page}>
      <ProductNav siteOnly={siteOnly} />
      <section className={styles.hero}>
        <div className={styles.heroCopy}>
          <div className={styles.eyebrow}>
            <span /> INCIDENT RESPONSE. HUMAN CONTROL.
          </div>
          <h1>
            Keep a pulse
            <br />
            <em>on your stack.</em>
          </h1>
          <p>
            Catch the incident. Understand the cause. Recover with confidence.
            Pulse connects your Docker telemetry to a clear next step—always
            with your approval.
          </p>
          <div className={styles.heroActions}>
            <a href="#get-started" className={styles.primary}>
              Install Pulse <ArrowRight size={17} />
            </a>
            <a href="#demo" className={styles.secondary}>
              <Play size={15} /> Explore the demo
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
              <CheckCircle2 size={14} /> Demo without an API key
            </span>
          </div>
        </div>
        <div className={styles.heroVisual}>
          <div className={styles.visualCaption}>
            <span>
              <Activity size={17} /> THE INCIDENT LOOP
            </span>
            <span className={styles.illustrationLabel}>Illustration</span>
          </div>
          <div className={styles.signalHeading}>
            <strong>Every signal tells a story.</strong>
            <span>Docker state · Metrics · Logs</span>
          </div>
          <div className={styles.signal} aria-hidden="true">
            <svg viewBox="0 0 480 110">
              <path
                className={styles.signalBaseline}
                d={pulseTrace}
                fill="none"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path
                className={styles.signalTrace}
                d={pulseTrace}
                pathLength="1"
                fill="none"
                strokeWidth="3.5"
                strokeLinecap="round"
                strokeLinejoin="round"
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
                <small>Observe what changed in your stack.</small>
              </span>
            </div>
            <div>
              <span className={styles.iconSquare}>
                <FileSearch size={20} />
              </span>
              <span>
                <strong>Cause explained</strong>
                <small>Trace the diagnosis back to evidence.</small>
              </span>
            </div>
            <div>
              <span className={styles.iconSquare}>
                <ShieldCheck size={20} />
              </span>
              <span>
                <strong>You approve the action</strong>
                <small>One scoped action. Then verify recovery.</small>
              </span>
            </div>
          </div>
          <div className={styles.visualFooter}>
            <ShieldCheck size={16} /> Recovery is measured, never assumed.
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
      <section className={styles.section} id="product">
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>THE PRODUCT, AS IT RUNS</div>
          <h2>A look at the workspace.</h2>
          <p>
            Actual screens captured from a local Docker demonstration. These are
            recorded measurements, not a live feed. The demo diagnosis uses
            deterministic reasoning; no live LLM was evaluated.
          </p>
        </div>
        <ProductScreenshots />
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
      <section className={`${styles.section} ${styles.docsSection}`} id="docs">
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>DOCUMENTATION</div>
          <h2>Your first run, explained.</h2>
          <p>
            Learn what Pulse observes, how an approval becomes an action, and
            how to run the demo, open the dashboard and keep your results.
          </p>
          <Link href="/docs" className={styles.primary}>
            <BookOpen size={17} /> Read the docs <ArrowRight size={17} />
          </Link>
        </div>
        <div className={styles.docsLinks}>
          <Link href="/docs#first-run">
            <strong>Run your first demo</strong>
            <span>Docker, REPL commands and dashboard login</span>
            <ArrowRight size={18} />
          </Link>
          <Link href="/docs#how-it-runs">
            <strong>Understand the workflow</strong>
            <span>Discovery, investigation, approval and verification</span>
            <ArrowRight size={18} />
          </Link>
          <Link href="/docs#screenshots">
            <strong>Explore the product screens</strong>
            <span>Overview, diagnosis and recovery evidence</span>
            <ArrowRight size={18} />
          </Link>
        </div>
      </section>
      <section
        className={`${styles.section} ${styles.aboutSection}`}
        id="about"
      >
        <div className={styles.sectionHeading}>
          <div className={styles.eyebrow}>ABOUT PULSE</div>
          <h2>
            Understand the incident.
            <br />
            Own the decision.
          </h2>
        </div>
        <div className={styles.aboutCopy}>
          <p>
            Pulse is an open-source AI SRE for trusted local Docker
            environments. It brings monitoring, evidence-backed investigation
            and controlled recovery into one workspace, with a guided incident
            lab to try the complete workflow on your own machine.
          </p>
          <p>
            The Next.js dashboard sits alongside a Python API, PostgreSQL
            history and Prometheus telemetry. Only opted-in resources can be
            monitored; recovery actions require separate permission and your
            explicit, expiring approval. Every verdict stays connected to its
            evidence.
          </p>
          <a href={repository} className={styles.secondary}>
            Explore the MIT-licensed source <ArrowRight size={15} />
          </a>
        </div>
      </section>
      <footer className={styles.footer}>
        <Link href="/" className={styles.brand}>
          <Activity size={23} />
          pulse<span>.</span>
        </Link>
        <p>Evidence before action.</p>
        <div>
          <Link href="/docs">Documentation</Link>
          <a href="#about">About</a>
          <a href={repository}>
            Source code <ArrowRight size={13} />
          </a>
          <span>MIT licensed</span>
        </div>
      </footer>
    </main>
  );
}
