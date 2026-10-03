from __future__ import annotations

from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from agenthop import auto, cli
from agenthop.models import AccountModel, ProviderModel, UsageModel


def account(name: str, status: str, *, active: bool = False, duplicate: bool = False, authenticated: bool = True) -> AccountModel:
    return AccountModel(
        provider="codex", id=name, active=active, authenticated=authenticated,
        duplicate=duplicate, usage=UsageModel(status=status),
    )


class Adapter:
    id = "codex"
    name = "Codex"
    binary = "/usr/bin/codex"

    def __init__(self, statuses: dict[str, str], active: str = "one") -> None:
        self.statuses = statuses
        self.active = active
        self.activations: list[str] = []
        self.default_home = Path("/tmp/agenthop-auto-test")
        self.profile_root = self.default_home / "profiles"
        self.account_calls: list[str] = []
        self.account_refreshes = 0
        self.accounts_refreshes = 0

    def _active(self) -> str:
        return self.active

    def account(self, name: str, *, refresh: bool = False) -> AccountModel:
        self.account_calls.append(name)
        self.account_refreshes += int(refresh)
        return account(name, self.statuses[name], active=name == self.active)

    def accounts(self, *, refresh: bool = False) -> list[AccountModel]:
        self.accounts_refreshes += int(refresh)
        return [
            account(name, status, active=name == self.active,
                    duplicate=name == "duplicate", authenticated=name != "logged-out")
            for name, status in self.statuses.items()
        ]

    def sessions(self):
        return []

    def provider(self) -> ProviderModel:
        return ProviderModel(id=self.id, name=self.name, available=True)

    def activate(self, name: str) -> None:
        self.active = name
        self.activations.append(name)

    def launch_environment(self, name: str) -> dict[str, str]:
        return {"CODEX_HOME": f"/profiles/{name}", "CODEX_SQLITE_HOME": "/shared"}


class Process:
    def __init__(self, result: int | None = 0) -> None:
        self.pid = 999999
        self.result = result

    def poll(self):
        return self.result

    def wait(self):
        return self.result


def test_cli_parses_auto_options_and_passthrough() -> None:
    parsed = cli.build_parser().parse_args(
        [
            "auto", "--poll-interval", "12", "--continue-prompt", "go",
            "--review-drain-grace", "10", "--", "resume", "root-1",
        ]
    )
    assert parsed.command == "auto"
    assert parsed.poll_interval == 12
    assert parsed.continue_prompt == "go"
    assert parsed.review_drain_grace == 10
    assert parsed.codex_args == ["--", "resume", "root-1"]


def test_critical_usage_queues_one_review_drain_and_allows_grace() -> None:
    adapter = Adapter({"one": "critical"})
    child = Process(None)
    queued: list[tuple[list[str], dict]] = []
    waits: list[float] = []

    def queue_runner(arguments, **kwargs):
        queued.append((arguments, kwargs))
        return subprocess.CompletedProcess(arguments, 0)

    supervisor = auto.AutoSupervisor(
        adapter,
        initial_arguments=["resume", "root-42"],
        queue_runner=queue_runner,
        sleep=waits.append,
        review_drain_grace=8,
    )
    supervisor.bound_account = "one"

    supervisor._request_review_drain(child)
    supervisor._request_review_drain(child)

    assert queued[0][0] == [
        "/usr/bin/codex", "queue", "--thread", "root-42", "--message",
        auto.REVIEW_DRAIN_MESSAGE,
    ]
    assert queued[0][1]["env"]["CODEX_HOME"] == "/profiles/one"
    assert waits == [8]
    assert len(queued) == 1


def test_blocked_rotation_queues_review_drain_when_critical_was_missed() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    child = Process(None)
    queued: list[list[str]] = []
    waits: list[float] = []

    def queue_runner(arguments, **_kwargs):
        queued.append(arguments)
        return subprocess.CompletedProcess(arguments, 0)

    supervisor = auto.AutoSupervisor(
        adapter,
        initial_arguments=["resume", "root-42"],
        popen=lambda *_args, **_kwargs: Process(0),
        queue_runner=queue_runner,
        sleep=waits.append,
        review_drain_grace=5,
    )
    supervisor.bound_account = "one"
    supervisor._stop_child = lambda _child: None  # type: ignore[method-assign]

    assert supervisor._rotate(child) is not None
    assert queued
    assert waits == [5]


