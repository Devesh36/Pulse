import Image from "next/image";
import styles from "./landing.module.css";

const screenshots = [
  {
    file: "overview",
    title: "Your local workspace",
    alt: "Pulse overview showing discovered Docker services, incident counts and measured resource charts",
    description:
      "Monitor discovered services, resource measurements and incident activity in one overview.",
  },
  {
    file: "investigation",
    title: "An investigation you can inspect",
    alt: "Pulse incident investigation with its recorded lifecycle and evidence-backed diagnosis",
    description:
      "A retained lab incident with its timeline and diagnosis. The lab was stopped when this history was captured.",
  },
  {
    file: "verification",
    title: "The evidence behind recovery",
    alt: "Pulse recovery verification panel displaying the recorded verdict and supporting measurements",
    description:
      "Inspect the recorded verification outcome and supporting measurements after an approved action.",
  },
];

export function ProductScreenshots({ all = false }: { all?: boolean }) {
  return (
    <div className={styles.screenshots}>
      {screenshots.slice(0, all ? 3 : 2).map((shot) => (
        <figure key={shot.file}>
          <a
            href={`/screenshots/${shot.file}.png`}
            target="_blank"
            rel="noreferrer"
            aria-label={`Open full-size screenshot: ${shot.title}`}
          >
            <Image
              src={`/screenshots/${shot.file}.png`}
              width={1440}
              height={1000}
              sizes={
                all
                  ? "(max-width: 650px) 100vw, 860px"
                  : "(max-width: 650px) 100vw, 560px"
              }
              alt={shot.alt}
            />
          </a>
          <figcaption>
            <strong>{shot.title}</strong>
            <p>{shot.description}</p>
            <span>
              Open screenshot to view full size{" "}
              <span aria-hidden="true">↗</span>
            </span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}
