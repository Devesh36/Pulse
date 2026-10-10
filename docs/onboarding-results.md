# REPL, distribution and landing-page validation

Validated on 2026-10-09. Pulse 0.2.0 adds `pulse repl` / `Pulse Repl`, numbered
demo choices, retained-data stop, installed demo assets, a preview Homebrew formula
and bootstrap installer, and a Next.js product home page. The operational overview
moved to `/dashboard`; the existing incident/lab routes and authentication remain.
Usage: [getting started](getting-started.md).

Current installation instructions track `main`. Branch names and commands below
retain their historical `work` references from the recorded validation run.

## Passed checks

Commands below ran from the checkout, with `UV_CACHE_DIR=/workspace/.cache/uv`.

```bash
uv lock
uv sync --frozen
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pyright
uv run --no-sync pytest -q --tb=short
npm run format:check --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
uv build --out-dir /workspace/pulse-dist-test
bash -n scripts/install-homebrew.sh
git diff --check
```

The complete Python run passed **156 tests**, with three optional integrations skipped
in that ordinary run. All **three integrations** were separately enabled and passed
against real PostgreSQL, Docker and the lab Prometheus in 4.37 seconds. PostgreSQL's
Alembic check found no new upgrade operations. Pyright reported zero errors/warnings;
lint, formatting, TypeScript and the Next.js production build passed.

New regressions cover consent refusal, only the selected scoped scenario being approved,
existing model/credential/resource preservation, missing Docker, stop without volume
deletion, blank input/EOF, failed demos, process-scoped mock settings, public-asset
upgrades, traversal/symlink refusal, and Homebrew bootstrap branch fetching and refusal
of dirty/different taps.

## Installed package

```bash
UV_TOOL_DIR=/workspace/pulse-install-test/tools \
UV_TOOL_BIN_DIR=/workspace/pulse-install-test/bin \
UV_LINK_MODE=hardlink \
uv tool install --from /workspace/pulse-dist-test/pulse_sre-0.2.0-py3-none-any.whl pulse-sre
```

From `/tmp`, the installed `pulse --version`, `pulse lab --help`, and piped
`Pulse Repl` help/status/reports/cancel/exit flow passed. No checkout or Docker startup
was required for this check. Wheel/source-archive inspection confirmed public demo
assets, API source/migrations, Dockerfiles, frontend source/lockfile and scenario
fixtures were included, while credentials, reports, node_modules and compiled caches
were excluded. Initial artifact sizes were about 416KB (wheel) and 344KB (source archive).
The wheel was built from the source archive. Public assets materialize into user-owned
storage; upgrades preserve credentials and reports.

The API Dockerfile's copy layout was reproduced in `/workspace/pulse-api-context-check`,
then installed with `uv sync --frozen --no-dev --no-editable`. SQLite migration and API
import passed with the custom build hook and without frontend/lab assets in that API
layout. No duplicate full Docker stack or rebuilt development image was required.

## Real REPL demo

```bash
uv run --no-sync python examples/incident-lab/scripts/verification-session.py up
uv run --no-sync python /workspace/pulse-repl-real-check.py
uv run --no-sync pulse lab stop
uv run --no-sync python examples/incident-lab/scripts/verification-session.py down
```

The [REPL driver](/workspace/pulse-repl-real-check.py) supplied `demo`, explicit `yes`,
`reports`, then `exit`. The cloud's limited-disk session reused the development
PostgreSQL server and four scoped lab containers. Only the evaluator's API-restart
command was redirected to the helper's native lab API restart; the actual REPL,
consent, Docker preflight, discovery, evaluator and report display ran unchanged.

[The measured report](../examples/incident-lab/reports/demo-1791561051508959369/evaluation-summary.md)
records one passing crash scenario: detection in **1.30 seconds**, **five real tool
results**, **two validated citations**, one executed approved Start, RECOVERED,
zero unexpected baseline incidents, and final-state persistence after API restart.
Fresh source spans were Docker state **7.072s**, Docker stats **8.069s**, and HTTP
health **7.059s**, meeting the six-second stable window. Reasoning was mocked;
Docker state/stats, logs, events, probes and mutation were real. This is not a
live-model evaluation.

REPL demo reports use timestamped directories. All seven earlier root report files
remained byte-for-byte unchanged. The new stop command retained data; final helper
cleanup retained databases, named volumes and reports. Original development container
identities, start times and restart counts were unchanged. Temporary native API/web
processes were stopped.

## Browser and Homebrew checks

Chromium/Playwright checked the production Next.js server at localhost:3100 at desktop
1440px and mobile 390px widths: landing content, workspace route, walkthrough controls,
missing-telemetry INCONCLUSIVE explanation, uv/Homebrew tabs, clipboard contents,
mobile horizontal overflow and dashboard authentication. No browser errors occurred.
Desktop/mobile screenshot artifacts are retained under `/workspace/pulse-ui-results`.

The installer passed Bash syntax and orchestration tests with mock `brew`/`git`
executables, including shallow-tap branch fetching, dirty-tap refusal and wrong-remote
refusal. The formula uses a locked isolated uv environment and avoids duplicate
capitalized symlinks on case-insensitive filesystems. **Native Homebrew was not
installed on this cloud host**, so an actual `brew install`/macOS run remains unverified.

No PyPI upload, tagged release, public site deployment, production-stack change or
infrastructure-permission expansion was performed. The preview install methods use
the existing GitHub `work` branch. CI now includes installed-wheel CLI smoke checks;
remote CI results are separate from these local measurements.

After pushing implementation commit `d00a6d1`, the actual advertised GitHub uv
installation also passed from `/tmp` using isolated tool/bin/data directories:

```bash
uv tool install --from git+https://github.com/Devesh36/Pulse.git@work pulse-sre
pulse --version
Pulse Repl
pulse lab --help
```

Both executables were installed; version reported 0.2.0. Help/status/reports/exit
and empty stdin passed outside a checkout without starting Docker or creating
credentials. The Homebrew bootstrap disables auto-update only for its install
command so the selected preview tap cannot be replaced with `main` mid-install.
