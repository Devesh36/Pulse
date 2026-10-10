import type { Metadata } from "next";
import { ProductDocs } from "@/components/product-docs";

export const metadata: Metadata = {
  title: "Pulse docs — Run it, understand it, inspect the evidence",
  description:
    "Install Pulse, run the guided Docker demo, open the dashboard and understand evidence-driven investigation, human approvals and recovery verification.",
};

export default function DocsPage() {
  return <ProductDocs />;
}
