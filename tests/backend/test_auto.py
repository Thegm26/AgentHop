from __future__ import annotations

from pathlib import Path
import multiprocessing
import fcntl
import signal
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from agenthop import auto, cli
from agenthop.models import AccountModel, ProviderModel, UsageModel


def account(
    name: str,
    status: str,
    *,
    active: bool = False,
    duplicate: bool = False,
    authenticated: bool = True,
    five_hour_used: int | None = None,
    weekly_used: int | None = None,
) -> AccountModel:
    return AccountModel(
        provider="codex", id=name, active=active, authenticated=authenticated,
        duplicate=duplicate,
        usage=UsageModel(
            status=status, fiveHourUsed=five_hour_used, weeklyUsed=weekly_used
        ),
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
            "--", "resume", "root-1",
        ]
    )
    assert parsed.command == "auto"
    assert parsed.poll_interval == 12
    assert parsed.continue_prompt == "go"
    assert parsed.codex_args == ["--", "resume", "root-1"]


def test_auto_default_poll_interval_is_two_minutes() -> None:
    assert cli.build_parser().parse_args(["auto"]).poll_interval == 120
    assert auto.AutoSupervisor(Adapter({"one": "ready"})).poll_interval == 120


@pytest.mark.parametrize("used", [85, 100])
def test_quota_checks_and_rotation_never_queue_reviewer_messages(used: int, monkeypatch) -> None:
    adapter = Adapter({"one": "blocked" if used == 100 else "close", "two": "ready"})
    commands: list[list[str]] = []
    child = Process(None)

    def forbidden(*_args, **_kwargs):
        pytest.fail("supervisor must not issue non-interactive messages")

    monkeypatch.setattr(auto.subprocess, "run", forbidden)
    supervisor = auto.AutoSupervisor(
        adapter, initial_arguments=["resume", "root-42"],
        popen=lambda args, **_kwargs: commands.append(args) or Process(0),
        sleep=lambda _seconds: setattr(child, "result", 0),
    )
    supervisor.bound_account = "one"
    if used == 100:
        supervisor._stop_child = lambda _child: None
        assert supervisor._rotate(child) is not None
        assert commands == [[adapter.binary, *auto.DEFAULT_CODEX_ARGS, "resume", "root-42", "continue"]]
    else:
        adapter.account = lambda name, **_kwargs: account(name, "close", five_hour_used=85)
        supervisor._popen = lambda args, **_kwargs: commands.append(args) or child
        assert supervisor.run() == 0
        assert commands == [[adapter.binary, *auto.DEFAULT_CODEX_ARGS, "resume", "root-42"]]
    assert all("queue" not in command for command in commands)


def test_interrupt_after_replacement_launch_cleans_up_current_owned_child(monkeypatch) -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    child = Process(None)
    supervisor = auto.AutoSupervisor(adapter, popen=lambda *_args, **_kwargs: child)
    stopped: list[Process] = []
    select = supervisor._wait_for_recommendation

    def interrupt_after_launch(*args):
        select(*args)
        supervisor._handle_interrupt(None, None)

    monkeypatch.setattr(supervisor, "_wait_for_recommendation", interrupt_after_launch)
    monkeypatch.setattr(supervisor, "_stop_child", stopped.append)
    assert supervisor.run() == 130
    assert stopped == [child]


@pytest.mark.parametrize("exit_code", [130, -signal.SIGINT])
@pytest.mark.parametrize("exit_probe", ["blocked", "hung"])
def test_intentional_child_interrupt_never_probes_or_rotates(exit_code, exit_probe, monkeypatch) -> None:
    adapter = Adapter({"one": "ready", "two": "ready"})
    probes = 0

    def inspect(name, **_kwargs):
        nonlocal probes
        probes += 1
        if probes > 1 and exit_probe == "hung":
            pytest.fail("intentional interrupt must not start an exit usage probe")
        return account(name, "ready" if probes == 1 else "blocked")

    monkeypatch.setattr(adapter, "account", inspect)
    supervisor = auto.AutoSupervisor(
        adapter, initial_arguments=["resume", "root-42"],
        popen=lambda *_args, **_kwargs: Process(exit_code),
    )
    assert supervisor.run() == 130
    assert probes == 1
    assert adapter.activations == []


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


@pytest.mark.parametrize("status", ["blocked", "error", "unknown"])
def test_all_unavailable_returns_to_shell_once(status, capsys) -> None:
    adapter = Adapter({"one": status, "two": status})
    def forbidden(*_args, **_kwargs):
        pytest.fail("no child or capacity sleep is permitted")
    supervisor = auto.AutoSupervisor(adapter, popen=forbidden, sleep=forbidden)
    assert supervisor.run() == 75
    assert adapter.accounts_refreshes == 1
    assert adapter.activations == []
    assert "No usable Codex profile available; returning to shell" in capsys.readouterr().err


