# Deploy the public Pulse website on Vercel

The repository-root `vercel.json` defines one Next.js service named `web`, built
from `apps/web`. All public requests go to that service. Its public build contains
only `/` (landing page), `/docs`, static assets and screenshots. The navigation
offers **Install Pulse** rather than a hosted dashboard link.

There is no backend service or service binding. The website needs no Pulse API URL,
Docker socket, database, administrator token or model credentials. Product screenshots
are retained captures, not live telemetry. Visitors install Pulse to run the dashboard
and guided incident lab on their own machines.

## Vercel project settings

1. Import `Devesh36/Pulse` and select the branch containing this patch.
2. Leave the project **Root Directory at the repository root** (`.`), so Vercel
   reads the root `vercel.json`. The service root is already `apps/web`.
3. Use the checked-in service settings without overriding the build command.
   `npm run build:site` selects the public routes and checks the resulting manifest.
4. Review the preview deployment: `/`, `/docs` and screenshots should load;
   `/dashboard`, `/lab` and `/api/v1/health` should return 404.

No Vercel project was linked or deployed while preparing this patch.

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

`npm run dev` and `npm run build` still include the local operational dashboard and
API proxy. `build:site` and `dev:site` set `PULSE_PUBLIC_SITE=1` for their Next child
process. Next's compound `site.tsx` page extension selects the public entrypoints;
the local pages remain in source but are absent from the public route manifest.
CI builds both profiles and rejects unexpected public routes.

See [validation commands and results](vercel-landing-results.md).