def test_failed_review_queue_does_not_delay_or_prevent_rotation() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    child = Process(None)
    waits: list[float] = []

    supervisor = auto.AutoSupervisor(
        adapter,
        initial_arguments=["resume", "root-42"],
        popen=lambda *_args, **_kwargs: Process(0),
        queue_runner=lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1),
        sleep=waits.append,
    )
    supervisor.bound_account = "one"
    supervisor._stop_child = lambda _child: None  # type: ignore[method-assign]

    assert supervisor._rotate(child) is not None
    assert waits == []


def test_failed_critical_review_queue_gets_one_final_blocked_retry() -> None:
    adapter = Adapter({"one": "blocked"})
    child = Process(None)
    results = [1, 0]
    queued: list[list[str]] = []
    waits: list[float] = []

    def queue_runner(arguments, **_kwargs):
        queued.append(arguments)
        return subprocess.CompletedProcess(arguments, results.pop(0))

    supervisor = auto.AutoSupervisor(
        adapter,
        initial_arguments=["resume", "root-42"],
        queue_runner=queue_runner,
        sleep=waits.append,
        review_drain_grace=6,
    )
    supervisor.bound_account = "one"

    supervisor._request_review_drain(child)
    supervisor._request_review_drain(child)
    supervisor._request_review_drain(child, final=True)
    supervisor._request_review_drain(child, final=True)

    assert len(queued) == 2
    assert waits == [6]


@pytest.mark.parametrize("value", ["-1", "121"])
def test_review_drain_grace_is_bounded(value: str) -> None:
    args = cli.build_parser().parse_args(["auto", "--review-drain-grace", value])
    with pytest.raises(ValueError, match="review-drain-grace"):
        auto.run(args)


def test_preblocked_startup_activates_a_live_recommendation_before_launch() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    started: list[list[str]] = []

    def popen(arguments, **_kwargs):
        started.append(arguments)
        return Process(0)

    supervisor = auto.AutoSupervisor(adapter, initial_arguments=["initial prompt"], popen=popen)
    assert supervisor.run() == 0
    assert adapter.activations == ["two"]
    assert started[0][-1] == "initial prompt"


def test_rotation_resumes_exact_known_root_with_continue() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    started: list[list[str]] = []

    def popen(arguments, **_kwargs):
        started.append(arguments)
        return Process(0)

    supervisor = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-42"], popen=popen)
    replacement = supervisor._rotate(None)
    assert replacement is not None
    assert adapter.activations == ["two"]
    assert started == [["/usr/bin/codex", *auto.DEFAULT_CODEX_ARGS, "resume", "root-42", "continue"]]


def test_blocked_active_rotates_to_authenticated_nonduplicate_critical_fallback() -> None:
    adapter = Adapter({"one": "blocked", "two": "critical"})
    started: list[list[str]] = []

    def popen(arguments, **_kwargs):
        started.append(arguments)
        return Process(0)

    supervisor = auto.AutoSupervisor(
        adapter, initial_arguments=["resume", "root-42"], popen=popen
    )
    assert supervisor._recommendation() == "two"
    assert supervisor._rotate(None) is not None
    assert adapter.activations == ["two"]
    assert started[0][-3:] == ["resume", "root-42", "continue"]


def test_all_blocked_waits_then_recovers() -> None:
    adapter = Adapter({"one": "blocked", "two": "blocked"})
    supervisor = auto.AutoSupervisor(
        adapter, poll_interval=0.1, popen=lambda *_args, **_kwargs: Process(0)
    )
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        adapter.statuses["two"] = "ready"

    supervisor._sleep = sleep
    replacement = supervisor._wait_for_recommendation(None, None)
    assert replacement is not None
    assert adapter.activations == ["two"]
    assert waits == [0.1]


@pytest.mark.parametrize("status", ["ready", "close", "critical", "unknown", "error"])
def test_normal_exit_and_nonblocked_states_never_switch(status: str) -> None:
    adapter = Adapter({"one": status, "two": "ready"})
    supervisor = auto.AutoSupervisor(adapter, popen=lambda *_args, **_kwargs: Process(7))
    assert supervisor.run() == 7
    assert adapter.activations == []


def test_ctrl_c_is_an_intentional_stop_without_rotation() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    supervisor = auto.AutoSupervisor(adapter)
    supervisor._on_interrupt(None, None)
    assert supervisor._wait_for_recommendation(None, None) is None
    assert adapter.activations == []