def test_failed_rotation_keeps_owned_child_interactive_without_more_probes() -> None:
    adapter = Adapter({"one": "blocked", "two": "blocked"})
    child = Process(None)
    supervisor = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-42"])
    supervisor.bound_account = "one"
    supervisor._stop_child = lambda _child: pytest.fail("keep existing child")
    assert supervisor._rotate(child) is child
    assert supervisor.automation_disabled
    assert adapter.accounts_refreshes == 1
    assert adapter.activations == []


@pytest.mark.parametrize("status", ["ready", "close", "critical"])
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


@pytest.mark.parametrize("interval", [None, 4])
def test_running_child_uses_the_configured_poll_interval(interval: float | None, monkeypatch) -> None:
    adapter = Adapter({"one": "ready"})
    child = Process(None)
    waits: list[float] = []
    now = 0.0
    expected_interval = 120 if interval is None else interval
    probes: list[float] = []
    account = adapter.account

    def inspect(*args, **kwargs):
        probes.append(now)
        return account(*args, **kwargs)

    def sleep(seconds: float) -> None:
        nonlocal now
        waits.append(seconds)
        now += seconds
        if now > expected_interval:
            child.result = 0

    monkeypatch.setattr(auto.time, "monotonic", lambda: now)
    monkeypatch.setattr(adapter, "account", inspect)

    supervisor = auto.AutoSupervisor(
        adapter, **({"poll_interval": interval} if interval is not None else {}),
        popen=lambda *_args, **_kwargs: child, sleep=sleep
    )
    assert supervisor.run() == 0
    assert waits == [1] * (expected_interval + 1)
    # Startup checks, one scheduled running check, then the existing exit check.
    assert probes == [0, 0, expected_interval, expected_interval + 1]


def test_child_exit_interrupts_a_long_quota_wait() -> None:
    supervisor = auto.AutoSupervisor(Adapter({"one": "ready"}))
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.05)"])
    try:
        started = time.monotonic()
        supervisor._wait_for_child(child, 120)
        assert time.monotonic() - started < 2
        assert child.poll() == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def test_ctrl_c_wakes_a_long_running_child_wait() -> None:
    supervisor = auto.AutoSupervisor(Adapter({"one": "ready"}))
    timer = threading.Timer(0.05, supervisor._on_interrupt, args=(None, None))
    timer.start()
    try:
        started = time.monotonic()
        supervisor._wait_for_child(Process(None), 120)
        assert time.monotonic() - started < 0.5
        assert supervisor.stop_requested
    finally:
        timer.cancel()
        timer.join()


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


def test_hung_selection_does_not_hold_lock_or_block_another_terminal(tmp_path: Path) -> None:
    context = multiprocessing.get_context("fork")
    probing, release = context.Event(), context.Event()
    profiles = tmp_path / "profiles"

    def slow_terminal():
        adapter = Adapter({"one": "blocked", "two": "ready"})
        adapter.profile_root = profiles
        original = adapter.accounts
        def accounts(**kwargs):
            probing.set()
            assert release.wait(5)
            return original(**kwargs)
        adapter.accounts = accounts
        supervisor = auto.AutoSupervisor(adapter, popen=lambda *_a, **_kw: Process(0))
        assert supervisor._select_activate_and_start(None) is not None

    process = context.Process(target=slow_terminal)
    process.start()
    try:
        assert probing.wait(3)
        adapter = Adapter({"one": "blocked", "two": "ready"})
        adapter.profile_root = profiles
        original = adapter.accounts
        def accounts(**kwargs):
            # A separate descriptor proves the snapshot is outside mutation lock.
            profiles.mkdir(exist_ok=True)
            with (profiles / auto.AUTO_LOCK_NAME).open("a") as descriptor:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            return original(**kwargs)
        adapter.accounts = accounts
        second = auto.AutoSupervisor(adapter, popen=lambda *_a, **_kw: Process(0))
        assert second._select_activate_and_start(None) is not None
        assert not release.is_set()
        assert second.bound_account == "two"
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.kill()
            process.join()
    assert process.exitcode == 0


def test_busy_selection_is_attempted_once_and_keeps_existing_child(tmp_path, monkeypatch, capsys) -> None:
    adapter = Adapter({"one": "blocked", "two": "ready"})
    child = Process(None)
    supervisor = auto.AutoSupervisor(adapter, initial_arguments=["resume", "root-42"])
    def busy():
        raise TimeoutError()
    monkeypatch.setattr(supervisor, "_selection_lock", busy)
    monkeypatch.setattr(supervisor, "_stop_child", lambda _child: pytest.fail("do not stop on lock contention"))
    assert supervisor._rotate(child) is child
    assert supervisor.automation_disabled
    assert adapter.accounts_refreshes == 1
    assert "selection is busy" in capsys.readouterr().err


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
