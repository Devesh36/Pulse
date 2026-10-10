# Keeping the Phases section current

The landing page’s **Phases** navigation link opens `/#phases`. The same link is
available from Docs. The timeline groups product changes into phases, with an
impact summary, UTC date and a GitHub commit link for each recorded commit.
Earlier phases can be expanded; the current repository-companion phase opens by
default. Black/red styling follows the rest of the public site.

Content lives in `apps/web/src/lib/product-history.ts`; rendering lives in
`apps/web/src/components/product-phases.tsx`. It is bundled with the website and
works without a backend, GitHub API credentials, or Git access during deployment.

For every change made through a chat or contribution:

1. Add an entry to the appropriate phase in the same patch, recording its UTC
   date, a concise title and what the change enables or corrects for users.
2. Give a previous completed entry its exact SHA from `git log` when available.
   The new entry omits `commit` and displays **This update**. A commit cannot
   contain its own final hash; the next contribution backfills it. Never link an
   entry to a guessed hash.
3. Include each subsequent commit, including integration/merge commits. Explain
   that a merge brings existing work together rather than claiming a new feature.
4. Preserve history. Describe an abandoned visual direction in the past tense,
   and keep real telemetry, mock reasoning, local checks and remote deployment
   claims distinct. Summarize the product impact instead of publishing chat text.
5. Run frontend formatting, type checking and production builds. Check the
   navigation, expandable details and narrow-screen layout in a browser.

`AGENTS.md` and `CONTRIBUTING.md` carry this rule for future repository work.
Entries are maintained alongside code changes; the website does not ingest
private conversations or automatically infer product claims from commit titles.

## Validation on 10 October 2026

All 14 existing Git commits were checked against the history data: each appears
once, and its displayed UTC date matches its Git author timestamp. The section
has six phase groups and fifteen dated entries, including this update. The
current entry’s commit link will be backfilled with the next contribution.

These commands passed from the repository root:

```bash
npm run format:check --prefix apps/web
npm run typecheck --prefix apps/web
NEXT_TELEMETRY_DISABLED=1 VERCEL=0 PULSE_PUBLIC_SITE=0 npm run build --prefix apps/web
NEXT_TELEMETRY_DISABLED=1 npm run build:site --prefix apps/web
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync ruff check .
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync ruff format --check .
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pyright
UV_CACHE_DIR=/workspace/.cache/uv uv run --no-sync pytest -q --tb=short
```

Pytest reported **207 passed, 3 skipped** in 32.27 seconds. The three opt-in
infrastructure tests were not rerun for this website-only change. No new backend
behavior, schema or infrastructure configuration was introduced.

The final public build contained only landing and Docs. An owned test server ran
with `PORT=3300 NEXT_TELEMETRY_DISABLED=1 npm run start --prefix apps/web`.
`node apps/web/scripts/check-site.mjs http://127.0.0.1:3300` passed: landing,
Docs and screenshots loaded; operational routes returned 404.

The session-only Chromium harness ran with
`UV_CACHE_DIR=/workspace/.cache/uv uv run --no-project --with playwright python /workspace/pulse-history-browser-check.py`.
It passed at 1440, 1024, 768, 651, 650, 390 and 320 px: navigation from both
landing and Docs, all phase disclosures, keyboard operation, fourteen exact
commit-link URLs and JavaScript-disabled reading. It found no overflow, browser
errors or operational API calls. Desktop/mobile screenshots were visually
reviewed, and the black/red styling was retained. The owned server was stopped
afterward; existing development services, databases and reports were untouched.
Remote Vercel rendering was not verified.
