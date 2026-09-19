# Architecture

This document describes AgentHop's MVP design and its safety invariants. It is a
design guide, not a promise that every roadmap capability is implemented.

## System context

AgentHop is a single-user local application with three major components:

```text
Browser (React)
      |
      | HTTP/JSON over loopback
      v
FastAPI API and application services
      |
      | provider-neutral calls
      v
Provider adapter registry
      |
      +---- Codex adapter ---- CLI, app-server, filesystem, SQLite
      +---- future adapters -- not yet implemented
```

### Frontend

The frontend is a presentation layer. It displays provider and profile names,
active state, sanitized status, usage summaries, recommendations, recent sessions,
and operation errors. It must not receive or persist provider credentials. New and
resume actions show a copyable command; the browser does not host a CLI terminal.
It normalizes integer epoch timestamps expressed in seconds or milliseconds and
renders them in the user's local timezone.

### Backend

The backend owns input validation, adapter lookup, error mapping, and local
process orchestration. Routes should remain thin: provider behavior belongs in
adapters or application services, not endpoint functions.

### Provider adapters

An adapter translates a provider's local model into AgentHop's common concepts.
It owns discovery, status, selection, usage, command preparation, and any migration
required to maintain session continuity. See [Provider adapters](PROVIDER_ADAPTERS.md).

## Core domain concepts

- **Provider**: an AI CLI integration, such as Codex.
- **Profile**: a named local identity/configuration home for a provider.
- **Active profile**: the profile selected for subsequent provider operations.
- **Credential state**: authentication material that must remain isolated.
- **Continuity state**: session data and discovery metadata intended to remain
  available after a profile switch.
- **Capability**: optional behavior such as usage reporting or session migration.

Unknown and unsupported are first-class states. They are not equivalent to zero,
unlimited, logged out, or failed.

## Codex storage model

