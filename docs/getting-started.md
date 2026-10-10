# Start with Pulse

For your own running Compose application, follow the
[repository companion guide](repository-companion.md): open `Pulse Repl` in that
repository and type `/demo` for automatic read-only setup and a local dashboard.
Normal recovery-enabled sessions use reviewed enrollment and `pulse watch`. The workflow below
demonstrates the separate authorized incident lab.

Install the preview from `main`, open the REPL, and type **/lab demo** to try the separate lab.
Git and uv are needed for the uv route. Homebrew installs Python and uv for its route.
Real demos need a running Docker Engine/Desktop with Compose v2. No model API key is needed.

## Install with uv

```bash
uv tool install --from git+https://github.com/Devesh36/Pulse.git@main pulse-sre
pulse repl
```

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first if needed.
Pulse requires Python 3.12+; uv can provision it. If `pulse` is not found, run
`uv tool update-shell`, then reopen your terminal. `Pulse Repl` works too.

## Install with Homebrew

The repository includes a preview tap formula; it is not a Homebrew core formula.
Install from the repository's default `main` branch:

```bash
curl -fsSL https://raw.githubusercontent.com/Devesh36/Pulse/main/scripts/install-homebrew.sh | bash
pulse repl
```

The [installer](../scripts/install-homebrew.sh) adds the explicit repository tap,
fetches `main` even when the tap was shallow-cloned, and installs
`--HEAD`. It refuses a dirty tap or a different existing remote. To inspect it first,
download the script to a local file and run it with Bash after review.

The formula installs an isolated Python environment using the committed uv lockfile.
Docker is a separate prerequisite. A native Homebrew installation was not available
on the cloud validation host; the equivalent locked installation and CLI were checked.

## Use the menu

```text
pulse › /lab demo
Continue? [y/N] y
```

The first demo builds and starts only the fixed `pulse-lab` Compose project, waits for
fresh discovery, then measures an actual crash, investigation, approval and recovery.
It explicitly asks before authorizing the lab test action. Deterministic mock reasoning
uses real Docker, Prometheus and HTTP observations. It makes no live-model calls.
The first build can take several minutes; later runs reuse images and data.

| Command | What happens |
|---|---|
| `/demo` or `1` | Scan and open the current project's read-only dashboard and monitor |
| `/lab demo` | Crash → evidence-backed investigation → approved start → recovery verification |
| `telemetry` or `2` | Successful and ineffective actions, selected telemetry loss, API restart and read-only restoration recheck |
| `/lab dashboard` | Open http://localhost:3100/lab |
| `/lab status` | Show fresh lab discoveries; no credentials are created by this command |
| `reports` or `5` | Show measured verdicts, citations, actions and actionable explanations |
| `/lab stop` | Stop the lab while preserving its database, credentials, volumes and reports |
| `quality` or `7` | Review retained evaluations, compatible baselines and improvement steps offline; no resource changes |
| `exit` or `0` | Leave the REPL; the lab remains available |

The dashboard uses the existing administrator login. The REPL prints the local
credential **file path**, never the token. Open that file privately and use its
`PULSE_ADMIN_TOKEN` to sign in. The landing page is `/`; the operational overview is
`/dashboard`; incident and lab routes retain their existing authentication.

An existing lab with a different model or missing matching credentials is not
silently replaced. Use its original installation to manage it. Start only one
`pulse-lab` project per Docker host. Native limited-disk cloud testing uses the
[small retained-data session](../examples/incident-lab/README.md#recovery-evidence-loss-evaluation);
normal installations use the self-contained Compose lab.

## Data and updates

The installed CLI carries the public sources, Compose definitions, locked build
dependencies and scenario fixtures needed for the demo. It works from any directory;
you do not need to clone a second repository. Credentials, previous reports, node_modules,
compiled frontend output and database files are excluded from the distribution.

Installed demo assets live in `$XDG_DATA_HOME/pulse/project` (default
`~/.local/share/pulse/project`), or `$PULSE_HOME/project` when set. Credentials are in
`examples/incident-lab/.env` under that directory, and reports in the neighboring
`reports/` directory. Upgrades replace bundled source files and retain mutable user
data. From a source checkout, Pulse uses that checkout's existing lab and credentials.

```bash
# Update a uv installation to the branch's latest commit:
uv tool upgrade pulse-sre

# Stop without deleting history, including outside the REPL:
pulse lab stop

# Advanced standalone commands remain available:
pulse lab --help
```

`pulse lab down` is the explicitly destructive disposable-lab teardown: it removes
lab volumes and database history. It retains host report files. Do not use it when
you want to retain the database. Uninstalling the CLI also leaves the user data
directory and any running Docker resources; stop the lab first.

## Product website

For a frontend-only preview from a checkout:

```bash
npm ci --prefix apps/web
npm run dev --prefix apps/web
```

Open http://localhost:3000 for the Next.js landing page. The interactive walkthrough
uses **clearly labeled example data** and works without an API. Install-command tabs,
clipboard copying, mobile layout and the missing-evidence example are interactive.
The real workspace at `/dashboard` needs the Pulse API. The REPL's lab startup builds
the frontend in Docker, so Node is not needed on users' hosts for the lab.

Choose **Docs** in the product navigation, or open http://localhost:3000/docs for
the dedicated first-run guide, runtime explanation, command reference, verification
outcomes, data storage and troubleshooting. The page includes actual recorded product
screenshots and works without the API. **About** on the landing page explains the
product and its approval model. In the REPL lab, the same guide is on port 3100.
The API schema reference is separate at http://localhost:8000/docs (8100 in the lab).

No PyPI release, official Homebrew core listing, public website deployment or live
LLM evaluation is claimed by this preview.
