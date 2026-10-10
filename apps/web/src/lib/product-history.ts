// Public product history. Add a dated impact summary with every product change.
// See docs/product-history.md; dates below come from Git, expressed in UTC.
export interface ProductChange {
  date: string;
  title: string;
  impact: string;
  commit?: string;
}

export interface ProductPhase {
  id: string;
  label: string;
  title: string;
  summary: string;
  changes: ProductChange[];
}

export const productPhases: ProductPhase[] = [
  {
    id: "foundation",
    label: "Phase 1",
    title: "The incident workspace",
    summary:
      "Connect a Docker signal to an investigation, a reviewed action and a durable incident record.",
    changes: [
      {
        date: "2026-10-09",
        title: "Pulse begins",
        impact:
          "Established the Python API, Next.js workspace, Docker discovery, Prometheus monitoring, evidence tools and approval-controlled recovery, with persisted history and regression tests.",
        commit: "3b04a551cfb5d487afcf12c1cff0ac338ce8c841",
      },
    ],
  },
  {
    id: "incident-lab",
    label: "Phase 2",
    title: "Prove recovery with evidence",
    summary:
      "An authorized incident lab makes faults repeatable. Missing telemetry becomes an explicit inconclusive result.",
    changes: [
      {
        date: "2026-10-09",
        title: "Real faults, durable verification",
        impact:
          "Added scoped lab workloads and evaluations, fresh evidence across recovery windows, and verification progress that survives an API restart. Telemetry loss can be restored and rechecked without replaying remediation or duplicating incidents.",
        commit: "6dc76cfe343c9da5e72f11b27e91267b4c4a0e9e",
      },
    ],
  },
  {
    id: "first-run",
    label: "Phase 2 · First run",
    title: "Make Pulse easier to try",
    summary:
      "A guided terminal session, installation paths and a public introduction bring the local product within reach.",
    changes: [
      {
        date: "2026-10-09",
        title: "A guided REPL and landing page",
        impact:
          "Added Pulse Repl with demo choices, uv installation, a Homebrew preview formula and the Next.js landing page. Users can follow a local incident demonstration from one terminal session.",
        commit: "d00a6d14efc3064c1904fd644a649f67bb91b27c",
      },
      {
        date: "2026-10-09",
        title: "Validate installation from GitHub",
        impact:
          "Recorded installation checks against the repository and kept the preview Homebrew tap selected, making the documented download path match the available package.",
        commit: "5772e6922f0a4e11d5d994c9b5f6e9c7aebdceb4",
      },
    ],
  },
  {
    id: "public-website",
    label: "Phase 2 · Public website",
    title: "Explain the product. Keep it local.",
    summary:
      "Documentation and real screenshots explain Pulse, while Vercel serves the public website and the operational workspace stays on the user’s machine.",
    changes: [
      {
        date: "2026-10-09",
        title: "Docs and actual product screenshots",
        impact:
          "Added a Docs page covering setup, commands and the incident workflow, with screenshots from measured local demonstrations. Updated the README and product description.",
        commit: "09d61738df8e2d0cc5ef303f82065c1cbbaae9fd",
      },
      {
        date: "2026-10-10",
        title: "A landing-only Vercel build",
        impact:
          "Configured the public build to include the landing page and Docs. Dashboard and operational API routes remain part of the local product.",
        commit: "c638bdc1f8184b5146d5ff8ab3332731bcee1c2b",
      },
      {
        date: "2026-10-10",
        title: "Select the public website on import",
        impact:
          "Made standalone Vercel imports select the public website automatically, reducing the chance of importing the local dashboard build.",
        commit: "20b56caff29c29124f9cea8e57bfb409d1b950a4",
      },
      {
        date: "2026-10-10",
        title: "Bring the website work into main",
        impact:
          "Merged the completed installation, documentation and public-build work into main. This integration commit adds no separate product capability.",
        commit: "dd48fc2d5e3e91c60ff3a0246f343f8ff2c9cd94",
      },
    ],
  },
  {
    id: "ecg-identity",
    label: "Phase 2 · Visual identity",
    title: "Find the Pulse signal",
    summary:
      "The website evolved through an ECG-inspired treatment to the current black canvas and red pulse.",
    changes: [
      {
        date: "2026-10-10",
        title: "Introduce the red ECG direction",
        impact:
          "Replaced the green website treatment with red pulse accents, an ECG trace and an initial white background.",
        commit: "4772469caff41c9255ec9249c4c2f730953cd68d",
      },
      {
        date: "2026-10-10",
        title: "Integrate the ECG theme",
        impact:
          "Merged the red ECG website styling into main. This commit integrates the preceding design change.",
        commit: "0be2191b79704f9c8a924095305f1e85bbd8200f",
      },
      {
        date: "2026-10-10",
        title: "Consolidate on main",
        impact:
          "Updated installation and deployment references to main after branch consolidation, giving users one consistent source branch.",
        commit: "32880c99d2d85c9e0d3dd18f12fe6b3caf2a426c",
      },
      {
        date: "2026-10-10",
        title: "Refine the landing-page layout",
        impact:
          "Adjusted the ECG website’s layout, hierarchy and spacing to improve the presentation of the product workflow.",
        commit: "4f88b6284a52ed06bbfaee2ef42fce1422b3b88d",
      },
      {
        date: "2026-10-10",
        title: "Settle on black and red",
        impact:
          "Changed the landing page and Docs to a dark canvas with red ECG branding, retaining responsive layouts, readable text and reduced-motion support.",
        commit: "2589c843302b31b5b4991fdf52141a2b107a63ba",
      },
    ],
  },
  {
    id: "continuous-quality",
    label: "Phase 3",
    title: "Measure. Compare. Improve.",
    summary:
      "Turn retained lab evaluations into a read-only quality review, with honest evidence gaps and concrete follow-up work.",
    changes: [
      {
        date: "2026-10-10",
        title: "Continuous quality feedback",
        impact:
          "Added compatible-run comparisons, missing-evidence and latency flags, and actionable explanations in the API, local dashboard, CLI and REPL. Runs retain unique reports; the weekly lab workflow exports a review. Real Docker and Prometheus checks use mock reasoning, not live-model evaluation.",
        commit: "f2e2149440ea0d618738e3d8237bcbc067976820",
      },
      {
        date: "2026-10-10",
        title: "Publish the story of Pulse",
        impact:
          "Added this Phases timeline and navigation link, with dated explanations and source commits. Established a contribution rule to record the product impact of future changes here.",
        commit: "64c6647737d65b29b4ce8fe1854030bd290d3a40",
      },
    ],
  },
  {
    id: "repository-companion",
    label: "Phase 4",
    title: "Bring Pulse to your repository",
    summary:
      "A terminal session owns a local project dashboard, continuous Docker Compose monitoring and background incident investigations.",
    changes: [
      {
        date: "2026-10-10",
        title: "Scan, observe and choose the recovery",
        impact:
          "Added bounded repository inventory, reviewed monitoring enrollment, an installed local dashboard and project commands in the CLI/REPL. Each repository keeps its own database, credentials and reports. The gateway checks its directory and service allowlist; users explicitly approve or reject exact recovery proposals. Stopping the terminal leaves the app running. Live monitoring currently supports local Compose apps; model investigations run on detected incidents within existing budgets.",
        commit: "60a94615690cf5f1842f3036fd89513926325a80",
      },
      {
        date: "2026-10-10",
        title: "An interactive incident companion",
        impact:
          "Added grouped slash commands, command completion and detailed help, repository/service context, read-only questions, logs and incident evidence inspection. Monitoring runs while the prompt remains available, and exits with its owning terminal. Invalid commands and cancellation preserve the session; recovery retains exact human approval and retained evidence.",
        commit: "229bc590e5b7f61186748683cb0d0a2779be7b30",
      },
      {
        date: "2026-10-10",
        title: "One command to meet your project",
        impact:
          "Added /demo in the project REPL: bounded inventory, automatic private setup, read-only discovery of existing Compose services, a readiness check and a local dashboard. Demo enrollment changes no app labels or containers and rejects recovery at both API and gateway. Repeated demos reuse the session; the separate crash lab stays available through /lab demo.",
      },
    ],
  },
];