def test_running_child_uses_the_configured_poll_interval() -> None:
    adapter = Adapter({"one": "ready"})
    child = Process(None)
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(seconds)
        child.result = 0

    supervisor = auto.AutoSupervisor(
        adapter, poll_interval=4, popen=lambda *_args, **_kwargs: child, sleep=sleep
    )
    assert supervisor.run() == 0
    assert waits == [4]


def test_recommendation_excludes_duplicate_and_unauthenticated_profiles() -> None:
    adapter = Adapter({"one": "blocked", "duplicate": "ready", "logged-out": "ready", "two": "close"})
    assert auto.AutoSupervisor(adapter)._recommendation() == "two"


def test_bound_supervisor_polls_its_child_profile_after_global_active_changes() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    first = auto.AutoSupervisor(adapter)
    first.bound_account = "one"

    # A second terminal has changed the global launch selector.  The first
    # child still owns CODEX_HOME for profile one and must inspect that profile.
    adapter.activate("two")
    inspected = first._bound_usage()

    assert inspected.id == "one"
    assert adapter.account_calls == ["one"]


def test_two_supervisors_serialize_selection_and_keep_distinct_sessions() -> None:
    adapter = Adapter({"one": "blocked", "two": "blocked", "three": "ready"})
    starts: list[list[str]] = []

    def popen(arguments, **_kwargs):
        starts.append(arguments)
        return Process(None)

    first = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-one"], popen=popen)
    second = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-two"], popen=popen)
    first.bound_account = "one"
    second.bound_account = "two"
    first_child, second_child = Process(None), Process(None)
    stopped: list[Process] = []
    first._stop_child = stopped.append  # type: ignore[method-assign]

    assert first._rotate(first_child) is not None
    # The second selection performs a new full refresh after the first marker
    # update and may validly select the same healthy account.
    assert second._rotate(None) is not None

    assert stopped == [first_child]
    assert second_child not in stopped
    assert adapter.active == "three"
    assert adapter.accounts_refreshes == 2
    assert starts == [
        ["/usr/bin/codex", *auto.DEFAULT_CODEX_ARGS, "resume", "root-one", "continue"],
        ["/usr/bin/codex", *auto.DEFAULT_CODEX_ARGS, "resume", "root-two", "continue"],
    ]
    assert first.bound_account == second.bound_account == "three"


def test_healthy_bound_child_is_not_rotated_when_another_profile_is_blocked() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    healthy = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-two"])
    healthy.bound_account = "two"

    adapter.activate("one")
    assert not healthy._blocked(healthy._bound_usage())
    assert adapter.activations == ["one"]


def test_selection_lock_rejects_a_symlinked_private_lock(tmp_path: Path) -> None:
    adapter = Adapter({"one": "ready"})
    adapter.profile_root = tmp_path / "profiles"
    adapter.profile_root.mkdir()
    target = tmp_path / "outside"
    target.touch()
    (adapter.profile_root / auto.AUTO_LOCK_NAME).symlink_to(target)

    with pytest.raises(RuntimeError, match="must not be a symbolic link"):
        with auto.AutoSupervisor(adapter)._selection_lock():
            pass


def test_session_locator_uses_cli_root_and_excludes_json_subagent(tmp_path: Path) -> None:
    root_rollout = tmp_path / "root.jsonl"
    subagent_rollout = tmp_path / "subagent.jsonl"
    root_rollout.touch()
    subagent_rollout.touch()
    database = tmp_path / "state_5.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE threads (id TEXT, rollout_path TEXT, source TEXT)")
        connection.executemany(
            "INSERT INTO threads VALUES (?, ?, ?)",
            [("root-1", str(root_rollout), "cli"), ("sub-1", str(subagent_rollout), '{"subagent":true}')],
        )
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys,time; a=open(sys.argv[1]); b=open(sys.argv[2]); time.sleep(5)", str(root_rollout), str(subagent_rollout)]
    )
    try:
        for _ in range(20):
            if auto.locate_root_session(child.pid, database) == "root-1":
                break
            __import__("time").sleep(0.02)
        assert auto.locate_root_session(child.pid, database) == "root-1"
    finally:
        child.terminate()
        child.wait()


def test_ambiguous_or_unidentified_session_disables_automation_without_killing() -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    child = Process(None)
    supervisor = auto.AutoSupervisor(adapter)
    assert supervisor._rotate(child) is child
    assert supervisor.automation_disabled is True
    assert adapter.activations == []
