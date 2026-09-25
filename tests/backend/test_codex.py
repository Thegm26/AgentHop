from __future__ import annotations

import os
import shlex
import sqlite3
import time
from pathlib import Path

import pytest

from agenthop.providers.base import DuplicateAccountError
from agenthop.providers.codex import CodexAdapter


@pytest.fixture
def adapter(tmp_path: Path) -> CodexAdapter:
    default = tmp_path / ".codex"
    profiles = tmp_path / ".codex-profiles"
    default.mkdir()
    profiles.mkdir()
    return CodexAdapter(
        default_home=default,
        profile_root=profiles,
        binary="/usr/bin/codex-test",
        rpc_timeout=0.1,
    )


def add_profile(adapter: CodexAdapter, name: str, authenticated: bool = True) -> Path:
    home = adapter.profile_root / name
    home.mkdir()
    if authenticated:
        (home / "auth.json").touch(mode=0o600)
    return home


def test_discovers_accounts_without_reading_auth(
    adapter: CodexAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_profile(adapter, "account-01")
    (adapter.profile_root / "bad name").mkdir()

    original = Path.read_text

    def guarded_read(path: Path, *args, **kwargs):
        assert path.name != "auth.json"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)

    accounts = adapter.accounts()
    assert [account.id for account in accounts] == ["default", "account-01"]
    assert accounts[1].authenticated is True


def test_activation_is_atomic_and_validated(adapter: CodexAdapter) -> None:
    add_profile(adapter, "account-01")
    adapter.activate("account-01")
    assert (adapter.profile_root / ".active").read_text() == "account-01\n"
    assert adapter.accounts()[1].active is True
    with pytest.raises(LookupError, match="unknown account"):
        adapter.activate("missing")
    with pytest.raises(ValueError, match="invalid account"):
        adapter.activate("../escape")


def test_onboard_creates_private_profile_and_returns_portable_login_command(
    adapter: CodexAdapter,
) -> None:
    command = adapter.onboard("account-02")
    profile = adapter.profile_root / "account-02"

    assert profile.is_dir()
    assert profile.stat().st_mode & 0o777 == 0o700
    assert shlex.split(command) == [
        "env",
        "CODEX_HOME=$HOME/.codex-profiles/account-02",
        "codex",
        "-c",
        'cli_auth_credentials_store="file"',
        "login",
    ]
    assert command.startswith("env ")
    assert str(adapter.profile_root) not in command
    assert adapter.binary not in command
    assert not (profile / "auth.json").exists()
    with pytest.raises(DuplicateAccountError, match="already exists"):
        adapter.onboard("account-02")
    with pytest.raises(DuplicateAccountError, match="already exists"):
        adapter.onboard("default")
    with pytest.raises(ValueError, match="invalid account"):
        adapter.onboard("../escape")


def test_stale_active_marker_falls_back_to_default(adapter: CodexAdapter) -> None:
    (adapter.profile_root / ".active").write_text("missing\n")
    assert adapter.accounts()[0].active is True


def test_remove_profile_hides_default_and_rejects_active_named_profile(adapter: CodexAdapter) -> None:
    profile = add_profile(adapter, "account-01")
    (adapter.default_home / "auth.json").touch(mode=0o600)
    (adapter.default_home / "config.toml").write_text('model = "gpt-5"\n')
    (adapter.default_home / "sessions").mkdir()
    adapter.activate("account-01")

    with pytest.raises(ValueError, match="cannot remove the active profile"):
        adapter.remove("account-01")
    assert profile.exists()
    adapter.remove("default")
    assert adapter.default_home.exists()
    assert not (adapter.default_home / "auth.json").exists()
    assert not (adapter.default_home / "config.toml").exists()
    assert (adapter.default_home / "sessions").exists()
    assert [account.id for account in adapter.accounts()] == ["account-01"]
    with pytest.raises(LookupError, match="unknown account"):
        adapter.activate("default")

    command = adapter.onboard("default")
    assert 'CODEX_HOME="$HOME/.codex"' in command
    assert [account.id for account in adapter.accounts()] == ["default", "account-01"]

    adapter.activate("default")
    adapter.remove("account-01")
    assert not profile.exists()


