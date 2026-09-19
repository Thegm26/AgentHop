# AgentHop

**Switch AI CLI accounts without leaving your work behind.**

AgentHop is a provider-neutral, local-first dashboard for managing AI coding CLI
accounts. Its first working adapter targets Codex. The long-term design can host
other providers without making their credentials, storage layouts, or usage
models part of the core application.

> [!IMPORTANT]
> AgentHop is an independent, unofficial project. It is not affiliated with,
> endorsed by, or supported by OpenAI.

The dashboard includes the AgentHop mascot artwork: a central meditating agent
surrounded by companion agents handling the work in progress.

## The problem

An AI CLI account is more than a login token. A CLI home can also contain
configuration, conversation rollouts, a session index, locks, and other runtime
state. A simple account switcher that points the whole CLI at a different home
does isolate credentials—but it also isolates the history needed by `resume`.
The account changes successfully, while the conversation appears to disappear.

AgentHop models these as separate concerns:

- **Credentials stay isolated** in per-account profile homes.
- **Resumable work stays shared** through provider-defined state paths and
  indexes.
- **Provider behavior stays behind an adapter**, keeping the dashboard and API
  independent of Codex-specific details.

For Codex, this is built around its documented `CODEX_HOME`, authentication,
and app-server interfaces. See the official [environment-variable
reference](https://developers.openai.com/codex/config-file/environment-variables),
[authentication guide](https://developers.openai.com/codex/auth), and [app-server
documentation](https://developers.openai.com/codex/app-server).

## Current status

AgentHop is an MVP. The Codex adapter and local dashboard are the first supported
path. Provider expansion, packaging, recovery tooling, and broader platform
coverage belong to the roadmap; they are not presented as finished features.

The MVP is designed to:

- discover locally configured Codex profiles;
- show profile status and available usage information;
- select the profile used for the next Codex launch;
- keep authentication material separate from shared resumable state;
- migrate existing session files, preserve conflicts, and backfill their SQLite
  thread metadata; and
- expose those operations through a small FastAPI backend and React dashboard.

## How it works

```text
React dashboard
      |
      | local HTTP/JSON
      v
FastAPI application
      |
      v
Provider registry ----> Codex adapter ----> Codex CLI / app-server
                              |
                  +-----------+-----------+
                  |                       |
          isolated profile homes     shared session state
          (credentials/config)       (rollouts/index/locks)
```

The browser never needs the contents of a credential file. It asks the local
backend for sanitized profile data; the backend delegates provider-specific work
to the adapter. The Codex adapter queries the official app server for live status
and prepares a safely quoted command for the user to run. The MVP does not run an
interactive Codex session inside the browser.

For a deeper treatment, read [Architecture](docs/ARCHITECTURE.md), [Provider
adapters](docs/PROVIDER_ADAPTERS.md), and the DEV.to-ready [project
article](docs/ARTICLE.md). Its companion [publishing checklist](docs/DEVTO_PUBLISHING.md)
includes the cover image and final upload steps.

## Requirements

- Python 3.11+
- Node.js 18.19+ and npm (Node 20+ is recommended)
- the Codex CLI installed and available on `PATH`
- a local Codex login for every profile you want to use

For the recommended Linux desktop mode, also install the distribution packages
for GTK 3, WebKit2GTK 4.1, and Ayatana AppIndicator3. They are system runtime
dependencies; AgentHop does not install them into its Python environment.

AgentHop is a local profile and continuity manager. It does not create accounts,
combine or pool subscriptions, bypass limits, or determine whether an account
setup or use complies with a provider's policies. Use only accounts you are
authorized to use and follow the provider's terms. For OpenAI services, review
the [Terms of Use](https://openai.com/policies/terms-of-use/) and the [account
switching help article](https://help.openai.com/en/articles/20001068).

## Quickstart

This project is under active development. From the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
./scripts/desktop.sh
```

This rebuilds the dashboard when its source has changed, starts a loopback-only
backend, and stays in the Linux system tray without opening a dashboard window.
Click the tray icon to see available profiles and their visible status/reset
information. Choose an enabled profile there to switch directly.
Use **Open dashboard…** only for detail, onboarding, or a new-session command.
Running the launcher a second time opens the existing dashboard instead of
starting another backend. The browser UI never receives credentials. The
**Start new session** dialog intentionally stays a copyable command in this MVP;
AgentHop does not execute shell commands for you.

To add an application-menu launcher (never installed automatically):

```bash
./scripts/install-desktop-launcher.sh
```

### Browser development mode

For frontend work, use separate terminals:

```bash
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:8080`). Keep the API
bound to loopback unless you have added authentication and transport security.
The CLI defaults to port `8765`; the development frontend currently proxies to
port `8000`, which is why the quickstart sets it explicitly. The proxy target is
currently fixed in `frontend/vite.config.ts`.

The frontend is tested on the locally available Node 18.19 runtime. The pinned
development toolchain keeps that compatibility, but a full `npm audit` currently
reports two moderate, development-only findings under Vitest's mocker. Runtime
dependencies are clean under `npm audit --omit=dev`; the automated fix requires a
breaking Vitest upgrade. Do not expose the Vite development server to untrusted
networks.

### Add a Codex profile

AgentHop discovers the normal `~/.codex` home as `default` and named directories
under `~/.codex-profiles`. In the dashboard, click **Add account**, enter a
profile name, then copy and run the displayed command in your terminal. Complete
the browser sign-in and click **Refresh usage**. The dashboard creates the local
profile but never receives your password or login token.

To add a file-backed profile manually with a valid name (letters, numbers,
dots, dashes, or underscores; maximum 64 characters), use Codex's supported login
flow:

```bash
mkdir -p "$HOME/.codex-profiles/account-01"
chmod 700 "$HOME/.codex-profiles/account-01"
CODEX_HOME="$HOME/.codex-profiles/account-01" \
  codex -c 'cli_auth_credentials_store="file"' login --device-auth
```

Use a different directory for each identity. Do not copy `auth.json` between
profiles. Other supported login and credential-store options are described in
the official [Codex authentication guide](https://developers.openai.com/codex/auth).

### Useful development commands

```bash
# Backend tests (or: make test)
pytest tests/backend

# Start the backend on its standalone default port
agenthop

# Frontend development and production build
cd frontend
npm run dev
npm test
npm run lint
npm run build
```

The root `Makefile` provides `make install`, `make dev`, and `make test`. `make
dev` uses the backend's standalone port `8765`, so use the explicit port `8000`
command from the quickstart when pairing it with Vite's configured proxy.

### Production build expectations

`npm run build` writes static assets to `frontend/dist`. Desktop mode serves this
directory through the loopback FastAPI process, so relative `/api` calls remain
same-origin. Set `AGENTHOP_FRONTEND_DIST` to an explicit built-assets directory
for a future package layout. If the build is missing, `scripts/desktop.sh` builds
it; direct `agenthop desktop` reports an actionable startup error. Remote and
multi-user deployment are outside the MVP.

## HTTP API

The FastAPI OpenAPI page at `/docs` is the authoritative interactive reference.
The MVP routes are:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Check service version and health |
| `GET` | `/api/state` | List providers, profiles, sessions, and a suggested profile |
| `POST` | `/api/refresh` | Refresh account and usage data through adapters |
| `POST` | `/api/providers/{provider}/accounts/{account}/activate` | Select an account |
| `POST` | `/api/providers/{provider}/accounts/{account}/command` | Prepare a new/resume shell command |

The command request uses `{"mode":"new"}` or
`{"mode":"resume","sessionId":"..."}`. API JSON uses camel-case names such as
`fiveHourUsed`, `weeklyResetsAt`, and `updatedAt`. Generated commands contain the
selected `CODEX_HOME` and shared SQLite home; review and run them in your terminal.
Preparing the first command also performs continuity migration, so stop Codex and
make a backup before doing this with existing profiles.

Reset and session timestamps are integer Unix epochs. The dashboard accepts reset
times in seconds or milliseconds and shows how long remains until each reset.
The API still supports session discovery and resume commands, but the dashboard
does not display a recent-conversations list.

## Safe operating model

AgentHop manages security-sensitive local state. Before using real profiles:

1. Back up your existing Codex home and profile directories.
2. Stop running Codex processes before a first migration.
3. Run AgentHop as your normal user—not as root.
4. Keep the server on `127.0.0.1`.
5. Inspect migration errors instead of deleting or overwriting colliding files.

The `agenthop` CLI only accepts loopback bind addresses. The API also validates
the HTTP `Host` header and rejects browser `Origin` headers outside `localhost`,
`127.0.0.1`, or `[::1]` (with any local port). Requests without an `Origin`
header remain possible for local tools such as `curl`; these checks are not user
authentication.

Never commit `auth.json`, tokens, profile homes, local databases, or session
rollouts. `.gitignore` is defense in depth, not a substitute for checking staged
files. See [Security](docs/SECURITY.md) and [the vulnerability reporting
policy](SECURITY.md).

## Why shared files alone are not enough

Codex resume discovery also depends on a SQLite thread index. Moving rollout
files into a common directory can leave that index pointing at the old profile
home—or omit migrated conversations entirely. The files exist, yet the picker
still looks empty.

The Codex migration therefore treats file movement and metadata reconciliation
as one operation: copy unique state, preserve different same-path files under a
content-derived conflict name, rewrite known rollout paths to the shared location,
and upsert thread rows conservatively. The
details and failure modes are documented in [Architecture](docs/ARCHITECTURE.md).

## Troubleshooting

### `resume` cannot find an older conversation

- Confirm the old rollout exists in the shared sessions directory.
- Confirm its thread row exists in the shared SQLite index and its rollout path
  points to the shared home.
- Restart processes that may have opened the database before migration.
- Do not manually edit the database while Codex or AgentHop is running.

### A profile shows as unauthenticated

Authenticate that profile through the provider-supported login flow. Do not copy
another profile's `auth.json`; that defeats isolation and may select the same
account twice. Codex authentication methods and credential storage are described
in the official [authentication guide](https://developers.openai.com/codex/auth).

### The backend cannot find `codex`

Run `codex --version` in the same shell used to start the backend. If it fails,
install the CLI or fix `PATH`, then restart AgentHop.

### Usage is unavailable

Usage data is provider-dependent and may be temporarily missing or unsupported.
An unavailable reading must not be interpreted as unlimited capacity. Check the
backend logs and confirm the selected profile can communicate with Codex. The UI
shows an em dash instead of a percentage when usage is unknown.

Accounts that are unauthenticated, marked duplicate, explicitly disallowed, or
blocked have their switch/start actions disabled. During a refresh or another
account operation, account actions are temporarily disabled to avoid overlapping
UI requests.

### A migrated file has `.agenthop-conflict-<hash>` in its name

AgentHop found different content at the same relative path and preserved both
files. The original shared file keeps its name; the incoming copy receives a
content-derived suffix. Inspect both before removing or renaming either one.

### The dashboard is reachable from another machine

Stop the server and bind it to `127.0.0.1`. The MVP is a single-user local tool,
not a hardened multi-user service.

## Roadmap

- harden the Codex migration and recovery experience;
- add explicit dry-run, backup, and migration audit views;
- package one-command local installation and startup;
- improve cross-platform coverage and automated compatibility checks;
- formalize adapter capability negotiation;
- add adapters for other AI CLIs after their state and auth boundaries are
  understood; and
- add optional local access controls before supporting non-loopback deployments.

Roadmap items are intentions, not commitments or currently supported behavior.

## Contributing

Start with [CONTRIBUTING.md](CONTRIBUTING.md). New provider integrations should
follow [the adapter contract](docs/PROVIDER_ADAPTERS.md) and must document their
credential boundary before implementation.

## License

[MIT](LICENSE)
