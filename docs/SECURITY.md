# Security model

AgentHop runs locally but operates near authentication material and conversation
history. Treat both as sensitive.

For vulnerability reporting, see the repository-level [security
policy](../SECURITY.md).

## Deployment assumptions

The MVP assumes:

- one trusted OS user;
- one AgentHop backend process;
- HTTP bound to loopback;
- a trusted local frontend origin; and
- provider profile roots owned by that user.

It is not designed for internet exposure, shared servers, containers with
untrusted tenants, or multiple mutually untrusted users.

## Provider-policy boundary

AgentHop manages local profile selection and continuity only. It does not create
accounts, combine or pool subscriptions, bypass provider restrictions, or make a
policy determination about an account setup or use. Operators are responsible
for using only accounts they are authorized to use and for following applicable
provider terms. For OpenAI services, review the [Terms of
Use](https://openai.com/policies/terms-of-use/) and [account-switching
help](https://help.openai.com/en/articles/20001068).

## Assets

- Provider credentials and refresh tokens.
- Conversation rollouts, which may contain source code, prompts, and command
  output.
- Profile configuration and account identifiers.
- SQLite indexes and active-profile markers.
- The ability to launch a provider CLI under a selected identity.

## Primary threats

### Secret disclosure

A backend response, exception, debug log, browser state snapshot, or committed
file could expose credentials. API models must use allowlists, not serialization
of provider objects. Never read `auth.json` merely to show its contents or return
raw app-server responses.

### Path traversal and link attacks

User-controlled profile names could escape configured roots, while symlinks could
redirect migration into unrelated files. Validate identifiers, resolve and check
paths, and reject unexpected links.

### Command injection

Provider operations include subprocesses and user-facing command generation.
App-server processes use an argument array with an explicit environment. Generated
commands must accept only strictly validated identifiers and shell-quote every
path and value. The backend returns command text for the user to inspect; it does
not execute that text.

### Cross-origin requests

A malicious webpage may try to call a loopback service. The backend accepts only
loopback Host values, permits CORS only for HTTP(S) loopback origins, and rejects
other supplied Origin headers. Development requests pass through Vite's `/api`
proxy. In Linux desktop mode, the embedded WebKit view uses the same loopback
FastAPI origin. Local tools can omit Origin, so these controls are not
authentication.
Future non-loopback or privileged deployments require a real authentication and
CSRF design.

### Desktop control socket and tray process

The Linux desktop launcher keeps one background tray process and uses a Unix
socket only to ask that process to reveal its dashboard window. The runtime
directory, socket, and socket mode are checked to be owned by the current user
and inaccessible to group or other users; unexpected socket paths are rejected.
The message contains only the literal request to show the window, never an
account identifier, credential, command, or API response. The tray shell talks
to its FastAPI child only on `127.0.0.1` and URL-encodes provider/account path
segments before activation requests.

### Migration loss or corruption

Merging profile state can collide, race with a running CLI, or leave files and
metadata inconsistent. Stop active provider processes, back up first, serialize
mutations, use transactions and atomic replacement, and fail on ambiguous state.

## Required practices

- Bind to `127.0.0.1` by default.
- Run as a normal user, never root.
- Create sensitive directories and markers with user-only permissions.
- Never expose or log credential contents.
- Never commit `auth.json`, local databases, session rollouts, or profile homes.
- Redact absolute paths and provider payloads from user-facing errors where they
  reveal sensitive information.
- Bound subprocess execution and parse only expected output.
- Keep dependencies patched and review lockfile changes.
- Test migration against temporary directories, not live user state.

## Credential storage

Codex may store credentials in a file or an operating-system credential store;
see the official [authentication documentation](https://developers.openai.com/codex/auth).
AgentHop should use provider-supported status mechanisms when possible and must
not assume `auth.json` always exists.

If file-based storage is used, `auth.json` is a secret. Do not copy it into the
repository, attach it to bug reports, paste it into logs, or share it between
profiles. If exposed, revoke the relevant session or credential using the
provider's supported controls.

## Operational checklist

Before first migration:

1. Stop Codex and AgentHop processes.
2. Back up all affected homes to a user-readable private location.
3. Confirm the backend will bind only to loopback.
4. Review the selected roots and profiles.
5. Run a dry-run mode if the installed version provides one.

After migration:

1. Confirm credentials remain isolated.
2. Confirm old sessions appear and open correctly.
3. Inspect permissions on profile and shared-state roots.
4. Review logs for accidental sensitive output.
5. Keep the backup until normal resume and switching workflows are verified.

## Known limitations

- Local malware with the same user's permissions can generally read the same
  files as AgentHop.
- Loopback binding does not by itself authenticate browser requests.
- Provider internals may change independently of AgentHop.
- An in-process lock serializes migration in one backend instance; separate
  backend and Codex processes can still race.
- Usage information may be missing or stale and is not an authorization signal.
- Desktop mode serves the built frontend from the same loopback FastAPI origin.
  Its static-file and SPA fallback handling are part of the local security
  boundary; remote or multi-user hosting is out of scope.

## Dependency audit note

The frontend's pinned toolchain supports the project's Node 18.19 baseline. At
the time of this review, `npm audit --omit=dev` reports no runtime dependency
vulnerabilities, while a full audit reports two moderate development-only
findings through Vitest's mocker. npm proposes a breaking Vitest major upgrade;
that change should be evaluated together with a newer Node baseline rather than
forced automatically. Keep Vite local and reassess this exception regularly.

These limitations are reasons to keep the MVP local and single-user.