def test_remove_rejects_non_profile_or_symlink(adapter: CodexAdapter) -> None:
    (adapter.profile_root / "account-link").symlink_to(adapter.default_home, target_is_directory=True)

    with pytest.raises(LookupError, match="unknown account"):
        adapter.remove("account-link")


def test_command_shares_state_and_never_contains_auth(adapter: CodexAdapter) -> None:
    home = add_profile(adapter, "account-01")
    session = home / "sessions" / "2026" / "rollout.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text("safe session")

    command = adapter.command("account-01", "resume", "abc-123")

    assert command == (
        f"CODEX_HOME={home} CODEX_SQLITE_HOME={adapter.default_home} "
        "/usr/bin/codex-test resume abc-123"
    )
    assert "auth.json" not in command
    assert (
        adapter.default_home / "sessions" / "2026" / "rollout.jsonl"
    ).read_text() == "safe session"
    assert (home / "sessions").is_symlink()


def test_command_validation_blocks_shell_injection(adapter: CodexAdapter) -> None:
    add_profile(adapter, "account-01")
    with pytest.raises(ValueError, match="invalid sessionId"):
        adapter.command("account-01", "resume", "abc; touch /tmp/owned")
    with pytest.raises(ValueError, match="invalid sessionId"):
        adapter.command("account-01", "resume", "../../auth.json")
    with pytest.raises(ValueError, match="only valid"):
        adapter.command("account-01", "new", "abc")


def test_command_quotes_paths_with_spaces(tmp_path: Path) -> None:
    adapter = CodexAdapter(
        default_home=tmp_path / "default home",
        profile_root=tmp_path / "profile root",
        binary="/opt/Codex App/codex",
    )
    adapter.default_home.mkdir()
    adapter.profile_root.mkdir()

    words = shlex.split(adapter.command("default", "new"))

    assert words == [
        f"CODEX_HOME={adapter.default_home}",
        f"CODEX_SQLITE_HOME={adapter.default_home}",
        "/opt/Codex App/codex",
    ]


def test_collision_migration_preserves_both_files(adapter: CodexAdapter) -> None:
    home = add_profile(adapter, "account-01")
    shared = adapter.default_home / "sessions" / "same.jsonl"
    local = home / "sessions" / "same.jsonl"
    shared.parent.mkdir()
    local.parent.mkdir()
    shared.write_text("original")
    local.write_text("different")
    create_threads_database(
        adapter.default_home / "state_5.sqlite",
        [("shared", "Shared", 10, str(shared))],
    )
    create_threads_database(
        home / "state_5.sqlite",
        [("profile", "Profile", 20, str(local))],
    )

    adapter.command("account-01", "new")

    assert shared.read_text() == "original"
    conflicts = list(shared.parent.glob("same.jsonl.agenthop-conflict-*"))
    assert len(conflicts) == 1
    assert conflicts[0].read_text() == "different"
    with sqlite3.connect(adapter.default_home / "state_5.sqlite") as database:
        rollout = database.execute(
            "SELECT rollout_path FROM threads WHERE id = 'profile'"
        ).fetchone()[0]
    assert rollout == str(conflicts[0])


def create_threads_database(path: Path, rows: list[tuple[str, str, int, str]]) -> None:
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, updated_at INTEGER, rollout_path TEXT)"
        )
        database.executemany("INSERT INTO threads VALUES (?, ?, ?, ?)", rows)


def test_migrates_and_lists_shared_sqlite_sessions(adapter: CodexAdapter) -> None:
    home = add_profile(adapter, "account-01")
    create_threads_database(
        adapter.default_home / "state_5.sqlite",
        [("shared", "Shared", 10, str(adapter.default_home / "sessions/shared.jsonl"))],
    )
    create_threads_database(
        home / "state_5.sqlite",
        [("profile", "Profile", 20, str(home / "sessions/profile.jsonl"))],
    )

    adapter.command("account-01", "new")
    sessions = adapter.sessions()

    assert [session.id for session in sessions] == ["profile", "shared"]
    with sqlite3.connect(adapter.default_home / "state_5.sqlite") as database:
        rollout = database.execute(
            "SELECT rollout_path FROM threads WHERE id = 'profile'"
        ).fetchone()[0]
    assert rollout == str(adapter.default_home / "sessions/profile.jsonl")


