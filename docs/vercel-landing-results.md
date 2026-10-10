# Public website configuration: validation results

Validated in the cloud checkout on 2026-10-09. Vercel CLI 63.1.0,
Node 24.19.0, Next.js 16.4.0 and Python 3.12 were used. This report covers
configuration and local execution, not a cloud deployment.

Current deployment instructions track `main`. The branch snapshots below retain
their historical `work` references; see the current [Vercel guide](vercel-landing.md).

## Commands and outcomes

Unless noted, run from the repository root.

| Command | Result |
| --- | --- |
| `NEXT_TELEMETRY_DISABLED=1 npm run build --prefix apps/web` | Passed; normal local build retains dashboard, lab, other operational routes and API proxy. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | Passed; only `/`, `/docs` and framework error handling are in the public route manifest. The manifest regression check passed. |
| `npm run typecheck --prefix apps/web` | Passed after both builds. |
| `npm run format:check --prefix apps/web` | Passed. |
| `cd apps/web && npx --no-install prettier --check scripts/site.mjs scripts/check-site.mjs` | Passed. |
| `cd apps/web && node scripts/check-site.mjs http://127.0.0.1:3199` | Passed against Vercel's real local runner. |
| `PORT=3200 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web` | Public production standalone server started successfully. |
| `cd apps/web && node scripts/check-site.mjs http://127.0.0.1:3200` | Passed against the real production server. |
| `UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync ruff check scripts/build-hook.py` | Passed. |
| `UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync ruff format --check scripts/build-hook.py` | Passed. |
| `UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pyright` | Passed; zero errors or warnings. |
| `UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pytest -q tests/test_onboarding.py` | 24 passed, no failures or skips. |
| `UV_CACHE_DIR=/workspace/.cache/uv uv build --wheel --out-dir /workspace/pulse-vercel-wheel` | Passed; wheel created outside the checkout. |
| `docker compose --profile demo config --quiet` | Passed; existing Compose configuration remains valid. |
| `.venv/bin/python examples/incident-lab/scripts/verification-session.py check` | Passed; unrelated development containers retained identities, start times and restart counts. |
| `git diff --check` | Passed. |

The Vercel runner was started with the following exact command. The XDG paths keep
CLI cache/config writes inside the writable workspace; `--local` avoids project
linking and pulling remote environment variables.

```bash
NO_UPDATE_NOTIFIER=1 \
XDG_DATA_HOME=/workspace/pulse-vercel-cli/data \
XDG_CACHE_HOME=/workspace/pulse-vercel-cli/cache \
XDG_CONFIG_HOME=/workspace/pulse-vercel-cli/config \
VERCEL_TELEMETRY_DISABLED=1 NEXT_TELEMETRY_DISABLED=1 NODE_USE_ENV_PROXY=1 \
/workspace/.cache/npm/_npx/cf16195db335a816/node_modules/.bin/vercel \
  dev --local --listen 127.0.0.1:3199 --non-interactive
```

It detected exactly one service, `web`, and ran `dev:site`. Both local test servers
were stopped after validation. No new Docker stack was started.

## Measured website behavior

For both Vercel dev and the production standalone server:

- `/` and `/docs`: HTTP 200, **Install Pulse** present, no `/dashboard` link.
- `/screenshots/overview.png`, `/screenshots/investigation.png` and
  `/screenshots/verification.png`: HTTP 200, `image/png`, valid PNG signatures.
- `/dashboard`, `/lab`, `/services`, `/incidents`, `/assistant`, `/settings`,
  `/api/v1/health` and `/api/schema`: HTTP 404.
- The production app manifest contains `/page`, `/docs/page`, `/_not-found/page`
  and `/_global-error/page`. No operational page or API handler is compiled.

These are real HTTP measurements. This increment performed no diagnosis, fault
injection or remediation and made no new live-LLM or telemetry claims. Existing
screenshots remain the previously measured local-product captures.

## Packaging check

The following inspection passed: all six public entrypoint/component/script assets
were present in the wheel's 91-file project bundle, with no mutable data,
credentials or installed dependencies.

```bash
python - <<'PY'
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
wheel = Path('/workspace/pulse-vercel-wheel/pulse_sre-0.2.0-py3-none-any.whl')
with ZipFile(wheel) as archive:
    with ZipFile(BytesIO(archive.read('pulse/resources/project.zip'))) as bundle:
        names = set(bundle.namelist())
        expected = {
            'apps/web/scripts/site.mjs', 'apps/web/scripts/check-site.mjs',
            'apps/web/src/app/page.site.tsx', 'apps/web/src/app/layout.site.tsx',
            'apps/web/src/app/docs/page.site.tsx',
            'apps/web/src/components/product-docs.tsx',
        }
        assert expected <= names
        assert not any(
            n.endswith(('.db', '.log')) or '/node_modules/' in n or
            '/reports/' in n or n.split('/')[-1].startswith('.env')
            for n in names
        )
PY
```

## Scope and limitations

