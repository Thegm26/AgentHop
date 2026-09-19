---
title: "AgentHop: switch AI coding accounts without losing your context"
published: false
description: "A local-first dashboard that separates AI CLI identity from resumable work, so switching accounts does not mean starting over."
tags: opensource, react, python, productivity
cover_image: "https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/agenthop-devto-cover.png"
---

# AgentHop: switch AI coding accounts without losing your context

*You should be able to change the account making the next request without throwing away the context that got you here.*

That is the small, stubborn problem behind [AgentHop](https://github.com/Thegm26/AgentHop): a local-first dashboard for managing AI coding CLI accounts while keeping resumable work close at hand.

It began with a script that did exactly one thing well: switch an AI coding CLI between isolated account directories. Then came the awkward moment: after a switch, `resume` could no longer find the conversation containing the current task, trade-offs, and unfinished work.

The login had changed correctly. The memory had changed with it.

AgentHop is the MVP I wanted instead: see locally available accounts, their sanitized usage state and reset times, choose a usable one, and prepare the next Codex command without treating an account change as a new project.

> **Independent project:** AgentHop is unofficial, local software. It is not affiliated with, endorsed by, or supported by OpenAI. It does not create accounts, bypass limits, or expose credentials to the browser.

## The problem is not account switching. It is state coupling.

Most quick account switchers point a CLI at a different home directory. That works for isolated credentials, but a home directory often contains much more: configuration, transcripts, archived sessions, SQLite indexes, locks, and snapshots. Change the whole directory and you may change all of those at once.

In short: the selected account fans out to two places—an isolated credential home and one shared continuity home—before Codex starts.

![Diagram: the selected account provides isolated credentials and shared continuity state to the Codex CLI.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/identity-continuity-diagram.png)

The central design decision is deliberately simple:

- **Identity is isolated.** Each account has its own local profile home.
- **Continuity is shared.** Resumable session state lives in a canonical shared location defined by the provider adapter.
- **The provider owns provider details.** The dashboard should not need to know how a particular CLI stores credentials, models usage, or indexes threads.

This is the difference between "switch who is making the next request" and "switch into a separate universe with no history."

## What the MVP does today

AgentHop currently ships with an OpenAI Codex adapter and a local React + FastAPI control surface. It can:

- discover the default and named local profiles;
- show account state as **ready**, **close**, or **blocked**, rather than hiding two limits behind one misleading percentage;
- show human-readable 5-hour and weekly reset times;
- mute blocked accounts and order them by when they are expected to become usable; and
- create a new isolated profile, guide the user through the normal terminal sign-in, select an account, and prepare a new or resume command.

The ordering is intentional. Accounts that can be used now appear first. If an account is blocked by more than one window, its expected-unblock time is the later reset: every exhausted window must clear before it is genuinely usable.

The practical sequence is refresh, choose a usable account, reconcile shared state when required, then copy the next command.

![Diagram: refresh account state, choose a usable account, reconcile continuity when needed, then copy a new or resume command.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/account-flow-diagram.png)

The browser sees sanitized profile names, status, reset information, and command results. It never needs the contents of an authentication file.

## The migration lesson: a transcript file is not a session list

The first continuity experiment was deceptively close. Shared transcript files existed on disk, yet the CLI's resume picker did not show every conversation.

The missing piece was discovery metadata. A SQLite index still pointed at an old profile-specific path. Copying a JSONL rollout preserved the content but did not teach the index where to look.

That led to a useful rule for any CLI integration:

> Durable data and the metadata used to discover it are one consistency boundary.

AgentHop treats migration as a cautious reconciliation step, not a blind copy:

The safe path is: stop active sessions, back up, preserve both sides of any conflict, refresh discoverability metadata, then launch.

![Diagram: stop and back up first, reconcile state without overwriting conflicts, backfill the session index, then launch with shared continuity.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/migration-diagram.png)

The adapter inspects database schemas rather than assuming one fixed layout, rewrites known rollout paths to the shared location, and prefers preservation over overwrite. The first prepared new/resume command is the migration boundary; opening the dashboard alone does not rewrite local state.

That behavior is intentionally conservative. Before migrating real profiles, back them up and stop active Codex processes.

## A small architecture that leaves room to grow

AgentHop is not "provider-neutral" because it has a generic dropdown. Different CLIs have different credential stores, session models, supported status interfaces, and safe launch semantics. The shared core stays small so adapters can own those facts.

| Layer | Responsibility |
| --- | --- |
| React dashboard | Local control surface; renders sanitized state and starts bounded actions. |
| FastAPI backend | Validates input, owns the local API boundary, selects adapters, and returns safe results. |
| Provider adapter | Discovers profiles, reads supported status, prepares commands, and owns migration behavior. |

For Codex, AgentHop builds on documented `CODEX_HOME`, authentication, and app-server interfaces. The browser does not host an interactive CLI. It gives you a quoted command to review and run in your own terminal.

## Try it locally

You need Python 3.11+, Node.js 18.19+ (Node 20+ recommended), npm, and the Codex CLI on your `PATH`.

```bash
git clone https://github.com/Thegm26/AgentHop.git
cd AgentHop

python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
agenthop --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:8080`. Click **Add account**, choose a local profile name, copy the displayed sign-in command, and complete the normal provider login in your browser. Then return to AgentHop and choose **Refresh usage**.

For the full setup, API, and security notes, see the [README](https://github.com/Thegm26/AgentHop#readme).

## What this is—and what it is not

This is a local, single-user MVP. It is deliberately narrow:

- It does not bypass provider limits or automate account creation.
- It does not send passwords or tokens to the dashboard.
- It is not intended for remote or multi-user deployment without authentication, authorization, CSRF protections, TLS, and a fuller threat model.
- It does not claim every future provider is supported; Codex is the first working adapter.

Local-only is a product decision as much as a security decision. The backend binds to loopback by default, validates local hosts and browser origins, keeps profile paths constrained to known roots, and avoids committing auth files, databases, and session rollouts. Those checks are helpful boundaries, not a substitute for real authentication on a networked service.

## The part I would love feedback on

The technical question is broader than Codex: where should a developer tool draw the boundary between identity, continuity, and provider-specific state?

If you manage multiple AI coding CLI profiles, I would especially value feedback on:

- the status model—what would make a "switch now vs. wait" decision clearer;
- session migrations—what failure modes deserve more guardrails; and
- the next provider adapter worth supporting.

If this sounds useful, please [star the repository](https://github.com/Thegm26/AgentHop), open an issue, or contribute an adapter design. The project is early, but the principle feels durable: switching accounts should not mean losing the thread.

---

### Disclosure

This post and project documentation were drafted with AI assistance and reviewed by the project author. The implementation, product decisions, and final claims should be evaluated against the repository and its documentation.
