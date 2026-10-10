# Deploy the public Pulse website on Vercel

The public build contains only `/` (landing page), `/docs`, static assets and
screenshots. The navigation offers **Install Pulse** rather than a hosted
dashboard link. Standalone imports use `apps/web/vercel.json`; imports from the
repository root use a single `web` service in the root `vercel.json`.

There is no backend service or service binding. The website needs no Pulse API URL,
Docker socket, database, administrator token or model credentials. Product screenshots
are retained captures, not live telemetry. Visitors install Pulse to run the dashboard
and guided incident lab on their own machines.

## Vercel project settings

1. Import `Devesh36/Pulse` from the **`work` branch**, which contains the website.
   At the time of this patch, `main` still renders the operational dashboard at `/`
   and does not contain the landing page. Redeploying that old branch will keep
   serving the old product. Changes must reach `main` before using it for this site.
2. Click **Import single project** beside **web / Next.js**. Use Root Directory
   **`apps/web`** and framework **Next.js**.
3. Leave build/install overrides disabled: `apps/web/vercel.json` supplies
   `npm ci` and `npm run build:site`. The build selects public routes and checks
   the resulting manifest. No environment variables are required.
4. Review the preview deployment: `/`, `/docs` and screenshots should load;
   `/dashboard`, `/lab` and `/api/v1/health` should return 404.

No Vercel project was linked or deployed while preparing this patch.

For an existing project, create a new deployment from `work` rather than merely
redeploying the previous commit. Confirm the deployment's source commit includes
this patch. Select `work` as the production branch if this project should track it;
branch pushes otherwise create previews according to the project's Git settings.

The repository-root Services import is also supported: leave Root Directory at
`.` and use its checked-in single-`web` configuration. Do not import FastAPI for
the public website. The two root directory options select different configuration
files; use one option for each project.

## Local checks

```bash
npm ci --prefix apps/web
npm run build:site --prefix apps/web
vercel dev --local --listen 127.0.0.1:3199
```

In another terminal, check the running public website:

```bash
cd apps/web
node scripts/check-site.mjs http://127.0.0.1:3199
```

The check verifies the production manifest, both public pages, installation links,
all three PNG screenshots, and 404 responses for eight operational/API paths.
Build before running it. Stop the local Vercel runner with Ctrl-C.

For a public-site-only Next development server without Vercel:

```bash
npm run dev:site --prefix apps/web -- --hostname 127.0.0.1 --port 3199
```

Outside Vercel, `npm run dev` and `npm run build` still include the local operational
dashboard and API proxy. `build:site` and `dev:site` set `PULSE_PUBLIC_SITE=1` for
their Next child process. `VERCEL=1` also selects the public profile, so Vercel's
default `npm run build` excludes operational routes even if a project overrides
the checked-in build command. Next's compound `site.tsx` page extension selects
the public entrypoints. The local pages remain in source but are absent from the
public route manifest.
CI builds both profiles and also checks Vercel's default build with the explicit
public-site flag disabled. Unexpected public routes fail the manifest check.

See [validation commands and results](vercel-landing-results.md).
