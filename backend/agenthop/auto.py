"""Supervise an interactive Codex process and rotate only exhausted profiles."""
from __future__ import annotations

import argparse
import errno
import fcntl
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

from agenthop.models import AccountModel
from agenthop.providers.codex import CodexAdapter, SESSION_RE
from agenthop.service import AccountService

DEFAULT_CODEX_ARGS = (
    "-C",
    "/home/gm26",
    "--dangerously-bypass-approvals-and-sandbox",
    "--search",
    "--add-dir",
    "/tmp",
)
AUTO_LOCK_NAME = ".agenthop-auto.lock"
LOCK_TIMEOUT = 5.0
DEFAULT_REVIEW_DRAIN_GRACE = 45.0
MAX_REVIEW_DRAIN_GRACE = 120.0
REVIEW_QUEUE_TIMEOUT = 15.0
REVIEW_DRAIN_MESSAGE = (
    "Finish all active subagent and reviewer work now. Ask every running agent "
    "to stop starting new work, complete its current review, and return all "
    "findings before this session is rotated."
)


class SelectionInterrupted(Exception):
    """A stop request arrived while waiting for the shared selection lock."""


def known_resume_session(arguments: list[str]) -> str | None:
    """Return an explicitly requested root session, if the invocation has one."""
    try:
        index = arguments.index("resume")
        candidate = arguments[index + 1]
    except (ValueError, IndexError):
        return None
    return candidate if SESSION_RE.fullmatch(candidate) else None


def _descendants(pid: int) -> set[int]:
    """Return Linux descendants without relying on an external process tool."""
    parents: dict[int, list[int]] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8").rsplit(") ", 1
            )[1].split()
            parents.setdefault(int(fields[1]), []).append(int(entry.name))
        except (FileNotFoundError, IndexError, OSError, ValueError):
            continue
    found = {pid}
    pending = [pid]
    while pending:
        current = pending.pop()
        for child in parents.get(current, []):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def locate_root_session(pid: int, database: Path) -> str | None:
    """Match open rollout FDs to a CLI-root thread in Codex's shared index.

    The Codex process retains file descriptors for both root and subagent
    rollouts.  `threads.source == "cli"` is the durable discriminator; a JSON
    source denotes a subagent.  Ambiguity intentionally returns ``None``.
    """
    if not database.is_file() or database.is_symlink():
        return None
    open_paths: set[str] = set()
    for process_id in _descendants(pid):
        fd_root = Path("/proc") / str(process_id) / "fd"
        try:
            descriptors = list(fd_root.iterdir())
        except OSError:
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.endswith(" (deleted)"):
                target = target[: -len(" (deleted)")]
            if target.endswith(".jsonl"):
                open_paths.add(os.path.realpath(target))
    if not open_paths:
        return None
    try:
        uri = database.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=2) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
            if not {"id", "rollout_path", "source"}.issubset(columns):
                return None
            rows = connection.execute(
                "SELECT id, rollout_path, source FROM threads WHERE source = ?", ("cli",)
            ).fetchall()
    except sqlite3.Error:
        return None
    matches = {
        thread_id
        for thread_id, rollout_path, _source in rows
        if isinstance(thread_id, str)
        and SESSION_RE.fullmatch(thread_id)
        and isinstance(rollout_path, str)
        and os.path.realpath(rollout_path) in open_paths
    }
    return matches.pop() if len(matches) == 1 else None


