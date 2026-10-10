import "./globals.css";
import styles from "@/components/landing.module.css";
export { metadata } from "./layout";

export default function SiteLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={styles.publicDocument}>
      <body>{children}</body>
    </html>
  );
}
