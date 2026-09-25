#!/usr/bin/env python3
"""Tray-first GTK shell for AgentHop; GTK is imported only after backend startup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(os.environ.get("AGENTHOP_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
BUILT_ICON = ROOT / "frontend" / "dist" / "assets" / "agenthop-mascot.png"
SOURCE_ICON = ROOT / "frontend" / "public" / "assets" / "agenthop-mascot.png"
ICON = BUILT_ICON if BUILT_ICON.is_file() else SOURCE_ICON
HTTP_TIMEOUT = 4
REFRESH_INTERVAL_SECONDS = 3_600


def _is_safe_directory(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and not stat.S_ISLNK(info.st_mode)
        and info.st_uid == os.getuid()
        and not (stat.S_IMODE(info.st_mode) & 0o077)
    )


def runtime_directory() -> Path:
    """Create a private runtime directory without trusting shared /tmp names."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(xdg) if xdg and _is_safe_directory(Path(xdg)) else Path("/tmp")
    name = "agenthop" if xdg and base != Path("/tmp") else f"agenthop-{os.getuid()}"
    candidate = base / name
    existed = candidate.exists()
    try:
        candidate.mkdir(mode=0o700, parents=False, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create AgentHop runtime directory: {exc}") from exc
    if not existed:
        candidate.chmod(0o700)
    if not _is_safe_directory(candidate):
        raise RuntimeError(f"unsafe AgentHop runtime directory: {candidate}")
    return candidate


def socket_path(runtime: Path) -> Path:
    return runtime / "desktop.sock"


def notify_existing(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        raise RuntimeError(f"unsafe AgentHop control socket: {path}")
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.5)
            client.connect(str(path))
            client.sendall(b"show")
        return True
    except OSError:
        path.unlink()
        return False


def reserve_socket(runtime: Path) -> tuple[socket.socket, Path]:
    path = socket_path(runtime)
    server = socket.socket(socket.AF_UNIX)
    try:
        server.bind(str(path))
        path.chmod(0o600)
        server.listen(2)
        server.setblocking(False)
        return server, path
    except Exception:
        server.close()
        raise


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stop_backend(backend: subprocess.Popen[object] | None) -> None:
    if backend is None or backend.poll() is not None:
        return
    backend.terminate()
    try:
        backend.wait(timeout=5)
    except subprocess.TimeoutExpired:
        backend.kill()
        backend.wait(timeout=5)


def request_json(
    url: str, method: str = "GET", body: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    with urlopen(request, timeout=HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode())


def fetch_state(base_url: str) -> dict[str, Any]:
    """Read the cached state without causing provider work."""
    return request_json(f"{base_url}/api/state")


def refresh_state(base_url: str) -> dict[str, Any]:
    """Ask the local backend to refresh usage before rebuilding the tray."""
    return request_json(f"{base_url}/api/refresh", method="POST")


def send_notification(notify_module: Any, title: str, message: str) -> None:
    """Best-effort desktop notification; GTK actions must not depend on it."""
    if notify_module is None:
        return
    try:
        notify_module.Notification.new(title, message, str(ICON)).show()
    except Exception:
        return


def activate_account(base_url: str, provider: str, account: str) -> dict[str, Any]:
    provider_path = quote(provider, safe="")
    account_path = quote(account, safe="")
    return request_json(
        f"{base_url}/api/providers/{provider_path}/accounts/{account_path}/activate",
        method="POST",
    )


def epoch_millis(value: object) -> int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return int(value * 1000 if value < 1_000_000_000_000 else value)


def expected_unblock_at(account: dict[str, Any]) -> int | None:
    usage = account.get("usage")
    if not isinstance(usage, dict):
        return None
    resets = []
    for used_key, reset_key in (
        ("fiveHourUsed", "fiveHourResetsAt"),
        ("weeklyUsed", "weeklyResetsAt"),
    ):
        used = usage.get(used_key)
        if isinstance(used, (int, float)) and used >= 100:
            reset = epoch_millis(usage.get(reset_key))
            if reset is None:
                return None
            resets.append(reset)
    return max(resets) if resets else None


def relative_time(timestamp: int | None, now_ms: int | None = None) -> str:
    if timestamp is None:
        return "unknown"
    remaining = max(0, timestamp - (now_ms if now_ms is not None else int(time.time() * 1000)))
    minutes = (remaining + 59_999) // 60_000
    days, remainder = divmod(minutes, 1_440)
    hours, minutes = divmod(remainder, 60)
    if days:
        return f"in {days}d {hours}h"
    if hours:
        return f"in {hours}h {minutes}m"
    return f"in {minutes}m"


def account_enabled(account: dict[str, Any]) -> bool:
    usage = account.get("usage")
    if not account.get("authenticated") or account.get("duplicate"):
        return False
    if not isinstance(usage, dict):
        return True
    return usage.get("status") not in {"blocked", "error"}


def account_order_group(account: dict[str, Any]) -> int:
    """Keep the tray order aligned with frontend/src/accountOrdering.ts."""
    usage = account.get("usage") if isinstance(account.get("usage"), dict) else {}
    status = usage.get("status")
    if not account.get("authenticated") or account.get("duplicate") or status == "error":
        return 3
    if status == "blocked":
        return 1 if expected_unblock_at(account) is not None else 2
    return 0


def sorted_accounts(state: dict[str, Any]) -> list[dict[str, Any]]:
    recommendation = state.get("recommendation") or {}
    recommended = (recommendation.get("provider"), recommendation.get("account"))
    accounts = [item for item in state.get("accounts", []) if isinstance(item, dict)]
    indexed = list(enumerate(accounts))

    def key(entry: tuple[int, dict[str, Any]]) -> tuple[int, int, int]:
        index, account = entry
        group = account_order_group(account)
        unblock = expected_unblock_at(account)
        if group == 0:
            recommended_rank = (
                0
                if (account.get("provider"), account.get("id")) == recommended
                else 1
            )
            return (0, recommended_rank, index)
        if group == 1 and unblock is not None:
            return (1, unblock, index)
        return (group, 0, index)

    return [account for _, account in sorted(indexed, key=key)]


def tray_label(account: dict[str, Any], now_ms: int | None = None) -> str:
    name = str(account.get("id", "unknown account"))
    usage = account.get("usage") if isinstance(account.get("usage"), dict) else {}
    if account.get("active"):
        return f"✓ {name} — active"
    if usage.get("status") == "blocked":
        unblock = expected_unblock_at(account)
        detail = relative_time(unblock, now_ms) if unblock is not None else "unavailable"
        return f"{name} — blocked · {detail}"
    if account.get("duplicate"):
        return f"{name} — duplicate"
    if not account.get("authenticated"):
        return f"{name} — disconnected"
    if usage.get("status") == "error":
        return f"{name} — error"
    if not account_enabled(account):
        return f"{name} — unavailable"
    status = usage.get("status") if isinstance(usage, dict) else "unknown"
    return f"{name} — {status if status in {'ready', 'close'} else 'available'}"


def wait_for_backend(port: int, backend: subprocess.Popen[object]) -> bool:
    for _ in range(50):
        if backend.poll() is not None:
            return False
        try:
            request_json(f"http://127.0.0.1:{port}/api/health")
            return True
        except (OSError, ValueError, json.JSONDecodeError):
            time.sleep(0.1)
    return False


def main() -> int:
    backend: subprocess.Popen[object] | None = None
    server: socket.socket | None = None
    control: Path | None = None
    owns_control_socket = False
    try:
        runtime = runtime_directory()
        control = socket_path(runtime)
        if notify_existing(control):
            return 0
        server, control = reserve_socket(runtime)
        owns_control_socket = True
        dist = ROOT / "frontend" / "dist" / "index.html"
        if not dist.is_file():
            print(
                "Frontend build is missing. Run `npm --prefix frontend run build`.",
                file=sys.stderr,
            )
            return 1
        port = int(os.environ.get("AGENTHOP_DESKTOP_PORT", "0")) or free_port()
        python = os.environ.get("AGENTHOP_BACKEND_PYTHON", sys.executable)
        environment = os.environ | {"AGENTHOP_FRONTEND_DIST": str(dist.parent)}
        backend = subprocess.Popen(
            [
                python,
                "-m",
                "uvicorn",
                "agenthop.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
            env=environment,
        )
        if not wait_for_backend(port, backend):
            detail = (
                "port may already be in use"
                if os.environ.get("AGENTHOP_DESKTOP_PORT")
                else "check the project virtual environment"
            )
            print(f"AgentHop backend did not start ({detail}).", file=sys.stderr)
            return 1
        base_url = f"http://127.0.0.1:{port}"

        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator, GLib, Gtk, WebKit2

        try:
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify

            Notify.init("AgentHop")
        except (ImportError, ValueError):
            Notify = None

        indicator = AppIndicator.Indicator.new(
            "agenthop", str(ICON), AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        window: Any = None
        view: Any = None
        tray_state: dict[str, Any] = {}
        tray_error: str | None = None
        tray_loading = True
        switching_account: str | None = None
        shutting_down = False
        operation_lock = threading.Lock()
        operation_inflight = False

        def notify(title: str, message: str) -> None:
            send_notification(Notify, title, message)

        def show_dashboard(*_args: object) -> None:
            nonlocal window, view
            if shutting_down:
                return
            if window is None:
                window = Gtk.Window(title="AgentHop")
                window.set_default_size(1180, 790)
                if ICON.exists():
                    window.set_icon_from_file(str(ICON))
                view = WebKit2.WebView()
                view.load_uri(f"{base_url}/")
                window.add(view)
                window.connect("delete-event", lambda *_inner: (window.hide(), True)[1])
            window.show_all()
            window.present()

        def operation_active() -> bool:
            with operation_lock:
                return operation_inflight

        def start_operation(worker: Any, name: str) -> bool:
            """Run network work once; worker code must not touch GTK."""
            nonlocal operation_inflight
            with operation_lock:
                if operation_inflight or shutting_down:
                    return False
                operation_inflight = True
            threading.Thread(target=worker, name=name, daemon=True).start()
            return True

        def finish_operation() -> None:
            nonlocal operation_inflight
            with operation_lock:
                operation_inflight = False

        def rebuild_menu() -> None:
            menu = Gtk.Menu()
            accounts = sorted_accounts(tray_state)
            best = next((item for item in accounts if account_enabled(item)), None)
            busy = operation_active()
            if tray_loading:
                summary_label = "Loading accounts…"
            elif switching_account:
                summary_label = f"Switching to {switching_account}…"
            else:
                summary_label = (
                    f"Available profile: {best.get('id')}"
                    if best
                    else "No account currently available"
                )
            summary = Gtk.MenuItem(label=summary_label)
            summary.set_sensitive(False)
            menu.append(summary)
            if tray_error:
                error = Gtk.MenuItem(label=f"Status error: {tray_error}")
                error.set_sensitive(False)
                menu.append(error)
            menu.append(Gtk.SeparatorMenuItem())
            for account in accounts:
                item = Gtk.MenuItem(label=tray_label(account))
                item.set_sensitive(account_enabled(account) and not busy)
                if account_enabled(account):
                    item.connect("activate", switch_account, account)
                menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())
            refresh = Gtk.MenuItem(
                label="Refreshing…" if busy else "Refresh accounts"
            )
            refresh.set_sensitive(not busy)
            refresh.connect("activate", refresh_accounts)
            menu.append(refresh)
            dashboard = Gtk.MenuItem(label="Open dashboard…")
            dashboard.connect("activate", show_dashboard)
            menu.append(dashboard)
            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", quit_desktop)
            menu.append(quit_item)
            menu.show_all()
            indicator.set_menu(menu)

        def publish_cached_accounts(
            state: dict[str, Any] | None, error: str | None
        ) -> bool:
            """GTK callback for the initial cached-state request."""
            nonlocal tray_state, tray_error, tray_loading
            finish_operation()
            if shutting_down:
                return False
            tray_loading = False
            if state is not None:
                tray_state = state
                tray_error = None
            elif error:
                tray_error = error
                notify("AgentHop", f"Could not load accounts: {error}")
            rebuild_menu()
            return False

        def finish_refresh(
            state: dict[str, Any] | None, error: str | None
        ) -> bool:
            """GTK callback for a manual live refresh."""
            nonlocal tray_state, tray_error
            finish_operation()
            if shutting_down:
                return False
            if state is not None:
                tray_state = state
                tray_error = None
            elif error:
                tray_error = error
                notify("AgentHop", f"Could not refresh accounts: {error}")
            rebuild_menu()
            return False

        def refresh_accounts(*_args: object) -> bool:
            def refresh_worker() -> None:
                try:
                    state = refresh_state(base_url)
                    GLib.idle_add(finish_refresh, state, None)
                except Exception as exc:  # Network calls must never kill the tray worker.
                    GLib.idle_add(finish_refresh, None, str(exc))

            if start_operation(refresh_worker, "agenthop-refresh"):
                rebuild_menu()
            return False

        def refresh_accounts_hourly() -> bool:
            """Refresh tray usage once per hour without overlapping work."""
            refresh_accounts()
            return not shutting_down

        def finish_switch(
            account_name: str,
            state: dict[str, Any] | None,
            activation_error: str | None,
            state_error: str | None,
        ) -> bool:
            """GTK callback for an account activation and cached-state update."""
            nonlocal tray_state, tray_error, switching_account
            finish_operation()
            if shutting_down:
                return False
            switching_account = None
            if activation_error:
                tray_error = activation_error
                notify("AgentHop", f"Could not switch account: {activation_error}")
            else:
                notify("AgentHop", f"Switched to {account_name}")
                if state is not None:
                    tray_state = state
                    tray_error = None
                elif state_error:
                    tray_error = state_error
                    notify("AgentHop", f"Could not load accounts: {state_error}")
            rebuild_menu()
            return False

        def switch_account(_item: object, account: dict[str, Any]) -> None:
            nonlocal switching_account
            account_name = str(account.get("id", "account"))
            provider = str(account.get("provider", ""))

            def switch_worker() -> None:
                try:
                    activate_account(base_url, provider, account_name)
                except Exception as exc:  # Keep failed HTTP work outside the GTK loop.
                    GLib.idle_add(
                        finish_switch, account_name, None, str(exc), None
                    )
                    return
                try:
                    state = fetch_state(base_url)
                    GLib.idle_add(finish_switch, account_name, state, None, None)
                except Exception as exc:
                    GLib.idle_add(finish_switch, account_name, None, None, str(exc))

            if not start_operation(switch_worker, "agenthop-switch"):
                return
            switching_account = account_name
            rebuild_menu()

        def start_initial_load() -> None:
            def startup_worker() -> None:
                try:
                    cached = fetch_state(base_url)
                    GLib.idle_add(publish_cached_accounts, cached, None)
                except Exception as exc:
                    GLib.idle_add(publish_cached_accounts, None, str(exc))

            start_operation(startup_worker, "agenthop-startup")

        def quit_desktop(*_args: object) -> None:
            nonlocal shutting_down
            shutting_down = True
            Gtk.main_quit()

        def accept_control(*_args: object) -> bool:
            if shutting_down:
                return False
            try:
                connection, _ = server.accept()
                with connection:
                    if connection.recv(32) == b"show":
                        show_dashboard()
            except BlockingIOError:
                pass
            return True

        # Start hidden: the lightweight tray state is available without creating
        # a WebKit window. The dashboard is created only from its menu item or a
        # second launcher invocation.
        rebuild_menu()
        start_initial_load()
        GLib.timeout_add_seconds(REFRESH_INTERVAL_SECONDS, refresh_accounts_hourly)
        GLib.io_add_watch(server.fileno(), GLib.IO_IN, accept_control)
        Gtk.main()
        return 0
    except (
        ImportError,
        KeyboardInterrupt,
        RuntimeError,
        ValueError,
        OSError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"AgentHop desktop failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if server is not None:
            server.close()
        if owns_control_socket and control is not None:
            control.unlink(missing_ok=True)
        stop_backend(backend)


if __name__ == "__main__":
    raise SystemExit(main())
