# Product documentation and screenshots

Validated on the cloud host on 2026-10-09. This increment adds a public Next.js
`/docs` guide, documentation and About sections on the landing page, shared public
navigation that remains visible on mobile, and actual product screenshots. README
and the installation guide describe the same workflow.

## Screenshot provenance

The three PNG files in `apps/web/public/screenshots/` total approximately 416 KiB.
They were captured with Chromium from the production frontend, without fabricating
API responses or changing displayed measurements:

- `overview.png`: the existing development API's measured overview, including
  discovered services, resource charts and incident activity.
- `investigation.png`: retained `pulse_verification_lab` history for a real stopped
  demo-worker incident, exit code 42, cited logs and recorded action lifecycle.
- `verification.png`: the same incident's **RECOVERED** result, **5 observations over
  17.2 seconds**, requiring Docker state, Docker metrics and HTTP health.

The lab diagnosis uses deterministic mock reasoning with low qualitative confidence.
Its measurements and approved action came from the earlier real incident-lab run;
this increment did not inject another fault or execute remediation. The temporary
history API disabled monitoring and all startup action/verification resumption.
The disconnected banner in the investigation capture reflects the stopped lab.
Screenshots are static records, not live telemetry or live-LLM evaluation.

Read-only captures used the existing credentials for ordinary local session login.
No credentials were displayed, changed or included in screenshots or distributions.
The original development containers retained their identities, start times and
restart counts. Databases, volumes and existing reports were preserved.

## Commands and results

| Exact command | Result |
|---|---|
| `npm run build --prefix apps/web` | PASS; Next.js 16.4.0 production build, `/` and `/docs` statically generated |
| `npm run typecheck --prefix apps/web` | PASS |
| `npm run format:check --prefix apps/web` | PASS |
| `apps/web/node_modules/.bin/prettier --check apps/web/scripts/start.mjs` | PASS |
| `node --check apps/web/scripts/start.mjs` | PASS |
| `.venv/bin/ruff check scripts/build-hook.py` | PASS |
| `.venv/bin/ruff format --check scripts/build-hook.py` | PASS |
| `.venv/bin/pytest tests/test_onboarding.py -q` | PASS; 24 passed, 0 failed, 0 skipped |
| `docker compose config --quiet` | PASS |
| `docker compose -f examples/incident-lab/docker-compose.yml --profile dashboard config --quiet` | PASS |
| `UV_CACHE_DIR=/workspace/.cache/uv uv build --wheel --out-dir /workspace/pulse-docs-dist` | PASS |
| `PORT=3100 PULSE_API_URL=http://127.0.0.1:8300 npm run start` in `apps/web` | PASS; standalone website, screenshot assets copied with the server |
| `python3 /workspace/pulse-docs-browser-check.py` | PASS; Chromium at 1440, 390 and 320 pixel widths |
| `.venv/bin/python examples/incident-lab/scripts/verification-session.py check` | PASS; unrelated development containers unchanged |
| `git diff --check` | PASS |

Changed files:

- `README.md`
- `apps/web/AGENTS.md` (generated Next.js version-specific agent guidance)
- `apps/web/Dockerfile`
- `apps/web/scripts/start.mjs`
- `apps/web/src/app/docs/page.tsx`
- `apps/web/src/components/landing.tsx`
- `apps/web/src/components/landing.module.css`
- `apps/web/src/components/product-nav.tsx`
- `apps/web/src/components/product-screenshots.tsx`
- `apps/web/public/screenshots/overview.png`
- `apps/web/public/screenshots/investigation.png`
- `apps/web/public/screenshots/verification.png`
- `docs/getting-started.md`
- `docs/product-docs-results.md`
- `scripts/build-hook.py`

The cloud browser driver verified public navigation, all guide anchors, all seven
REPL commands, uv/Homebrew tabs, actual clipboard contents, troubleshooting
disclosures, all three loaded screenshots and their full-size PNG responses. There
was no horizontal overflow, JavaScript error or API request from the public pages.
The guide remained functional with the temporary history API stopped and browser
API requests blocked. Desktop/mobile captures are retained outside the checkout
at `/workspace/pulse-ui-results/docs-1440.png` and `docs-390.png`.

A direct nested-ZIP inspection of the built wheel compared each screenshot and
the documentation/asset-delivery sources byte-for-byte against the checkout. All
matched; credentials, reports, node_modules and compiled output were absent. Public
assets are now included in the wheel's demo bundle and copied into both native and
Docker standalone frontend output.

## Initial failures and limits

The initial development-mode capture hit the existing CSP restriction on development
`eval`, so captures and browser validation used the production build. A history
selection against the development database found no suitable verification record;
the investigation instead uses the existing measured lab database with its worker
disabled. Initial screenshot requests returned 404 because new files were captured
after the preview server had indexed its public directory; building and starting
with all final assets present resolved this, and all three PNG/optimized-image
requests passed the final browser check.

The default uv cache path was read-only on this host; the wheel build used the
workspace cache shown above. An attempted preview restart encountered its previous
process still bound to port 3100; only this task's native process was stopped before
restarting. Final checks have no unresolved failures.

No database schema or recovery-engine changes were made, so migrations, fault
scenarios and backend integration suites were not rerun for this documentation
increment. Their earlier measurements remain in the existing validation reports.
Native Homebrew installation remains unverified on this Linux host. Docker frontend
images were not rebuilt; Compose and the equivalent native standalone asset delivery
were checked. No deployment, release or live-model evaluation was performed.
