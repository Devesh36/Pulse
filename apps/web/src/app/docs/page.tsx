import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BookOpen,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { Install } from "@/components/landing";
import { ProductNav } from "@/components/product-nav";
import { ProductScreenshots } from "@/components/product-screenshots";
import styles from "@/components/landing.module.css";

export const metadata: Metadata = {
  title: "Pulse docs — Run it, understand it, inspect the evidence",
  description:
    "Install Pulse, run the guided Docker demo, open the dashboard and understand evidence-driven investigation, human approvals and recovery verification.",
};

const contents = [
  ["what-it-does", "What Pulse does"],
  ["first-run", "Your first run"],
  ["commands", "REPL commands"],
  ["how-it-runs", "How it runs"],
  ["verification", "Read the verdict"],
  ["screenshots", "Product screenshots"],
  ["data", "Data & troubleshooting"],
];
const commands = [
  [
    "demo / 1",
    "Run a real crash, investigation, approved Start and recovery check.",
  ],
  [
    "telemetry / 2",
    "Compare recovery and continuing failure, interrupt selected lab telemetry, restart the API and recheck after restoration.",
  ],
  ["dashboard / 3", "Open the Incident Lab at http://localhost:3100/lab."],
  ["status / 4", "Inspect fresh lab discoveries and current state."],
  [
    "reports / 5",
    "Read measured outcomes, citations, action results and explanations.",
  ],
  [
    "stop / 6",
    "Confirm and stop the lab; keep credentials, volumes, database and reports.",
  ],
  ["exit / 0", "Leave the REPL. Running lab services stay available."],
];

