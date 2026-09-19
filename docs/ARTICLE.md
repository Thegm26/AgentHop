# AgentHop: switching accounts without switching away from your work

There is a particular kind of failure that looks like success.

You build a small script to switch between accounts for an AI coding CLI. It
does exactly what you asked: each account gets its own directory, each directory
gets its own authentication, and launching the CLI with a different environment
selects the right account. Then you try to resume yesterday's conversation.
Nothing is there.

The work was not necessarily deleted. The new account is simply looking through
a different window.

AgentHop grew out of that problem. It is a local dashboard and a provider-neutral
architecture for switching AI CLI identities while preserving the context that
should survive an account change. Codex is the first working adapter, but the
central idea is broader: **identity and continuity are different kinds of
state**. They deserve different lifecycles.

AgentHop is an independent, unofficial project and is not affiliated with or
endorsed by OpenAI.

## What we wanted

At the human level, the goal was straightforward. When one account is unavailable
or unsuitable for the next piece of work, choose another account and continue.
Do not copy secrets around. Do not hunt through dated JSONL files. Do not lose the
conversation that explains the repository, decisions, and incomplete task.

At the engineering level, that becomes a stricter set of requirements:

1. Each account's credentials must remain isolated.
2. Switching must be explicit, inspectable, and local.
3. Conversations intended to be resumable must be visible across profiles.
4. Existing profiles must migrate without silent overwrite or data loss.
5. The user interface must not need to read or return secrets.
6. Codex-specific behavior must not leak into every layer of the application.

The last point matters. “Support more providers later” is easy to write and hard
to earn. Provider neutrality is not a generic logo in a dropdown. Different CLIs
store credentials differently, define a session differently, expose usage through
different interfaces, and have different safe ways to launch. A credible shared
core has to let an adapter own those facts.

## Why the first account switcher broke resume

