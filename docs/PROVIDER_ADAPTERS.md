# Provider adapters

AgentHop keeps its UI and HTTP API provider-neutral by placing CLI-specific logic
behind adapters. Codex is the first working adapter. Other providers are roadmap
work until an adapter is implemented, tested, and documented.

## Responsibilities

An adapter owns the provider-specific answer to each of these questions:

| Area | Adapter responsibility |
| --- | --- |
| Availability | Locate the executable and report availability/status |
| Discovery | Find valid local profiles under explicitly allowed roots |
| Identity | Determine authentication status without returning secrets |
| Selection | Persist the active profile atomically |
| Usage | Obtain and normalize provider status information without treating unknown as available |
| Profile suggestion | Supply comparable inputs for a local suggested-profile display |
| Command | Prepare a strictly validated, safely quoted user-facing command |
| Continuity | Identify session files, indexes, locks, and snapshots |
| Migration | Reconcile continuity state safely and repeatably |
| Diagnostics | Return sanitized, actionable failures |

The core decides how common data is serialized and presented. It must not contain
conditionals for a provider's filenames, database schema, or command flags.

## Capability evolution

The current abstract adapter has one compact required contract. A future explicit
capability model could distinguish features such as:

- profile discovery;
- authentication status;
- usage reporting;
- active-profile selection;
- continuity migration; and
- managed command preparation.

Unsupported capability and temporary failure are different states. For example,
a provider that has no usage API is `unsupported`; a normally available API that
times out is `unavailable`. The UI should not present either as zero usage.

## Implemented interface

The MVP Python contract is:

```python
class ProviderAdapter(Protocol):
    id: str
    name: str

    def provider(self) -> ProviderModel: ...
    def accounts(self, *, refresh: bool = False) -> list[AccountModel]: ...
    def sessions(self) -> list[SessionModel]: ...
    def activate(self, account: str) -> None: ...
    def command(
        self, account: str, mode: str, session_id: str | None = None
    ) -> str: ...
```

Use domain models rather than provider response dictionaries. `command` currently
returns a POSIX shell command shown to the user; inputs must be strictly validated
and each interpolated value shell-quoted. If AgentHop later executes commands
directly, the contract should return an argument array and environment map instead.

## Security contract

Every adapter must document its credential and continuity boundaries before it
is accepted.

An adapter must:

- constrain profile identifiers to a strict, short character set;
- resolve filesystem paths under configured roots;
- reject traversal and unexpected symlinks;
- never return credential values through domain models;
- never log tokens, authorization headers, or credential-file contents;
- never execute generated command text in the backend;
- strictly validate identifiers and shell-quote every generated-command value;
- use timeouts for child processes and local RPC;
- fail closed on ambiguous migration state; and
- describe any destructive or irreversible operation explicitly.

Do not add a provider by copying credentials between profile homes. That is not
account isolation.

## Continuity contract

Before implementation, classify every relevant provider artifact:

| Classification | Meaning | Typical handling |
| --- | --- | --- |
| Credential | Selects or authorizes an identity | Keep per profile |
| Profile config | Intentionally follows an identity | Usually per profile |
| Session rollout | Conversation/event history | Share if cross-profile resume is intended |
| Discovery index | Makes sessions visible | Share or reconcile with rollouts |
| Ephemeral lock | Coordinates writers | Share only with the state it protects |
| Cache | Rebuildable acceleration | Prefer rebuild over risky migration |
| Unknown | Semantics not established | Leave untouched |

Sharing rollout files without their index is not a complete migration. Sharing a
lock directory without the protected data can be actively wrong. The adapter
must define these relationships as a unit.

## Codex adapter notes

Codex supports configuration through `CODEX_HOME`; see OpenAI's official
[environment-variable documentation](https://developers.openai.com/codex/config-file/environment-variables).
Authentication may use file or OS credential storage, as described in the
[authentication guide](https://developers.openai.com/codex/auth). A missing local
credential file therefore does not conclusively mean that a profile is logged
out.

The [Codex app server](https://developers.openai.com/codex/app-server) offers a
JSON-RPC surface intended for rich clients. AgentHop should prefer supported
provider interfaces for status data and contain protocol parsing within the
adapter.

Codex continuity migration must account for both rollout directories and the
SQLite thread index. Because the database is an internal compatibility surface,
schema inspection and safe degradation are mandatory.

## Adding an adapter

1. Write a short state map covering credentials, configuration, sessions,
   indexes, locks, and caches.
2. List the supported provider documentation and any unavoidable undocumented
   surface.
3. Implement the smallest useful capability set.
4. Register it without changing existing provider code paths.
5. Add unit tests using temporary homes and fake subprocess/RPC responses.
6. Add migration tests for empty, populated, repeated, conflicting, linked, and
   incompatible-schema cases.
7. Add contract tests confirming no API model includes secrets.
8. Document platform support and recovery steps.

An adapter is ready when its failure modes are understandable, not merely when
the happy path works once.