OpenAI documents `CODEX_HOME` and Codex authentication behavior in the official
[environment-variable reference](https://developers.openai.com/codex/config-file/environment-variables)
and [authentication guide](https://developers.openai.com/codex/auth). AgentHop
uses a per-profile Codex home to select identity, but treats continuity data
separately.

```text
~/.codex/                         canonical/shared home
├── sessions/                    shared continuity
├── archived_sessions/           shared continuity
├── shell_snapshots/             shared continuity
├── thread-writer-locks/         shared continuity
└── state_5.sqlite               shared discovery metadata used by the MVP

~/.codex-profiles/<profile>/     isolated profile home
├── auth.json                    isolated when file storage is used
├── config.toml                  profile-scoped configuration
└── sessions -> ~/.codex/sessions
```

Names and layouts are compatibility-sensitive details contained by the Codex
adapter. Not every authentication setup has an `auth.json`: Codex can use an OS
credential store. AgentHop must not infer authentication solely from file
presence.

## Selection and command flow

1. The frontend requests sanitized provider/profile state.
2. The user chooses a profile.
3. The API validates the provider and profile identifier.
4. The adapter verifies the profile is usable.
5. The active marker is replaced atomically with restrictive permissions.
6. A new/resume action asks the adapter for a command using the selected profile
   home and shared continuity location.
7. The Codex adapter prepares shared state before returning a command. The first
   command request is the migration boundary for existing profile continuity;
   ordinary state/session reads remain non-mutating.
8. The API returns the quoted command; the dashboard lets the user copy it and
   run it in a terminal.

The current Codex adapter emits a POSIX shell command. Account and session IDs are
strictly validated, and every path/value is shell-quoted. Future direct execution
should use an argument array and explicit environment rather than a shell.

## Migration flow

Migration converts independently isolated homes into isolated identity plus
shared continuity.

```text
discover -> validate -> merge files -> link shared paths -> backfill index
              |             |                |                 |
              +---- preserve data; fail on unsafe state ------+
```

### File merge invariants

- Source and destination paths are derived from validated names under known
  roots.
- Unexpected symlinks are rejected.
- Missing destination files may be copied.
- Existing identical files are accepted.
- Existing different files are both preserved: the incoming file gets a
  deterministic `.agenthop-conflict-<hash>` suffix.
- A source directory is replaced only after its merge succeeds.
- Sensitive roots and markers use user-only permissions where the platform
  supports POSIX modes.

Migration should be repeatable after success. If a multi-step operation fails,
the original state should remain available or a clear recovery artifact should
be retained.

### SQLite index reconciliation

Session rollouts and their discovery index are one consistency boundary. The
backfill algorithm should:

1. open the profile and shared databases with bounded lock waits;
2. inspect the source and destination thread schemas;
3. operate only on a known table with required identity and rollout-path fields;
4. select the intersection of compatible columns;
5. rewrite rollout paths under the old profile home to the shared home;
6. insert missing thread rows;
7. update conflicts only when there is a defensible freshness comparison; and
8. roll back and surface an actionable error on failure.

The adapter must not guess through an unknown schema. A Codex upgrade can change
internal storage; compatibility failures should reduce functionality safely.

## App-server boundary

The official [Codex app-server documentation](https://developers.openai.com/codex/app-server)
describes a bidirectional JSON-RPC API for clients. The Codex adapter may use it
for supported account or usage information. App-server communication belongs in
the adapter and should include:

- subprocess timeouts and cleanup;
- request/response correlation;
- bounded output parsing;
- sanitized errors;
- graceful handling of missing fields and unsupported methods; and
- no logging of raw secret-bearing responses.

The common API must not expose app-server wire objects directly.

## Concurrency

State switching and migration can race with provider processes or other AgentHop
requests. Active selection uses atomic filesystem replacement. Each Codex adapter
uses an in-process lock to serialize migration triggered by concurrent command
requests. This is not an inter-process lock: run one backend instance per state
root and stop Codex before the first migration.

SQLite writes use transactions and bounded timeouts. A locked database produces
an error; it must not trigger deletion, recreation, or an unbounded wait.

## API design rules

- Return stable, provider-neutral models where possible.
- Include provider-specific detail only in a namespaced, sanitized structure.
- Use explicit status values rather than overloaded nulls when practical.
- Treat mutating requests as non-idempotent unless the operation defines
  otherwise.
- Map validation, conflict, unavailable-provider, and internal failures to
  distinct responses.
- Do not include absolute secret paths or credential contents in responses.

The generated OpenAPI document from the running backend is the authoritative
route and schema reference for the current build.

### Implemented routes

| Method | Route | Result |
| --- | --- | --- |
| `GET` | `/api/health` | Service health and version |
| `GET` | `/api/state` | Providers, cached account status, sessions, recommendation |
| `POST` | `/api/refresh` | Same state shape with live adapter refresh |
| `POST` | `/api/providers/{provider}/accounts/{account}/activate` | Active selection |
| `POST` | `/api/providers/{provider}/accounts/{account}/command` | Quoted new/resume command |

Response models use camel-case aliases for compound JSON fields. The command body
accepts `mode` (`new` or `resume`) and optional `sessionId` for resume.

## Trust boundaries and non-goals

The browser and backend are separate trust zones even on one machine. The Vite
development server proxies relative `/api` requests to `127.0.0.1:8000`. FastAPI
allows CORS only for HTTP(S) origins on `localhost`, `127.0.0.1`, and `[::1]`, and
an additional middleware rejects any other supplied `Origin`. Trusted-host
middleware accepts only those loopback hostnames (plus the test host). Requests
without `Origin` remain possible for local non-browser clients, so these controls
are not authentication and do not stop malicious software running as the user.

`npm run build` produces `frontend/dist`, but the FastAPI application does not
serve it. A production-like local server must serve those static assets and proxy
`/api` to FastAPI. Bundled production serving and remote deployment are not MVP
features.

The MVP is not:

- a multi-user service;
- a remote account gateway;
- a secret manager;
- a provider-limit bypass;
- a replacement for backups; or
- a guarantee of compatibility with undocumented provider internals.

See [Security](SECURITY.md) for the threat model and operational guidance.