Codex uses `CODEX_HOME` as its home for local Codex data. That makes it a useful
lever for isolation: run one process with one home, another process with another,
and their credentials can live apart. OpenAI documents the Codex configuration
environment, authentication choices, and app-server protocol in its official
[environment-variable reference](https://developers.openai.com/codex/config-file/environment-variables),
[authentication guide](https://developers.openai.com/codex/auth), and [app-server
documentation](https://developers.openai.com/codex/app-server).

But a home directory is a storage boundary, not an authentication boundary. If a
profile home contains both credentials and session history, changing the whole
home changes both at once:

```text
Profile A home                 Profile B home
├── auth.json                  ├── auth.json
├── sessions/                  ├── sessions/
├── archived_sessions/         ├── archived_sessions/
└── state SQLite               └── state SQLite
```

This is internally consistent. Profile B's resume command sees profile B's
history. It is just inconsistent with the user's intent, which was “change who is
making the next request” rather than “enter a new universe with no memory.”

The initial mental model was one variable, one concern. The real model was one
variable controlling several concerns.

## The split: isolated credentials, shared continuity

AgentHop's Codex adapter introduces a deliberate split.

Per-profile homes retain identity-sensitive material: authentication and any
configuration that must follow that identity. A canonical shared home owns the
continuity material: active and archived session rollouts, shell snapshots,
writer locks, and the session index used for discovery. Profile session paths can
then resolve to the common store while the process still receives the selected
credential home.

```text
                    selected account
                          |
          +---------------+---------------+
          |                               |
          v                               v
  isolated profile home            shared state home
  - credentials                    - sessions
  - account config                 - archived sessions
                                   - snapshots and locks
                                   - thread index
```

The exact mechanisms are adapter details. The invariant is the important part:
selecting identity must not accidentally select a disconnected history.

This split also improves the user interface. The dashboard needs profile names,
status, perhaps sanitized plan or usage values, and the result of a switch. It
does not need token values or the contents of `auth.json`. Secrets stay below the
API boundary.

## The SQLite lesson: files are not discovery

The most useful lesson arrived after shared session directories appeared to work.
Old conversation files were present in the common location, but the resume picker
still did not list every conversation.

The reason was stale metadata. A SQLite database indexed threads and recorded
where their rollout files lived. Copying a JSONL rollout preserved the transcript
but did not teach the shared index about it. Worse, a copied row could still point
to the old profile-specific path.

This is a recurring systems lesson: **durable data and discoverability metadata
form a consistency boundary**. A migration is incomplete until both agree.

The backfill strategy follows a few conservative rules:

- inspect schemas instead of assuming every installed version is identical;
- copy only columns shared by the source and destination tables;
- require the identity and rollout-path columns before attempting a merge;
- rewrite rollout paths from a profile home to the canonical shared home;
- upsert by thread identity, preferring newer metadata when a comparable update
  field exists; and
- fail visibly on database errors rather than pretending the migration succeeded.

This is not glamorous code, but it is the difference between “the files are
somewhere” and “the product works.”

It also argues for a narrow compatibility layer. SQLite tables are an internal
implementation detail of the CLI and may evolve. The adapter should contain that
risk, tests should use representative schemas, and unknown layouts should result
in a safe refusal or reduced capability—not speculative mutation.

## Migration without casual data loss

Combining previously separate homes creates the possibility of collisions. Two
profiles can contain the same relative path with different bytes. Treating one as
authoritative would be convenient and dangerous.

AgentHop's intended migration behavior is conservative:

1. Create shared directories with user-only permissions.
2. Walk each known state directory without following unexpected symlinks.
3. Copy files that do not exist at the destination.
4. Accept an existing file only when it is equivalent.
5. Preserve a conflicting file under a content-derived conflict name rather than
   overwriting either version.
6. Replace a migrated profile directory with a link to shared state only after
   its contents have been reconciled.
7. Reconcile the thread index and update rollout paths.

The first request to prepare a new or resumed command is the migration boundary.
Merely opening the dashboard does not rewrite user state.
Within one backend process, a lock serializes migrations so two command requests
cannot merge the same homes concurrently. That lock cannot coordinate another
AgentHop process or a running Codex process, which is why the operational advice
remains simple: run one backend and stop Codex before the first migration.

When two different rollouts occupy the same relative path, the incoming file is
stored with a short content-hash suffix. The SQLite backfill records that actual
conflict path, so preserving both copies does not leave the imported thread
pointing at the wrong transcript.

The principle is stronger than any single implementation: migration should be
idempotent where practical, explicit when it cannot be, and biased toward
preserving evidence. A dashboard can make this approachable, but it must not make
dangerous operations look harmless.

## Architecture: a small core and honest adapters

AgentHop uses three layers.

The React frontend is a local control surface. It presents sanitized profile
state, makes the active selection visible, and initiates bounded operations. It
does not parse provider files and should never receive credential contents.

The FastAPI backend is the application boundary. It validates input, selects an
adapter, serializes results, and maps known failures to useful responses. It is
also the security boundary for the browser: local-only defaults and no
secret-bearing payloads. In development, Vite proxies relative `/api` requests.
The API restricts accepted Host values to loopback names, permits CORS only for
loopback HTTP(S) origins, and explicitly rejects other supplied Origin headers.
That still is not authentication: local non-browser clients can omit Origin.

Provider adapters own everything that varies by CLI: discovery, authentication
status, usage inspection, state classification, migration, switching, and command
preparation. The Codex adapter can use documented surfaces such as the official
app server, whose JSON-RPC protocol is intended for rich clients, without making
the rest of AgentHop speak Codex. The MVP returns a quoted command for the user to
copy and run; it does not host the interactive CLI process in the browser.

That separation creates a useful rule for future integrations: an adapter is not
complete because it can change a token. It is complete when it documents and
tests the provider's identity boundary, continuity boundary, launch semantics,
and failure behavior.

## Safeguards that matter

AgentHop is local software, but local does not mean harmless. It sits near bearer
credentials and conversation history, both of which can be sensitive.

The MVP's security posture rests on restraint:

- bind the development service to loopback;
- never include credential contents in API models, UI state, logs, or errors;
- derive profile paths from strict names and known roots;
- strictly validate identifiers and quote every value placed in generated shell
  commands;
- create sensitive directories and markers with user-only permissions;
- make selection updates atomically;
- reject unexpected links and preserve collisions under distinct names during
  migration;
- serialize migrations inside one backend process;
- restrict Host and browser Origin values to loopback addresses; and
- keep `auth.json`, databases, profiles, and session data out of version control.

The official Codex authentication documentation notes that credentials may be
stored in a local file or an operating-system credential store depending on
configuration. AgentHop must handle the absence of a readable `auth.json` as a
valid possibility; “no file” does not automatically mean “logged out.” Provider
supported status interfaces are safer than inspecting secret files whenever they
are available.

The MVP is not intended to be exposed to a network or shared among multiple OS
users. Those deployments require authentication, authorization, CSRF analysis,
TLS, audit controls, and a more formal threat model.

The dashboard also refuses to make every visible account look actionable. It
disables switch/start controls for unauthenticated, duplicate, provider-disallowed,
or blocked accounts, and prevents overlapping account actions while a refresh or
operation is in flight. The API still supports resume command preparation, while
the dashboard focuses on account status and does not expose conversation titles.
Reset times arrive as integer epochs; the UI handles seconds and milliseconds
and displays the time remaining.

## What the dashboard changes—and what it does not

A dashboard helps because invisible state becomes visible. The selected profile,
provider status, recommendation inputs, and errors can be shown before the next
launch. This reduces the chance that an environment variable set in a forgotten
shell silently controls an important process.

It does not change provider rules. AgentHop does not create accounts, bypass
limits, manufacture capacity, or guarantee that an undocumented provider surface
will remain stable. Usage figures can be missing, stale, or change semantics.
Unknown data should be shown as unknown.

It also does not eliminate backups. Any first migration of real developer state
deserves a backup and a quiet moment with active CLI processes stopped.

## Where this can go

The immediate work is deliberately practical: make the Codex path reliable,
observable, recoverable, and easy to install. Dry-run migration previews,
structured audit output, and compatibility tests are more valuable than quickly
adding a dozen shallow adapters.

After the adapter contract proves itself, another provider can be added by
answering concrete questions:

- How is identity selected?
- Where and how are credentials stored?
- Which state should follow the person, project, account, or machine?
- How are resumable sessions discovered?
- Is there a supported local API or only a CLI?
- What operations are safe to automate?
- How does the adapter degrade when a capability is unavailable?

That is provider neutrality as engineering discipline, not branding.

Today, provider neutrality means a stable interface, shared domain models, a
registry, and failure isolation so one adapter does not erase another provider's
state from the response. It does not mean providers can be installed dynamically:
the shipped registry contains only Codex, and another adapter still requires code,
tests, registration, and documentation.

## The broader lesson

Configuration directories often accumulate responsibilities over time. They
begin as a place for a token, then gain preferences, caches, histories, indexes,
locks, and snapshots. Using the directory as the unit of account isolation feels
natural until users want some of those things to remain continuous.

AgentHop's core insight is small: isolate the secret, share the work, and make the
boundary explicit. The hard part is honoring that sentence through migrations,
metadata, API design, permissions, and honest failure modes.

When it works, switching accounts becomes boring. That is exactly the goal.
