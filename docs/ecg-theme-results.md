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
