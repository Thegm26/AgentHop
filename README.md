# AgentHop

<img src="frontend/public/assets/agenthop-mascot.png" alt="AgentHop mascot" width="160" />

**A local, tray-first way to switch AI coding CLI profiles without leaving resumable work behind.**

AgentHop is an independent, unofficial project and is not affiliated with,
endorsed by, or supported by OpenAI. Its first adapter supports Codex; the
application is designed so other providers can be added without putting their
credentials or storage conventions into the core.

## What it does

AgentHop separates two things that are easy to accidentally conflate:

- Per-profile homes keep credentials and profile configuration isolated.
- Shared provider state preserves the rollouts and indexes needed to resume
  work after switching profiles.

The Linux desktop experience lives in the system tray. Choose an enabled profile
to make it active, then open the dashboard only when you need onboarding,
details, or a copyable command for a new or resumed session. AgentHop does not
run Codex commands in the browser, and the browser never receives credentials.

## Install with npm

AgentHop is published as a Linux npm package. Install it globally, then launch
the tray application:

```bash
npm install -g @thegm26/agenthop
agenthop
```

`npx @thegm26/agenthop` also works for a temporary install. The first launch creates an
isolated Python runtime under `$XDG_CACHE_HOME/agenthop` (or `~/.cache/agenthop`). It needs Python 3.11+ with venv support,
Node.js 18.19+, the Codex CLI on `PATH`, and these Linux desktop libraries:
GTK 3, WebKit2GTK 4.1, and Ayatana AppIndicator3. On Ubuntu 24.04:

```bash
sudo apt install python3-venv python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-ayatanaappindicator3-0.1
```

The dashboard stays local and opens from the AgentHop system-tray icon. A
second `agenthop` invocation opens the existing dashboard.

## Quickstart from source

Requirements: Python 3.11+, Node.js 18.19+ (Node 20+ recommended), npm, and a
Codex CLI installation available on `PATH`. Each profile must be authenticated
through Codex's supported login flow. On Linux desktop mode also requires GTK 3,
WebKit2GTK 4.1, and Ayatana AppIndicator3 from your distribution.

From a fresh checkout:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
npm --prefix frontend ci
./scripts/desktop.sh
```

The launcher builds the frontend when necessary, starts a loopback-only backend,
and remains in the system tray without opening a dashboard window. Starting it
again opens the existing dashboard rather than another backend.

To add a desktop-menu entry (this is never installed automatically):

```bash
./scripts/install-desktop-launcher.sh
```

The installed `.desktop` launcher invokes `scripts/desktop.sh`. If you already
have built frontend assets, `.venv/bin/agenthop desktop` is an alternative
launcher.

## Onboard a Codex profile

Open the dashboard from the tray and select **Add account**. Enter a profile
name, copy the displayed command into a terminal, finish the Codex sign-in, then
return to AgentHop and refresh usage. The normal `~/.codex` home is discovered
as `default`; named profile homes are discovered under `~/.codex-profiles`.

For manual setup, create one directory per identity and use the Codex login
flow—do not copy another profile's `auth.json`:

```bash
mkdir -p "$HOME/.codex-profiles/account-01"
chmod 700 "$HOME/.codex-profiles/account-01"
env CODEX_HOME="$HOME/.codex-profiles/account-01" \
  codex -c 'cli_auth_credentials_store="file"' login --device-auth
```

See the official [Codex authentication guide](https://developers.openai.com/codex/auth)
for other supported credential-store and sign-in options.

If a saved profile is disconnected or its token is revoked, use **Reconnect**
on that profile. AgentHop gives you a profile-scoped `codex login` command; it
does not delete or recreate the profile, so its configuration and shared session
state remain in place. A `Codex app-server timed out` status is a transient
usage check failure: use **Retry refresh** rather than removing the profile.

## Continuity and safety

Before first migration, back up your Codex homes and stop running Codex
processes. Resume discovery depends on both rollout files and Codex's SQLite
thread index; moving files alone can make older conversations appear missing.
AgentHop migrates unique state, reconciles known index paths, and preserves
different same-path files with an `.agenthop-conflict-<hash>` suffix instead of
overwriting them. Inspect conflicts before removing anything.

AgentHop is a local profile and continuity manager. It does not create accounts,
pool subscriptions, bypass limits, or decide whether an account setup complies
with a provider's terms. Use only accounts you are authorized to use. Keep the
service on loopback and never commit profile homes, tokens, `auth.json`, local
databases, or session rollouts. For OpenAI services, review the
[Terms of Use](https://openai.com/policies/terms-of-use/).

## Development

Run the complete local development stack:

```bash
.venv/bin/python -m pip install -e '.[dev]'
npm --prefix frontend ci
PYTHON=.venv/bin/python make dev
```

This starts the API on port 8000 and Vite on port 8080. For individual checks:

```bash
.venv/bin/python -m pytest tests/backend
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
```

`.venv/bin/agenthop` starts the standalone loopback API on port 8765. The interactive API
reference is available at `/docs`; use Vite's port-8000 proxy when developing the
frontend.

## Supervised Codex rotation

`agenthop auto` keeps an interactive Codex terminal attached while it checks its
own launched profile every 30 seconds. It changes profiles only after the authoritative
five-hour or weekly counter is at 100%, never consumes reset credits, and resumes
the proven root session with `continue` after a switch. It deliberately does not
switch on critical, unknown, or failed usage checks.

```bash
agenthop auto -- resume SESSION_ID
agenthop auto --poll-interval 60 --continue-prompt continue -- "your initial prompt"
agenthop auto --review-drain-threshold 85 --review-drain-grace 45 -- resume SESSION_ID
```

The convenience shell function `codex-auto` passes its arguments to this mode
while retaining its fixed workspace, approval, search, and `/tmp` options. You
can run multiple terminal instances at once: each independently tracks and
resumes its own root session, while profile selection is briefly coordinated on
disk. Use Ctrl-C to stop only that terminal's supervisor; when every usable
profile is exhausted, each affected instance waits and polls until capacity
returns. For safety, if AgentHop cannot uniquely match
the running process's root rollout to the shared Codex SQLite index, it leaves
the process running and disables automatic rotation rather than resuming a
possibly wrong thread.

When either known five-hour or weekly usage reaches 85%, AgentHop queues a
message to the proven root session asking active reviewer and subagent work to
finish and return findings. Set `--review-drain-threshold` from 1 to 99 to tune
that early handoff. It gives that work 45 seconds by default before a subsequent
rotation; use `--review-drain-grace 0` to disable this best-effort handoff, or
set up to 120 seconds. The request uses Codex's non-interactive `queue` command
with the bound profile environment, so AgentHop never writes synthetic input to
the shared interactive terminal. If the early queue request fails, or the
threshold is missed, rotation still proceeds; on confirmed exhaustion it makes
one final best-effort request before stopping the owned Codex process.

## Publishing a release

The package tarball builds the dashboard before publishing and contains the
Python backend, desktop launcher, and built frontend. Before publishing, run:

```bash
npm run test:package
npm pack --dry-run
npm publish --access public
```

Publishing requires an authenticated npm account with permission to publish to
the `@thegm26` scope. npm will run `prepack` automatically during `npm publish`.

## Further reading

- [Architecture](docs/ARCHITECTURE.md) — component, storage, and migration design.
- [Provider adapters](docs/PROVIDER_ADAPTERS.md) — adapter contract and boundaries.
- [Security](docs/SECURITY.md) and [vulnerability reporting](SECURITY.md).
- [Contributing](CONTRIBUTING.md).

## License

[MIT](LICENSE)