def test_first_profile_database_seeds_missing_shared_database(
    adapter: CodexAdapter,
) -> None:
    home = add_profile(adapter, "account-01")
    create_threads_database(
        home / "state_5.sqlite",
        [("profile", "Profile", 20, str(home / "sessions/profile.jsonl"))],
    )

    assert adapter.sessions() == []
    adapter.command("account-01", "new")
    sessions = adapter.sessions()

    assert [session.id for session in sessions] == ["profile"]
    assert (adapter.default_home / "state_5.sqlite").stat().st_mode & 0o777 == 0o600


def test_duplicate_account_is_not_usable(adapter: CodexAdapter) -> None:
    home = add_profile(adapter, "account-01")
    (home / ".duplicate-of").write_text("default\n")
    account = adapter.accounts()[1]
    assert account.duplicate is True
    with pytest.raises(ValueError, match="duplicate"):
        adapter.command("account-01", "new")


def test_usage_mapping_and_status() -> None:
    usage = CodexAdapter._usage(
        {"account": {"planType": "plus"}},
        {
            "ordinaryUsageAllowed": True,
            "rateLimits": {
                "primary": {
                    "windowDurationMins": 300,
                    "usedPercent": 96,
                    "resetsAt": 100,
                },
                "secondary": {
                    "windowDurationMins": 10080,
                    "usedPercent": 40,
                    "resetsAt": 200,
                },
            },
        },
    )
    assert usage.status == "critical"
    assert usage.plan == "plus"
    assert usage.five_hour_used == 96


def test_usage_exposes_available_reset_credit_count_without_credit_ids() -> None:
    usage = CodexAdapter._usage(
        {"account": {"planType": "plus"}},
        {
            "rateLimits": {},
            "rateLimitResetCredits": {
                "availableCount": 1,
                "credits": [{"creditId": "opaque-credit-id"}],
            },
        },
    )

    assert usage.reset_credits_available == 1
    assert "opaque-credit-id" not in usage.model_dump_json()
    assert CodexAdapter._reset_credit_ids({"rateLimitResetCredits": {"credits": [{"creditId": "opaque-credit-id"}]}}) == ["opaque-credit-id"]


def test_usage_uses_window_exhaustion_not_ordinary_usage_flag() -> None:
    usage = CodexAdapter._usage(
        {"account": {"planType": "plus"}},
        {
            "ordinaryUsageAllowed": False,
            "rateLimits": {
                "primary": {
                    "windowDurationMins": 300,
                    "usedPercent": 32,
                    "resetsAt": 100,
                },
                "secondary": {
                    "windowDurationMins": 10080,
                    "usedPercent": 75,
                    "resetsAt": 200,
                },
            },
        },
    )

    assert usage.status == "ready"
    assert usage.allowed is False


def test_usage_without_limit_windows_is_unknown_not_blocked() -> None:
    usage = CodexAdapter._usage(
        {"account": {"planType": "plus"}},
        {"ordinaryUsageAllowed": False, "rateLimits": {}},
    )

    assert usage.status == "unknown"


