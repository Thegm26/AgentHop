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

## Quickstart

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
CODEX_HOME="$HOME/.codex-profiles/account-01" \
  codex -c 'cli_auth_credentials_store="file"' login --device-auth
```

See the official [Codex authentication guide](https://developers.openai.com/codex/auth)
for other supported credential-store and sign-in options.

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

## Further reading

- [Architecture](docs/ARCHITECTURE.md) — component, storage, and migration design.
- [Provider adapters](docs/PROVIDER_ADAPTERS.md) — adapter contract and boundaries.
- [Security](docs/SECURITY.md) and [vulnerability reporting](SECURITY.md).
- [Contributing](CONTRIBUTING.md).
- [Project article](docs/ARTICLE.md) and [publishing checklist](docs/DEVTO_PUBLISHING.md).

## License

[MIT](LICENSE)