class AutoSupervisor:
    """Own a Codex child process and restart it only with a proven root id."""

    def __init__(
        self,
        adapter: CodexAdapter,
        *,
        poll_interval: float = 30.0,
        continue_prompt: str = "continue",
        initial_arguments: list[str] | None = None,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        queue_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        sleep: Callable[[float], None] | None = None,
        review_drain_grace: float = DEFAULT_REVIEW_DRAIN_GRACE,
        stderr=None,
    ) -> None:
        self.adapter = adapter
        self.poll_interval = poll_interval
        self.continue_prompt = continue_prompt
        self.initial_arguments = initial_arguments or []
        self._popen = popen
        self._queue_runner = queue_runner
        self._sleep = sleep
        self.review_drain_grace = review_drain_grace
        self._wake = threading.Event()
        self._stderr = stderr or sys.stderr
        self.stop_requested = False
        self.automation_disabled = False
        self.root_session = known_resume_session(self.initial_arguments)
        self._review_drain_delivered = False
        self._review_drain_critical_attempted = False
        self._review_drain_final_attempted = False
        # This is the identity whose CODEX_HOME the owned child received.  The
        # shared .active marker remains a launch selector for other terminals,
        # never a source of truth for an already-running child.
        self.bound_account: str | None = None

    @staticmethod
    def _blocked(account: AccountModel) -> bool:
        return bool(account.usage and account.usage.status == "blocked")

    def _warn(self, message: str) -> None:
        print(f"agenthop auto: {message}", file=self._stderr)

    def _pause(self, seconds: float) -> None:
        if self._sleep is not None:
            self._sleep(seconds)
            return
        self._wake.wait(seconds)
        self._wake.clear()

    def _bound_usage(self) -> AccountModel:
        if self.bound_account is None:
            raise RuntimeError("supervisor has no bound Codex profile")
        return self.adapter.account(self.bound_account, refresh=True)

    @contextmanager
    def _selection_lock(self):
        """Take a bounded, interruptible private lock for profile selection."""
        root = self.adapter.profile_root
        if root.is_symlink():
            raise RuntimeError("Codex profile root must not be a symbolic link")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        lock_path = root / AUTO_LOCK_NAME
        if lock_path.is_symlink():
            raise RuntimeError("AgentHop auto lock must not be a symbolic link")
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise RuntimeError("AgentHop auto lock must not be a symbolic link") from exc
            raise
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != os.geteuid()
            ):
                raise RuntimeError("AgentHop auto lock must be a private regular file")
            os.fchmod(descriptor, 0o600)
            deadline = time.monotonic() + LOCK_TIMEOUT
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                    if self.stop_requested:
                        raise SelectionInterrupted
                    if time.monotonic() >= deadline:
                        raise TimeoutError("timed out waiting for AgentHop auto lock")
                    self._pause(0.1)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _recommendation(self) -> str | None:
        """Return a live recommendation under the same lock used for switching."""
        try:
            with self._selection_lock():
                return self._recommendation_locked()
        except (SelectionInterrupted, TimeoutError):
            return None

    def _recommendation_locked(self) -> str | None:
        """Full-refresh selection; caller owns the shared profile lock."""
        state = AccountService([self.adapter]).state(refresh=True)
        recommendation = state.recommendation
        if not recommendation or recommendation.provider != self.adapter.id:
            return None
        for account in state.accounts:
            if (
                account.id == recommendation.account
                and account.authenticated
                and not account.duplicate
                and account.usage
                and account.usage.status in {"ready", "close", "critical"}
            ):
                return account.id
        return None

    def _select_activate_and_start(
        self, session_id: str | None
    ) -> subprocess.Popen | None:
        """Atomically pick a profile, update .active, and bind a new child."""
        if self.stop_requested:
            return None
        try:
            with self._selection_lock():
                target = self._recommendation_locked()
                if not target or self.stop_requested:
                    return None
                self.adapter.activate(target)
                replacement = self._start(target, session_id)
                self.bound_account = target
                return replacement
        except SelectionInterrupted:
            return None
        except TimeoutError:
            self._warn("timed out waiting for the profile selection lock; retrying")
            return None

    def _wait_for_recommendation(
        self, child: subprocess.Popen | None, session_id: str | None
    ) -> subprocess.Popen | None:
        # A rotation owns only this supervisor's child tree.  Stop it before
        # acquiring the cross-process lock, so lock holders never encompass a
        # running interactive Codex process or capacity wait.
        if child is not None:
            self._stop_child(child)
        announced = False
        while not self.stop_requested:
            replacement = self._select_activate_and_start(session_id)
            if replacement is not None:
                return replacement
            if not announced:
                self._warn("all usable profiles are exhausted; waiting for capacity")
                announced = True
            self._pause(self.poll_interval)
        return None

    def _arguments(self, session_id: str | None) -> list[str]:
        binary = self.adapter.binary or "codex"
        tail = (
            ["resume", session_id, self.continue_prompt]
            if session_id
            else self.initial_arguments
        )
        return [binary, *DEFAULT_CODEX_ARGS, *tail]

    def _request_review_drain(self, child: subprocess.Popen, *, final: bool = False) -> None:
        """Ask the proven root thread to collect reviews before its rotation.

        The owned Codex child inherits the user's terminal, so AgentHop must
        never synthesize terminal input.  ``codex queue`` is an independent,
        non-interactive supported delivery path for a thread message.
        """
        if self.review_drain_grace <= 0 or child.poll() is not None:
            return
        if not self.root_session or self._review_drain_delivered:
            return
        if final:
            if self._review_drain_final_attempted:
                return
            self._review_drain_final_attempted = True
        else:
            if self._review_drain_critical_attempted:
                return
            self._review_drain_critical_attempted = True
        if self.bound_account is None:
            return
        binary = self.adapter.binary or "codex"
        try:
            result = self._queue_runner(
                [
                    binary,
                    "queue",
                    "--thread",
                    self.root_session,
                    "--message",
                    REVIEW_DRAIN_MESSAGE,
                ],
                env=os.environ | self.adapter.launch_environment(self.bound_account),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=REVIEW_QUEUE_TIMEOUT,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._warn(f"could not queue review wrap-up request; rotating normally ({exc})")
            return
        if result.returncode != 0:
            self._warn("could not queue review wrap-up request; rotating normally")
            return
        self._review_drain_delivered = True
        self._warn(
            f"queued review wrap-up request; allowing {self.review_drain_grace:g}s before rotation"
        )
        self._pause(self.review_drain_grace)

    def _start(self, account: str, session_id: str | None) -> subprocess.Popen:
        environment = os.environ | self.adapter.launch_environment(account)
        # Inherit the foreground terminal's process group so interactive Codex
        # can read it normally.  Cleanup below targets only this child tree;
        # never signal the shell's process group.
        self._review_drain_delivered = False
        self._review_drain_critical_attempted = False
        self._review_drain_final_attempted = False
        return self._popen(self._arguments(session_id), env=environment)

    def _stop_child(self, child: subprocess.Popen) -> None:
        if child.poll() is not None:
            return
        self._signal_tree(child.pid, signal.SIGTERM)
        for _ in range(50):
            if child.poll() is not None:
                return
            self._pause(0.1)
        self._signal_tree(child.pid, signal.SIGKILL)
        child.wait()

    @staticmethod
    def _signal_tree(pid: int, signum: signal.Signals) -> None:
        # Signal descendants first so a parent cannot immediately recreate a
        # worker after it receives TERM.  PIDs are rechecked by kill itself.
        for process_id in sorted(_descendants(pid), reverse=True):
            try:
                os.kill(process_id, signum)
            except ProcessLookupError:
                continue

    def _remember_root_session(self, child: subprocess.Popen) -> None:
        if self.root_session:
            return
        self.root_session = locate_root_session(
            child.pid, self.adapter.default_home / "state_5.sqlite"
        )

    def _rotate(self, child: subprocess.Popen | None) -> subprocess.Popen | None:
        if not self.root_session:
            action = (
                "leaving Codex running with rotation disabled"
                if child is not None
                else "not restarting after exit"
            )
            self._warn(f"could not uniquely identify the root session; {action}")
            self.automation_disabled = True
            return child
        if child is not None:
            self._request_review_drain(child, final=True)
        return self._wait_for_recommendation(child, self.root_session)

    def _on_interrupt(self, _signum, _frame) -> None:
        self.stop_requested = True
        self._wake.set()

    def run(self) -> int:
        previous_handler = signal.signal(signal.SIGINT, self._on_interrupt)
        child: subprocess.Popen | None = None
        try:
            self.bound_account = self.adapter._active()
            initial = self._bound_usage()
            if self._blocked(initial):
                child = self._wait_for_recommendation(None, None)
                if child is None:
                    return 130
            else:
                child = self._start(self.bound_account, None)
            while True:
                if self.stop_requested:
                    self._stop_child(child)
                    return 130
                exit_code = child.poll()
                if exit_code is not None:
                    if self.automation_disabled:
                        return exit_code
                    usage = self._bound_usage()
                    if self._blocked(usage):
                        replacement = self._rotate(None)
                        if replacement is None:
                            return 130 if self.stop_requested else exit_code
                        child = replacement
                        continue
                    return exit_code
                if not self.automation_disabled:
                    self._remember_root_session(child)
                    usage = self._bound_usage()
                    if usage.usage and usage.usage.status == "critical":
                        self._request_review_drain(child)
                    if self._blocked(usage):
                        replacement = self._rotate(child)
                        if replacement is None:
                            return 130
                        child = replacement
                        continue
                self._pause(self.poll_interval)
        finally:
            signal.signal(signal.SIGINT, previous_handler)


def add_parser(subcommands: argparse._SubParsersAction) -> None:
    auto = subcommands.add_parser(
        "auto", help="supervise Codex and switch profiles only after confirmed exhaustion"
    )
    auto.add_argument(
        "--poll-interval", type=float, default=30.0,
        help="seconds between active-profile checks (default: 30)",
    )
    auto.add_argument(
        "--continue-prompt", default="continue",
        help="prompt passed after an automatic resume (default: continue)",
    )
    auto.add_argument(
        "--review-drain-grace",
        type=float,
        default=DEFAULT_REVIEW_DRAIN_GRACE,
        help=(
            "seconds for queued reviewers to return findings before rotation "
            f"(0 disables; default: {DEFAULT_REVIEW_DRAIN_GRACE:g}; max: {MAX_REVIEW_DRAIN_GRACE:g})"
        ),
    )
    auto.add_argument(
        "codex_args", nargs=argparse.REMAINDER,
        help="initial Codex arguments; place them after --",
    )


def run(args: argparse.Namespace) -> int:
    if args.poll_interval <= 0:
        raise ValueError("--poll-interval must be greater than zero")
    if not 0 <= args.review_drain_grace <= MAX_REVIEW_DRAIN_GRACE:
        raise ValueError(
            "--review-drain-grace must be between 0 and "
            f"{MAX_REVIEW_DRAIN_GRACE:g} seconds"
        )
    initial = list(args.codex_args)
    if initial[:1] == ["--"]:
        initial.pop(0)
    return AutoSupervisor(
        CodexAdapter(),
        poll_interval=args.poll_interval,
        continue_prompt=args.continue_prompt,
        initial_arguments=initial,
        review_drain_grace=args.review_drain_grace,
    ).run()
