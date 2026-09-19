---
title: "I built AgentHop because switching Codex accounts kept breaking my flow"
published: false
description: "The story of a local-first dashboard that makes multiple Codex CLI accounts visible while keeping resumable work continuous."
tags: opensource, react, python, productivity
cover_image: "https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/agenthop-devto-cover.png"
---

# I built AgentHop because switching Codex accounts kept breaking my flow

*Changing the local profile for a request should be easy. The context that got you here should not disappear with it.*

I use separate, legitimate Codex profiles for distinct contexts: personal work, a client workspace, and experiments that should not inherit the same local setup. Keeping those contexts separate is useful; repeatedly navigating between them was not. Each time I needed a different profile, I would log out, change the active setup, reload Codex, and authenticate again.

That routine was repetitive, slow, and disruptive. Worse, it pulled me out of the task just to answer ordinary operational questions: *which profile is selected? Is it signed in? What status did Codex last report?*

## First, I made switching less painful

My first answer was a small CLI script. It gave each context an isolated local profile and made the normal sign-out/re-auth cycle unnecessary for routine switching. That solved the most visible friction: I could select the identity and configuration used by the CLI without redoing the entire setup.

But it only made the switch faster. It did not make the decision easier.

When you are deep in work, a list of profile names is not enough. I still could not quickly see which profile was signed in, which one Codex reported as ready, close, or blocked, and when a reported reset would occur. I could ask the CLI for status, but checking several isolated profiles by hand was still manual and easy to get wrong.

![Terminal showing AgentHop's CLI profile-status output for several local Codex profiles, including their active state and reset information.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/agenthop-cli-profile-status.gif)

*AgentHop's CLI makes each local profile's current status visible at a glance.*

So the script became a dashboard. AgentHop reads the local, supported status for each profile and turns it into a small operational view: **ready**, **close**, or **blocked**, plus readable reset times. Profiles that are currently usable appear first; a blocked profile remains muted until the provider reports it as usable again.

That was the first payoff. Instead of bouncing between profile directories and terminal output, I could refresh once and see the current local picture. But a dashboard still asks you to open a dashboard. For a check that happens several times in a day, that is one window too many.

## The control surface moved to the tray

Now AgentHop starts quietly in the Linux system tray. Clicking its icon gives me
the short list I actually need: the active profile, a suggested available
profile when one is reported, then profiles grouped by current status. A blocked
profile stays muted; an enabled entry can be clicked to switch directly. The
full dashboard is still there for onboarding, inspecting status, or preparing a
new command, but it is no longer a mandatory stop between work and the profile
I need.

That distinction matters to me. The tray is for the frequent, low-friction
question—*which profile do I need right now?* The dashboard is for the less
frequent, higher-context tasks—*add an identity, inspect the details, or start a
new session.*

![AgentHop workflow moving from CLI profile status to the Linux tray menu and then the dashboard, where an enabled profile can be selected.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/agenthop-cli-to-tray-dashboard-workflow.gif)

*From CLI status to a tray action and the full dashboard without losing the operational context.*

## Then I found the problem that mattered more

The first time I switched profiles and tried to continue a real task, I expected to run `resume` and pick up the conversation. Instead, the resume list looked empty.

The account switch had worked. My working memory had not followed me.

That discovery changed the project. The local profile directory was doing two jobs at once: it held account-specific identity, but it also held the transcripts, indexes, snapshots, and other state that made a session discoverable. Pointing `CODEX_HOME` at a new profile did not just choose a different account; it could make the CLI look at a different history.

The actual product question became more interesting: how do you keep identity isolated without turning every account switch into a separate universe?

[AgentHop](https://github.com/Thegm26/AgentHop) is the MVP that came out of that question. It is a local-first dashboard for managing AI coding CLI profiles while keeping resumable work close at hand. It separates profile identity from continuity, shows the status Codex makes available, and prepares the next Codex command without treating a profile change as a new project.

> **Independent project:** AgentHop is unofficial, local software. It is not affiliated with, endorsed by, or supported by OpenAI. It does not create accounts, combine subscriptions, bypass limits, or expose credentials to the browser. It does not decide whether any account setup or use complies with provider policy.

Use only accounts you are authorized to use and follow the provider's terms. For
OpenAI services, see the current [Terms of Use](https://openai.com/policies/terms-of-use/)
and [account-switching help](https://help.openai.com/en/articles/20001068).

## The architecture: identity is not continuity

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
- show profile state as **ready**, **close**, or **blocked**, rather than hiding two independent status windows behind one percentage;
- show human-readable 5-hour and weekly reset times when the provider supplies them;
- mute profiles the provider reports as blocked and group profiles by their current status; and
- create a new isolated profile, guide the user through the normal terminal sign-in, select a profile, and prepare a new or resume command.

The ordering is operational, not a policy judgment. Profiles reported as usable appear first. When a profile has more than one blocked window, AgentHop presents the later reset as its expected unblock time because that is the latest status change it can show.

The practical sequence is refresh, choose the profile appropriate for the work, reconcile shared state when required, then copy the next command.

![Diagram: refresh profile status, choose the appropriate profile, reconcile continuity when needed, then copy a new or resume command.](https://raw.githubusercontent.com/Thegm26/AgentHop/main/docs/assets/account-flow-diagram.png)

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

python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
./scripts/desktop.sh
```

That starts AgentHop in the local Linux system tray; it does not open a window.
Click the icon to refresh and select an enabled profile directly. Choose
**Open dashboard…** when you need the full view, or run the launcher again to
reveal the existing dashboard. The launcher builds the React UI when needed and
keeps the backend on loopback.

For frontend development, use another terminal:

```bash
cd frontend
npm install
npm run dev
```

Click **Add account**, choose a local profile name, copy the displayed sign-in
command, and complete the normal provider login in your browser. Then return to
AgentHop and choose **Refresh usage**. The app deliberately shows new-session
commands for review rather than executing a shell for you.

For the full setup, API, and security notes, see the [README](https://github.com/Thegm26/AgentHop#readme).

## What this is—and what it is not

This is a local, single-user MVP. It is deliberately narrow:

- It does not create accounts, combine subscriptions, bypass provider limits, or determine policy compliance.
- It does not send passwords or tokens to the dashboard.
- It is not intended for remote or multi-user deployment without authentication, authorization, CSRF protections, TLS, and a fuller threat model.
- It does not claim every future provider is supported; Codex is the first working adapter.

Local-only is a product decision as much as a security decision. The backend binds to loopback by default, validates local hosts and browser origins, keeps profile paths constrained to known roots, and avoids committing auth files, databases, and session rollouts. Those checks are helpful boundaries, not a substitute for real authentication on a networked service.

## The part I would love feedback on

The technical question is broader than Codex: where should a developer tool draw the boundary between identity, continuity, and provider-specific state?

If you manage multiple AI coding CLI profiles, I would especially value feedback on:

- the status model—what would make local profile status clearer;
- session migrations—what failure modes deserve more guardrails; and
- the next provider adapter worth supporting.

If this sounds useful, please [star the repository](https://github.com/Thegm26/AgentHop), open an issue, or contribute an adapter design. The project is early, but the principle feels durable: switching accounts should not mean losing the thread.

---

### Disclosure

This post and project documentation were drafted with AI assistance and reviewed by the project author. The implementation, product decisions, and final claims should be evaluated against the repository and its documentation.
