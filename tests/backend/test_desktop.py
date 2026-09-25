from __future__ import annotations

import socket
import stat
from unittest.mock import Mock

import pytest

from agenthop import desktop


def test_control_socket_allows_one_owner(tmp_path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    server, path = desktop.reserve_socket(runtime)
    try:
        assert desktop.notify_existing(path) is True
        connection, _ = server.accept()
        with connection:
            assert connection.recv(32) == b"show"
    finally:
        server.close()
        path.unlink(missing_ok=True)


def test_free_port_is_bindable() -> None:
    port = desktop.free_port()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_runtime_falls_back_to_private_user_tmp_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "unsafe"))
    monkeypatch.setattr(
        desktop,
        "Path",
        lambda value: tmp_path if value == "/tmp" else __import__("pathlib").Path(value),
    )
    runtime = desktop.runtime_directory()
    assert runtime.name == f"agenthop-{desktop.os.getuid()}"
    assert stat.S_IMODE(runtime.stat().st_mode) == 0o700


def test_runtime_rejects_an_unsafe_existing_directory(tmp_path, monkeypatch) -> None:
    unsafe = tmp_path / "agenthop"
    unsafe.mkdir(mode=0o755)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    with pytest.raises(RuntimeError, match="unsafe"):
        desktop.runtime_directory()


def test_stop_backend_terminates_then_kills_only_when_needed() -> None:
    graceful = Mock()
    graceful.poll.side_effect = [None, 0]
    desktop.stop_backend(graceful)
    graceful.terminate.assert_called_once_with()
    graceful.wait.assert_called_once_with(timeout=5)
    graceful.kill.assert_not_called()

    stubborn = Mock()
    stubborn.poll.return_value = None
    stubborn.wait.side_effect = [desktop.subprocess.TimeoutExpired("agenthop", 5), None]
    desktop.stop_backend(stubborn)
    stubborn.kill.assert_called_once_with()


def test_account_sorting_labels_and_expected_unblock() -> None:
    state = {
        "recommendation": {"provider": "codex", "account": "best"},
        "accounts": [
            {
                "provider": "codex",
                "id": "blocked-later",
                "authenticated": True,
                "usage": {
                    "status": "blocked",
                    "fiveHourUsed": 100,
                    "fiveHourResetsAt": 1_700_000_000,
                    "weeklyUsed": 100,
                    "weeklyResetsAt": 1_700_100_000,
                },
            },
            {
                "provider": "codex",
                "id": "other",
                "authenticated": True,
                "usage": {"status": "close", "allowed": True},
            },
            {
                "provider": "codex",
                "id": "best",
                "active": True,
                "authenticated": True,
                "usage": {"status": "ready", "allowed": True},
            },
            {
                "provider": "codex",
                "id": "blocked-sooner",
                "authenticated": True,
                "usage": {
                    "status": "blocked",
                    "fiveHourUsed": 100,
                    "fiveHourResetsAt": 1_700_050_000,
                },
            },
        ],
    }
    accounts = desktop.sorted_accounts(state)
    assert [account["id"] for account in accounts] == [
        "best",
        "other",
        "blocked-sooner",
        "blocked-later",
    ]
    assert desktop.expected_unblock_at(accounts[-1]) == 1_700_100_000_000
    assert desktop.tray_label(accounts[0]) == "✓ best — active"
    assert (
        desktop.tray_label(accounts[-1], now_ms=1_700_000_000_000)
        == "blocked-later — blocked · in 1d 3h"
    )


def test_tray_order_uses_window_status_not_ordinary_usage_flag() -> None:
    state = {
        "accounts": [
            {
                "id": "disallowed",
                "authenticated": True,
                "usage": {
                    "status": "ready",
                    "allowed": False,
                    "fiveHourUsed": 32,
                    "fiveHourResetsAt": 1_900_000_000,
                },
            },
            {"id": "error", "authenticated": True, "usage": {"status": "error"}},
            {
                "id": "blocked",
                "authenticated": True,
                "usage": {
                    "status": "blocked",
                    "fiveHourUsed": 100,
                    "fiveHourResetsAt": 1_800_000_000,
                },
            },
        ],
    }
    accounts = desktop.sorted_accounts(state)
    assert [account["id"] for account in accounts] == ["disallowed", "blocked", "error"]
    assert desktop.tray_label(accounts[0]) == "disallowed — ready"
    assert desktop.tray_label(accounts[2]) == "error — error"


def test_request_helpers_use_local_json_post_and_encoded_path(monkeypatch) -> None:
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"active": true}'

    def fake_urlopen(request, timeout):
        seen.append((request, timeout))
        return Response()

    monkeypatch.setattr(desktop, "urlopen", fake_urlopen)
    result = desktop.activate_account("http://127.0.0.1:9000", "open ai", "account/01")
    assert result == {"active": True}
    request, timeout = seen[0]
    assert request.get_method() == "POST"
    assert request.full_url.endswith("/open%20ai/accounts/account%2F01/activate")
    assert request.get_header("Accept") == "application/json"
    assert timeout == desktop.HTTP_TIMEOUT


def test_state_helpers_use_the_read_and_refresh_endpoints(monkeypatch) -> None:
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"accounts": []}'

    def fake_urlopen(request, timeout):
        seen.append((request, timeout))
        return Response()

    monkeypatch.setattr(desktop, "urlopen", fake_urlopen)

    assert desktop.fetch_state("http://127.0.0.1:9000") == {"accounts": []}
    assert desktop.refresh_state("http://127.0.0.1:9000") == {"accounts": []}
    assert [request.get_method() for request, _ in seen] == ["GET", "POST"]
    assert [request.full_url for request, _ in seen] == [
        "http://127.0.0.1:9000/api/state",
        "http://127.0.0.1:9000/api/refresh",
    ]


def test_send_notification_ignores_desktop_notification_failures() -> None:
    notification = Mock()
    notification.show.side_effect = RuntimeError("notification daemon unavailable")
    notify_module = Mock()
    notify_module.Notification.new.return_value = notification

    desktop.send_notification(notify_module, "AgentHop", "Switched to work")

    notify_module.Notification.new.assert_called_once_with(
        "AgentHop", "Switched to work", str(desktop.ICON)
    )
    notification.show.assert_called_once_with()