def test_refresh_regenerates_usage_and_state_keeps_the_last_snapshot(
    adapter: CodexAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_profile(adapter, "account-01")
    calls: list[Path] = []
    profile_refreshes = 0

    def rpc_call(home: Path):
        nonlocal profile_refreshes
        calls.append(home)
        if home.name == "account-01":
            profile_refreshes += 1
            account = {
                "account": {
                    "type": "chatgpt",
                    "planType": "plus",
                    "email": "profile@example.com",
                    "idToken": "must-not-leak",
                }
            }
            used_percent = profile_refreshes
        else:
            account = {}
            used_percent = 0
        return (
            account,
            {
                "ordinaryUsageAllowed": True,
                "rateLimits": {
                    "primary": {
                        "windowDurationMins": 300,
                        "usedPercent": used_percent,
                    }
                },
            },
        )

    monkeypatch.setattr(adapter, "_rpc_call", rpc_call)

    first = adapter.accounts(refresh=True)[1]
    cached = adapter.accounts()[1]
    second = adapter.accounts(refresh=True)[1]

    assert first.usage and first.usage.five_hour_used == 1
    assert first.email == "profile@example.com"
    assert cached.usage and cached.usage.five_hour_used == 1
    assert cached.email == "profile@example.com"
    assert second.usage and second.usage.five_hour_used == 2
    assert second.email == "profile@example.com"
    assert len(calls) == 4


def test_identity_cache_is_cleared_for_unauthenticated_and_duplicate_profiles(
    adapter: CodexAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = add_profile(adapter, "account-01")
    logged_in = True

    def rpc_call(_home: Path):
        account = (
            {"type": "chatgpt", "email": "profile@example.com"}
            if logged_in
            else None
        )
        return {"account": account}, {"ordinaryUsageAllowed": True, "rateLimits": {}}

    monkeypatch.setattr(adapter, "_rpc_call", rpc_call)

    assert adapter.accounts(refresh=True)[1].email == "profile@example.com"

    logged_in = False
    disconnected = adapter.accounts(refresh=True)[1]
    assert disconnected.authenticated is False
    assert disconnected.email is None
    assert "account-01" not in adapter._email_cache

    logged_in = True
    assert adapter.accounts(refresh=True)[1].email == "profile@example.com"
    (profile / ".duplicate-of").write_text("default\n")
    duplicate = adapter.accounts()[1]
    assert duplicate.duplicate is True
    assert duplicate.email is None
    assert "account-01" not in adapter._email_cache


def test_destination_symlink_is_rejected(adapter: CodexAdapter, tmp_path: Path) -> None:
    home = add_profile(adapter, "account-01")
    local = home / "sessions" / "nested" / "rollout.jsonl"
    local.parent.mkdir(parents=True)
    local.write_text("session")
    external = tmp_path / "external"
    external.mkdir()
    shared = adapter.default_home / "sessions"
    shared.mkdir()
    (shared / "nested").symlink_to(external, target_is_directory=True)

    with pytest.raises(RuntimeError, match="symlink inside shared-state destination"):
        adapter.command("account-01", "new")
    assert not (external / "rollout.jsonl").exists()
    assert local.read_text() == "session"


def test_rpc_partial_line_honors_timeout_and_cleans_up(tmp_path: Path) -> None:
    pid_file = tmp_path / "pid"
    binary = tmp_path / "fake-codex"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import os, pathlib, sys, time\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "sys.stdin.readline()\n"
        "sys.stdout.write('{\\\"id\\\":2')\n"
        "sys.stdout.flush()\n"
        "time.sleep(10)\n"
    )
    binary.chmod(0o700)
    home = tmp_path / "home"
    home.mkdir()
    adapter = CodexAdapter(
        default_home=home,
        profile_root=tmp_path / "profiles",
        binary=str(binary),
        rpc_timeout=0.05,
    )

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="timed out"):
        adapter._rpc_call(home)
    assert time.monotonic() - started < 1
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_rpc_does_not_surface_server_error_details(tmp_path: Path) -> None:
    binary = tmp_path / "fake-codex"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, time\n"
        "sys.stdin.readline()\n"
        'print(\'{\\"id\\":2,\\"error\\":{\\"message\\":\\"secret-token\\"}}\', flush=True)\n'
        'print(\'{\\"id\\":3,\\"result\\":{}}\', flush=True)\n'
        "time.sleep(10)\n"
    )
    binary.chmod(0o700)
    home = tmp_path / "home"
    home.mkdir()
    adapter = CodexAdapter(
        default_home=home,
        profile_root=tmp_path / "profiles",
        binary=str(binary),
        rpc_timeout=1,
    )

    with pytest.raises(RuntimeError) as error:
        adapter._rpc_call(home)
    assert "secret-token" not in str(error.value)