Changed files: root `vercel.json`, `.vercelignore`, `.gitignore`, README and CI;
the web package scripts and Next config; three public `*.site.tsx` entrypoints;
the Docs wrapper and shared Docs component; landing/navigation props; two public
build/check scripts; the wheel asset allowlist; this report and the Vercel guide.
There are no backend, schema, dependency or lockfile changes.

An initial `uv` invocation failed because its default cache under `/home/agent`
is read-only. Repeating it with `UV_CACHE_DIR=/workspace/.cache/uv` passed.

Vercel cloud build/deployment was not run. Direct requests to Vercel documentation
and schema hosts were denied by the environment's network policy; the installed
Vercel CLI accepted and exercised the configuration locally. Database migrations,
backend integration suites and incident scenarios were not rerun for this
frontend-only increment. No databases, reports or credentials were deleted or changed.

## 2026-10-10: standalone import and default Vercel build

Investigation of the reported public-site mismatch established the following:

- `git ls-remote --heads origin main work` confirmed `main` at
  `3b04a551cfb5d487afcf12c1cff0ac338ce8c841`, and the previously pushed website on
  `work` at `c638bdc1f8184b5146d5ff8ab3332731bcee1c2b`.
- `git show 3b04a551cfb5d487afcf12c1cff0ac338ce8c841:apps/web/src/app/page.tsx`
  showed `return <Dashboard view="overview" />`. That branch has no landing-page
  component or public build script. The earlier import screenshot selected `main`.
- A request to `https://web-nine-delta-xhemr4gt8b.vercel.app/` was blocked by the
  environment proxy: CONNECT returned 403, curl exited 56 and reported HTTP `000`.
  This is an environment access denial, not a response from the deployed website.
  The live page and its deployed commit could not be inspected.
- No Vercel credential or linked project was available. Private project settings
  and deployment logs were not read or changed.

The follow-up adds `apps/web/vercel.json`, so standalone imports automatically
select the public build/install commands. `VERCEL=1` now independently selects
the public route profile, including when Vercel uses the default build command.
CI checks that behavior with `PULSE_PUBLIC_SITE=0`. The guide explains which
branch contains the website and both supported root directory choices.

| Follow-up command | Result |
| --- | --- |
| `VERCEL=1 PULSE_PUBLIC_SITE=0 NEXT_TELEMETRY_DISABLED=1 npm run build --prefix apps/web` | Passed; default Vercel build contains only `/`, `/docs` and framework error handling. |
| `node apps/web/scripts/check-site.mjs` | Passed against that manifest. |
| `npm run typecheck --prefix apps/web` | Passed. |
| `npm run format:check --prefix apps/web` | Passed. |
| `PORT=3200 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web` | Automatic Vercel-profile production server started. |
| `cd apps/web && node scripts/check-site.mjs http://127.0.0.1:3200` | Passed; public pages/screenshots load and all eight operational/API paths return 404. |
| `python /workspace/pulse-standalone-import-check.py` | Passed; frontend Vercel configuration and real HTTP behavior checked in standalone mode, with the parent Services configuration restored afterward. |
| `VERCEL=0 PULSE_PUBLIC_SITE=0 NEXT_TELEMETRY_DISABLED=1 npm run build --prefix apps/web` | Passed; normal local dashboard, lab and API proxy remain compiled. |
| `NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web` | Passed; explicit public profile still compiles only the public routes. |
| `cd apps/web && npx --no-install prettier --check vercel.json` | Passed. |
| `git diff --check` | Passed. |

The normal-build manifest was checked with this command from `apps/web`:

```bash
node --input-type=module -e 'import assert from "node:assert/strict"; import { readFile } from "node:fs/promises"; const routes = JSON.parse(await readFile(".next/server/app-paths-manifest.json")); for (const path of ["/dashboard/page", "/lab/page", "/api/[...path]/route", "/page", "/docs/page"]) assert.ok(path in routes, path); console.log("PASS: normal local build retains the operational product.");'
```

The standalone helper launches this command from `apps/web`, with the same XDG,
proxy and telemetry settings used above:

```bash
/workspace/.cache/npm/_npx/cf16195db335a816/node_modules/.bin/vercel \
  dev --local --local-config /workspace/Pulse/apps/web/vercel.json \
  --listen 127.0.0.1:3199 --non-interactive
```

The unlinked CLI initially ascended to the parent repository's Services project;
forcing the frontend configuration there served a directory listing and the HTTP
assertion failed. The helper isolates the standalone configuration by temporarily
moving only the parent `vercel.json`, then restores it in `finally` after stopping
the test process. In standalone mode the CLI ran `dev:site`, and the full HTTP
check passed. An initial helper backup under `/tmp` failed with a cross-filesystem
rename; using a backup in the same directory resolved that setup issue.

These measurements verify local production and standalone import behavior. They
do not establish which commit the inaccessible live URL serves. Switching the
Vercel deployment to the website branch is still required if it currently uses
the old `main` commit. No main-branch merge, cloud deployment or project-settings
mutation was performed. No Docker stack, database or incident engine was changed.
