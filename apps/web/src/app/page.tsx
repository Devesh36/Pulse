import type { Metadata } from "next";
import { Landing } from "@/components/landing";
export const metadata: Metadata = {
  title: "Pulse — Evidence before action",
  description:
    "Investigate local Docker incidents, review evidence, approve recovery, and verify what actually happened. Start with the Pulse interactive demo.",
};
export default function Page() {
  return <Landing />;
}
