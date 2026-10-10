import { ArrowUpRight, ChevronDown } from "lucide-react";
import { productPhases } from "@/lib/product-history";
import styles from "./landing.module.css";

function date(value: string) {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function ProductPhases() {
  return (
    <section
      className={`${styles.section} ${styles.phasesSection}`}
      id="phases"
      aria-labelledby="phases-heading"
    >
      <div className={styles.sectionHeading}>
        <div className={styles.eyebrow}>HOW PULSE CAME TO LIFE</div>
        <h2 id="phases-heading">Phases</h2>
        <p>
          From the first incident workspace to your own repository companion.
          Follow what changed, when it changed, and what each step added to
          Pulse.
        </p>
      </div>
      <ol className={styles.phaseTimeline}>
        {productPhases.map((phase) => {
          const first = phase.changes[0].date;
          const last = phase.changes[phase.changes.length - 1].date;
          return (
            <li key={phase.id} className={styles.phase}>
              <div className={styles.phaseMarker}>
                <span>{phase.label}</span>
                <p>
                  <time dateTime={first}>{date(first)}</time>
                  {last !== first && (
                    <>
                      <br />
                      to <time dateTime={last}>{date(last)}</time>
                    </>
                  )}
                </p>
              </div>
              <article aria-labelledby={`phase-${phase.id}`}>
                <h3 id={`phase-${phase.id}`}>{phase.title}</h3>
                <p className={styles.phaseSummary}>{phase.summary}</p>
                <details open={phase.id === "repository-companion"}>
                  <summary>
                    {phase.changes.length}{" "}
                    {phase.changes.length === 1 ? "change" : "changes"}
                    <span>Dates &amp; details</span>
                    <ChevronDown size={16} aria-hidden="true" />
                  </summary>
                  <ol className={styles.phaseChanges}>
                    {phase.changes.map((change) => (
                      <li key={change.title}>
                        <div className={styles.changeMeta}>
                          <time dateTime={change.date}>
                            {date(change.date)}
                          </time>
                          {change.commit ? (
                            <a
                              href={`https://github.com/Devesh36/Pulse/commit/${change.commit}`}
                              aria-label={`View commit ${change.commit.slice(0, 7)}: ${change.title}`}
                            >
                              <code>{change.commit.slice(0, 7)}</code>
                              <ArrowUpRight size={13} aria-hidden="true" />
                            </a>
                          ) : (
                            <span>This update</span>
                          )}
                        </div>
                        <h4>{change.title}</h4>
                        <p>{change.impact}</p>
                      </li>
                    ))}
                  </ol>
                </details>
              </article>
            </li>
          );
        })}
      </ol>
      <p className={styles.historyNote}>
        Dates use UTC. Entries describe shipped work and its effect on the
        product; they are not release or deployment claims.{" "}
        <a href="https://github.com/Devesh36/Pulse/commits/main">
          Browse the full commit history <ArrowUpRight size={13} />
        </a>
      </p>
    </section>
  );
}
