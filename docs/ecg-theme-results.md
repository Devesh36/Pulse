# Red ECG website theme

Validated on 2026-10-10 using Next.js 16.4.0 and Chromium. The landing page and
Docs now use a white canvas, deep red accents, faint ECG paper grids, an animated
heartbeat trace and light panels. Shared CSS variables keep the complete website
palette consistent. The public document uses a light color scheme even when the
visitor's operating system prefers dark mode.

## Validation

Commands from the repository root:

```bash
NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web
VERCEL=0 PULSE_PUBLIC_SITE=0 NEXT_TELEMETRY_DISABLED=1 npm run build --prefix apps/web
npm run typecheck --prefix apps/web
npm run format:check --prefix apps/web
PORT=3200 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-project --with playwright python /workspace/pulse-ecg-theme-check.py
git diff --check
```

All passed. The production public build contains only `/`, `/docs` and framework
error pages; the normal local build still contains the operational dashboard,
lab and API proxy. Browser checks covered both public pages at 1440, 390 and 320 pixels:

- White page/body backgrounds and red branding with a dark OS preference.
- Minimum contrast of sampled text and button labels: **5.58:1**.
- Animated ECG trace with normal motion; a complete static trace with reduced motion.
- Installation tabs and clipboard, navigation, seven REPL command rows,
  troubleshooting disclosures, image loading and the interactive verification example.
- No horizontal overflow, JavaScript errors or backend API requests.

Screenshots and measured colors are retained under
`/workspace/pulse-ui-results/ecg-theme/`, including `landing-1440.png`,
`landing-390.png`, `docs-1440.png`, `docs-390.png` and `measurements.json`.
These are browser captures of the local production build. The public Vercel URL
was not inspected during this theme change.

Changed application files: `apps/web/src/components/landing.module.css`,
`landing.tsx`, `product-docs.tsx` and `apps/web/src/app/layout.site.tsx`.
Existing measured product screenshots remain intact. There are no backend,
database, dependency, credential or deployment-setting changes.
The production test server was stopped after validation.

## Visual refinement — 2026-10-10

The follow-up replaces the page-wide grid with a clean white canvas. ECG paper
appears only inside the signal illustration. The palette now uses red `#d52535`,
neutral text and gray borders. A shorter headline, larger type, wider desktop
layout and simpler incident flow replace the crowded labels and nested cards.
The entire ECG remains visible while a subtle highlight moves along it; reduced
motion stops the highlight. The hero explicitly labels the graphic as an
illustration, and the interactive walkthrough still uses example data.

Commands run from the repository root:

```bash
NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web
npm run typecheck --prefix apps/web
npm run format:check --prefix apps/web
PORT=3200 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web
node apps/web/scripts/check-site.mjs http://127.0.0.1:3200
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-project --with playwright python /workspace/pulse-ecg-refinement-check.py
git diff --check
```

All checks passed. Chromium exercised `/` and `/docs` at **1920, 1440, 1024,
768, 390 and 320 pixels** (12 page/viewport combinations). Measured backgrounds
are `rgb(255, 255, 255)` even with a dark OS preference; red branding is
`rgb(213, 37, 53)`. Minimum sampled text contrast is **5.07:1**. Hero buttons
measure at least 48 pixels high. There was no horizontal overflow, JavaScript
error or backend API request. Installation tabs, clipboard, navigation,
troubleshooting disclosures, images, normal/reduced motion and both recovered
and inconclusive walkthrough states passed. Desktop and mobile captures were
visually inspected. The HTTP smoke check confirmed both public pages and all
three existing screenshots load, while all eight checked operational paths
return 404.

The browser driver is a local validation helper outside the checkout. Captures
and measured results are retained at `/workspace/pulse-ui-results/ecg-refinement/`.
These checks validate the website illustration and navigation; they are not a
new real-telemetry incident run or a complete accessibility audit.

Changed application files: `apps/web/src/components/landing.module.css`,
`apps/web/src/components/landing.tsx` and
`apps/web/src/components/product-docs.tsx`. This report records the checks.
Python/backend tests, migrations, Compose and the full local dashboard build
were not rerun for this presentation-only refinement. The Vercel deployment was
not inspected; account access is unavailable and the environment's network
allowlist does not include its domain. Existing operational screenshots,
databases and reports were preserved. Only the temporary production server
started for these checks was stopped.
