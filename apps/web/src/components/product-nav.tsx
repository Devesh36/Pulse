import Link from "next/link";
import { Activity, ArrowRight } from "lucide-react";
import styles from "./landing.module.css";

export function ProductNav({ siteOnly = false }: { siteOnly?: boolean }) {
  return (
    <nav className={styles.nav} aria-label="Product navigation">
      <Link href="/" className={styles.brand} aria-label="Pulse home">
        <Activity size={27} strokeWidth={2.2} />
        pulse<span>.</span>
      </Link>
      <div className={styles.navLinks}>
        <Link href="/#how-it-works">How it works</Link>
        <Link href="/#demo">Demo</Link>
        <Link href="/docs">Docs</Link>
        <Link href="/#phases">Phases</Link>
        <Link href="/#about">About</Link>
      </div>
      <Link
        href={siteOnly ? "/#get-started" : "/dashboard"}
        className={styles.workspaceLink}
      >
        {siteOnly ? "Install Pulse" : "Open workspace"} <ArrowRight size={15} />
      </Link>
    </nav>
  );
}