export default function DocsPage() {
  return (
    <main className={styles.page}>
      <ProductNav />
      <header className={`${styles.section} ${styles.docsHero}`}>
        <div className={styles.eyebrow}>
          <BookOpen size={14} /> PULSE DOCUMENTATION
        </div>
        <h1>
          From download to
          <br />
          <em>verified recovery.</em>
        </h1>
        <p>
          Run the product on your machine, understand each step, and inspect the
          evidence behind the result.
        </p>
        <span className={styles.docsBadge}>
          Local Docker · Preview 0.2 · No API key needed for demos
        </span>
      </header>
      <div className={styles.docsLayout}>
        <aside className={styles.docsSidebar}>
          <nav aria-label="Documentation contents">
            <span>IN THIS GUIDE</span>
            {contents.map(([id, label]) => (
              <a key={id} href={`#${id}`}>
                {label}
              </a>
            ))}
          </nav>
        </aside>
        <article className={styles.docsContent}>
          <section id="what-it-does">
            <div className={styles.eyebrow}>01 / THE PRODUCT</div>
            <h2>What Pulse does</h2>
            <p>
              Pulse monitors Docker containers you opt in, detects incidents
              from their actual state and metrics, and collects logs, events and
              measurements with scoped read-only tools. Its diagnosis cites that
              evidence and proposes a bounded Start or Restart action for
              review.
            </p>
            <p>
              You decide whether the action runs. Pulse then observes the
              affected service across a configured recovery window, saves the
              measurements and explains whether it recovered, is still failing
              or cannot yet be verified.
            </p>
            <div className={styles.docsCallout}>
              <ShieldCheck size={20} />
              <p>
                Monitoring and remediation permissions are separate. An approval
                expires, binds to the exact proposed action and resource, and
                can be used once. The guided demo asks for your consent before
                authorizing its scoped lab action.
              </p>
            </div>
          </section>
          <section id="first-run">
            <div className={styles.eyebrow}>02 / GET STARTED</div>
            <h2>Your first run</h2>
            <ol className={styles.runSteps}>
              <li>
                <h3>Start Docker</h3>
                <p>
                  Install and start Docker Desktop, or Docker Engine with
                  Compose v2. The demo needs a working daemon and free lab ports
                  8100, 8109 and 3100. Use one Pulse lab per Docker host.
                </p>
              </li>
              <li>
                <h3>Install and open the REPL</h3>
                <p>
                  For the uv route, install{" "}
                  <a href="https://docs.astral.sh/uv/getting-started/installation/">
                    uv
                  </a>{" "}
                  and Git. Pulse requires Python 3.12+; uv can provision it. The
                  Homebrew route needs Homebrew and Git and installs Python and
                  uv.
                </p>
                <Install />
                <p>
                  These commands install the GitHub <code>work</code> preview.
                  The Homebrew formula is a repository tap; native Homebrew
                  installation has not been validated on the cloud test host.
                </p>
              </li>
              <li>
                <h3>Run the real demo</h3>
                <pre tabIndex={0}>
                  <code>{"pulse › demo\nContinue? [y/N] y"}</code>
                </pre>
                <p>
                  The first run builds the fixed <code>pulse-lab</code> Compose
                  project and can take several minutes. The demo injects a crash
                  into its selected lab container, measures detection,
                  investigates, executes one approved Start and checks sustained
                  recovery. It uses real Docker, Prometheus and HTTP
                  observations with deterministic mock reasoning. It makes no
                  live-model calls.
                </p>
              </li>
              <li>
                <h3>Open the dashboard</h3>
                <pre tabIndex={0}>
                  <code>pulse › dashboard</code>
                </pre>
                <p>
                  Pulse opens <code>http://localhost:3100/lab</code> and prints
                  the path to its local credential file. Open that file
                  privately and sign in with <code>PULSE_ADMIN_TOKEN</code>. The
                  token itself is never printed by the REPL.
                </p>
              </li>
              <li>
                <h3>Inspect results and stop</h3>
                <pre tabIndex={0}>
                  <code>
                    {
                      "pulse › reports\npulse › stop\nContinue? [y/N] y\npulse › exit"
                    }
                  </code>
                </pre>
                <p>
                  Read the measured verdict and explanation. Stop preserves the
                  lab database, volumes and reports for your next run.
                </p>
              </li>
            </ol>
          </section>
          <section id="commands">
            <div className={styles.eyebrow}>03 / THE TERMINAL MENU</div>
            <h2>REPL commands</h2>
            <p>
              Launch with <code>pulse repl</code> or <code>Pulse Repl</code>.
              Type a command or its menu number.
            </p>
            <div
              className={styles.commandTable}
              tabIndex={0}
              role="region"
              aria-label="REPL command reference"
            >
              <table>
                <thead>
                  <tr>
                    <th scope="col">Command</th>
                    <th scope="col">What it does</th>
                  </tr>
                </thead>
                <tbody>
                  {commands.map(([command, meaning]) => (
                    <tr key={command}>
                      <th scope="row">
                        <code>{command}</code>
                      </th>
                      <td>{meaning}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              For advanced usage, run <code>pulse lab --help</code>. Run{" "}
              <code>telemetry</code> to see why missing evidence produces an
              inconclusive verdict, then how a read-only recheck behaves after
              telemetry returns.
            </p>
          </section>
          <section id="how-it-runs">
            <div className={styles.eyebrow}>04 / UNDER THE HOOD</div>
            <h2>How it runs</h2>
            <p>
              The installed CLI carries the public project assets needed for the
              lab, so you can run it from any directory without cloning a second
              checkout. It starts an isolated Compose project containing the
              API, database, private Docker gateway, Prometheus, demo services
              and dashboard.
            </p>
            <div className={styles.runtimeFlow} aria-label="Pulse architecture">
              {[
                {
                  icon: Terminal,
                  title: "REPL & Next.js",
                  text: "Start the lab, review incidents and approve actions.",
                },
                {
                  icon: Activity,
                  title: "Python API",
                  text: "Monitor, investigate, enforce policy and verify.",
                },
                {
                  icon: ShieldCheck,
                  title: "Private Docker gateway",
                  text: "Read opted-in resources and execute approved Start/Restart.",
                },
                {
                  icon: BookOpen,
                  title: "PostgreSQL & Prometheus",
                  text: "Retain incident history, audit records and measured telemetry.",
                },
              ].map(({ icon: Icon, title, text }) => (
                <div key={title}>
                  <Icon size={21} />
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              ))}
            </div>
            <p>
              The monitor opens a deduplicated incident from actual
              observations. Investigation tools gather bounded, redacted
              evidence. An optional configured model can assist the diagnosis;
              the demo uses deterministic reasoning. The API validates fresh
              permissions and an exact, expiring approval before a mutation,
              then persists verification progress and evidence across an API
              restart.
            </p>
            <p>
              For your own trusted development services, opt in with{" "}
              <code>pulse.monitor=true</code>. Start/Restart proposals also
              require the remediation labels and separate dashboard permission.
              See the{" "}
              <a href="https://github.com/Devesh36/Pulse/blob/work/README.md#opt-containers-in">
                container opt-in guide
              </a>{" "}
              before adding resources.
            </p>
            <div className={styles.docsCallout}>
              <BookOpen size={20} />
              <p>
                The landing-page walkthrough uses labeled example data. These
                documentation screenshots are recorded product captures. Run the
                REPL demo to measure behavior on your own Docker host.
              </p>
            </div>
          </section>
          <section id="verification">
            <div className={styles.eyebrow}>05 / THE RESULT</div>
            <h2>Read the verdict</h2>
            <dl className={styles.verdictList}>
              <div>
                <dt>RECOVERED</dt>
                <dd>
                  Fresh, relevant and ordered observations from all required
                  sources cover the configured stability window.
                </dd>
              </div>
              <div>
                <dt>NOT_RECOVERED</dt>
                <dd>
                  Trustworthy measurements show continuing failure. An observed
                  failure remains visible even when other telemetry is missing.
                </dd>
              </div>
              <div>
                <dt>INCONCLUSIVE</dt>
                <dd>
                  Missing, stale, unavailable, contradictory or incomplete
                  evidence prevents a reliable conclusion. Restore the required
                  telemetry and request a read-only recheck; the approved action
                  is not replayed.
                </dd>
              </div>
            </dl>
            <p>
              The API, dashboard, CLI and evaluation reports expose the outcome,
              required evidence, received observations, timestamps and reason.
              Read the{" "}
              <a href="https://github.com/Devesh36/Pulse/blob/work/docs/recovery-verification.md">
                verification policy
              </a>{" "}
              and{" "}
              <a href="https://github.com/Devesh36/Pulse/blob/work/docs/verification-telemetry-results.md">
                measured telemetry-loss results
              </a>{" "}
              for the detailed evidence.
            </p>
          </section>
          <section id="screenshots">
            <div className={styles.eyebrow}>06 / INSIDE THE WORKSPACE</div>
            <h2>Product screenshots</h2>
            <p>
              Actual overview and investigation screens captured from the
              existing local development demonstration. Measurements and
              incident history came from the backend; these images are static
              captures. Demo diagnosis is deterministic reasoning, not a
              live-LLM evaluation.
            </p>
            <ProductScreenshots all />
          </section>
          <section id="data">
            <div className={styles.eyebrow}>07 / KEEP YOUR WORK</div>
            <h2>Data & troubleshooting</h2>
            <details open>
              <summary>Where are credentials and reports?</summary>
              <p>
                Installed assets live in{" "}
                <code>$XDG_DATA_HOME/pulse/project</code> (default{" "}
                <code>~/.local/share/pulse/project</code>), or{" "}
                <code>$PULSE_HOME/project</code> when set. Lab credentials are
                in <code>examples/incident-lab/.env</code> and reports in the
                neighboring <code>reports/</code> directory. From a checkout,
                Pulse uses that checkout. PostgreSQL history lives in the lab’s
                Docker volume. Upgrades retain mutable data.
              </p>
            </details>
            <details>
              <summary>The pulse command is missing</summary>
              <p>
                Run <code>uv tool update-shell</code> and reopen your terminal.
                You can also check <code>pulse --version</code> once your tool
                directory is on PATH.
              </p>
            </details>
            <details>
              <summary>The demo cannot reach Docker or use its ports</summary>
              <p>
                Start Docker Desktop or Engine and check{" "}
                <code>docker info</code> and <code>docker compose version</code>
                . Lab ports 8100, 8109 and 3100 must be free. Pulse rejects an
                existing lab with mismatched credentials or another model;
                manage that lab from its original installation.
              </p>
            </details>
            <details>
              <summary>How do I stop or update safely?</summary>
              <p>
                Use <code>stop</code> in the REPL or <code>pulse lab stop</code>{" "}
                to retain history. <code>exit</code> leaves the lab running.
                Update a uv install with <code>uv tool upgrade pulse-sre</code>.{" "}
                <code>pulse lab down</code> deletes disposable lab volumes and
                database history, while retaining host reports. Uninstalling the
                CLI leaves user data and running containers.
              </p>
            </details>
            <details>
              <summary>How do I run only the website?</summary>
              <p>
                From a checkout, run <code>npm ci --prefix apps/web</code>, then{" "}
                <code>npm run dev --prefix apps/web</code>. The landing page and
                this guide work without the API at{" "}
                <code>http://localhost:3000</code>. The operational dashboard
                requires the backend. See the{" "}
                <a href="https://github.com/Devesh36/Pulse/blob/work/docs/getting-started.md#product-website">
                  development instructions
                </a>{" "}
                for the complete stack.
              </p>
            </details>
          </section>
          <div className={styles.docsEnd}>
            <Link href="/#get-started" className={styles.primary}>
              Start with Pulse <ArrowRight size={16} />
            </Link>
            <a href="https://github.com/Devesh36/Pulse/tree/work/docs">
              More technical docs <ArrowRight size={16} />
            </a>
          </div>
        </article>
      </div>
      <footer className={styles.footer}>
        <Link href="/" className={styles.brand}>
          <Activity size={23} />
          pulse<span>.</span>
        </Link>
        <p>Evidence before action.</p>
        <div>
          <Link href="/#about">About Pulse</Link>
          <a href="https://github.com/Devesh36/Pulse/tree/work">Source code</a>
          <span>MIT licensed</span>
        </div>
      </footer>
    </main>
  );
}
