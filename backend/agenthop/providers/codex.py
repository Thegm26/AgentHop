from __future__ import annotations

import concurrent.futures
import filecmp
import hashlib
import json
import os
import queue
import re
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from agenthop import __version__
from agenthop.models import AccountModel, ProviderModel, SessionModel, UsageModel
from agenthop.providers.base import (
    DuplicateAccountError,
    ProviderAdapter,
    UnknownAccountError,
)

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
FIVE_HOURS = 300
ONE_WEEK = 10080
SHARED_STATE_DIRS = (
    "sessions",
    "archived_sessions",
    "shell_snapshots",
    "thread-writer-locks",
)
DUPLICATE_MARKER = ".duplicate-of"
ACTIVE_MARKER = ".active"


class CodexAdapter(ProviderAdapter):
    id = "codex"
    name = "OpenAI Codex"

    def __init__(
        self,
        *,
        default_home: Path | None = None,
        profile_root: Path | None = None,
        binary: str | None = None,
        rpc_timeout: float = 5.0,
    ) -> None:
        home = Path.home()
        self.default_home = (default_home or home / ".codex").expanduser()
        self.profile_root = (profile_root or home / ".codex-profiles").expanduser()
        self.binary = binary or shutil.which("codex")
        self.rpc_timeout = rpc_timeout
        self._migration_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._usage_cache: dict[str, UsageModel] = {}
        self._email_cache: dict[str, str] = {}

    def provider(self) -> ProviderModel:
        return ProviderModel(
            id=self.id,
            name=self.name,
            available=self.binary is not None,
            error=None if self.binary else "codex executable not found in PATH",
        )

    @staticmethod
    def _validate_account(name: str) -> str:
        if name == "default":
            return name
        if not NAME_RE.fullmatch(name):
            raise ValueError("invalid account name")
        return name

    def _ensure_roots(self) -> None:
        if self.default_home.is_symlink() or self.profile_root.is_symlink():
            raise RuntimeError("Codex state roots must not be symbolic links")
        self.default_home.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.profile_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.default_home.chmod(0o700)
        self.profile_root.chmod(0o700)

    def _profiles(self) -> list[tuple[str, Path]]:
        self._ensure_roots()
        profiles = [("default", self.default_home)]
        profiles.extend(
            (path.name, path)
            for path in sorted(
                self.profile_root.iterdir(), key=lambda item: item.name.lower()
            )
            if path.is_dir() and not path.is_symlink() and NAME_RE.fullmatch(path.name)
        )
        return profiles

    def _home(self, name: str) -> Path:
        self._validate_account(name)
        home = self.default_home if name == "default" else self.profile_root / name
        if not home.is_dir() or home.is_symlink():
            raise UnknownAccountError(f"unknown account: {name}")
        if (home / DUPLICATE_MARKER).is_file():
            raise DuplicateAccountError(f"account is marked as a duplicate: {name}")
        return home

    def _active(self) -> str:
        try:
            name = (
                (self.profile_root / ACTIVE_MARKER).read_text(encoding="utf-8").strip()
            )
            self._home(name)
            return name
        except (OSError, ValueError, LookupError):
            return "default"

    def activate(self, account: str) -> None:
        self._home(account)
        self._ensure_roots()
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.profile_root,
                prefix=".active.",
                delete=False,
            ) as handle:
                temporary = handle.name
                os.fchmod(handle.fileno(), 0o600)
                handle.write(account + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.profile_root / ACTIVE_MARKER)
            temporary = None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)

    def onboard(self, account: str) -> str:
        self._validate_account(account)
        if account == "default":
            raise ValueError("default is reserved for the existing Codex home")
        if not self.binary:
            raise RuntimeError("codex executable not found in PATH")
        self._ensure_roots()
        home = self.profile_root / account
        try:
            home.mkdir(mode=0o700)
        except FileExistsError as exc:
            raise DuplicateAccountError(f"account already exists: {account}") from exc
        return " ".join(
            [
                "env",
                f'CODEX_HOME="$HOME/.codex-profiles/{account}"',
                "codex",
                "-c",
                shlex.quote('cli_auth_credentials_store="file"'),
                "login",
            ]
        )

    def _rpc_call(self, home: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self.binary:
            raise RuntimeError("codex executable not found in PATH")
        env = os.environ.copy()
        env["CODEX_HOME"] = str(home)
        proc = subprocess.Popen(
            [self.binary, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        requests = (
            {
                "method": "initialize",
                "id": 1,
                "params": {
                    "clientInfo": {
                        "name": "agenthop",
                        "title": "AgentHop",
                        "version": __version__,
                    }
                },
            },
            {"method": "initialized", "params": {}},
            {"method": "account/read", "id": 2, "params": {"refreshToken": False}},
            {
                "method": "account/rateLimits/read",
                "id": 3,
                "params": {"excludeResetCreditDetails": True},
            },
        )
        replies: dict[int, dict[str, Any]] = {}
        lines: queue.Queue[bytes | None] = queue.Queue()

        def read_lines() -> None:
            assert proc.stdout is not None
            while True:
                line = proc.stdout.readline(1024 * 1024 + 1)
                lines.put(line or None)
                if not line:
                    return

        reader = threading.Thread(
            target=read_lines, name="agenthop-codex-rpc", daemon=True
        )
        try:
            assert proc.stdin is not None and proc.stdout is not None
            payload = "\n".join(
                json.dumps(item, separators=(",", ":")) for item in requests
            )
            proc.stdin.write((payload + "\n").encode())
            proc.stdin.flush()
            reader.start()
            deadline = time.monotonic() + self.rpc_timeout
            while time.monotonic() < deadline and not {2, 3}.issubset(replies):
                try:
                    line = lines.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if line is None:
                    break
                if len(line) > 1024 * 1024:
                    raise RuntimeError(
                        "Codex app-server response exceeded the size limit"
                    )
                try:
                    message = json.loads(line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(message.get("id"), int):
                    replies[message["id"]] = message
            if not {2, 3}.issubset(replies):
                raise RuntimeError("Codex app-server timed out")
            for request_id in (2, 3):
                if "error" in replies[request_id]:
                    raise RuntimeError("Codex app-server request failed")
            return replies[2].get("result", {}), replies[3].get("result", {})
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1)
            if reader.is_alive():
                reader.join(timeout=1)

    @staticmethod
    def _usage(account: dict[str, Any], limits: dict[str, Any]) -> UsageModel:
        snapshot = limits.get("rateLimits") or {}
        windows: dict[int, dict[str, Any]] = {}
        for key in ("primary", "secondary"):
            window = snapshot.get(key)
            if isinstance(window, dict) and window.get("windowDurationMins") in (
                FIVE_HOURS,
                ONE_WEEK,
            ):
                windows[window["windowDurationMins"]] = window
        five, week = windows.get(FIVE_HOURS, {}), windows.get(ONE_WEEK, {})
        values = [
            value
            for value in (five.get("usedPercent"), week.get("usedPercent"))
            if isinstance(value, int)
        ]
        allowed = limits.get("ordinaryUsageAllowed")
        if allowed is False or any(value >= 100 for value in values):
            status = "blocked"
        elif max(values, default=0) >= 95:
            status = "critical"
        elif max(values, default=0) >= 80:
            status = "close"
        else:
            status = "ready"
        account_data = account.get("account") or {}
        return UsageModel(
            plan=snapshot.get("planType") or account_data.get("planType"),
            fiveHourUsed=five.get("usedPercent"),
            fiveHourResetsAt=five.get("resetsAt"),
            weeklyUsed=week.get("usedPercent"),
            weeklyResetsAt=week.get("resetsAt"),
            allowed=allowed if isinstance(allowed, bool) else None,
            status=status,
        )

    def _inspect(
        self, name: str, home: Path, active: str, refresh: bool
    ) -> AccountModel:
        duplicate = (home / DUPLICATE_MARKER).is_file()
        authenticated = (home / "auth.json").is_file()
        with self._cache_lock:
            if authenticated and not duplicate:
                usage = self._usage_cache.get(name)
                email = self._email_cache.get(name)
            else:
                usage = None
                email = None
        if refresh and not duplicate:
            try:
                account, limits = self._rpc_call(home)
                account_data = account.get("account")
                authenticated = isinstance(account_data, dict)
                usage = (
                    self._usage(account, limits)
                    if authenticated
                    else UsageModel(status="error", error="not logged in")
                )
                refreshed_email = (
                    account_data.get("email")
                    if isinstance(account_data, dict)
                    else None
                )
            except (
                AttributeError,
                OSError,
                RuntimeError,
                subprocess.SubprocessError,
                TypeError,
                ValueError,
            ) as exc:
                usage = UsageModel(status="error", error=str(exc))
                refreshed_email = None
            if authenticated:
                with self._cache_lock:
                    self._usage_cache[name] = usage
                    if isinstance(refreshed_email, str) and refreshed_email:
                        self._email_cache[name] = refreshed_email
                    email = self._email_cache.get(name)
            else:
                with self._cache_lock:
                    self._usage_cache.pop(name, None)
                    self._email_cache.pop(name, None)
                email = None
        elif not authenticated or duplicate:
            with self._cache_lock:
                self._usage_cache.pop(name, None)
                self._email_cache.pop(name, None)
            email = None
        return AccountModel(
            provider=self.id,
            id=name,
            active=name == active,
            authenticated=authenticated,
            duplicate=duplicate,
            email=email,
            usage=usage,
        )

    def accounts(self, *, refresh: bool = False) -> list[AccountModel]:
        profiles = self._profiles()
        active = self._active()
        if not refresh:
            return [self._inspect(name, home, active, False) for name, home in profiles]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(4, len(profiles))
        ) as pool:
            return list(
                pool.map(lambda pair: self._inspect(*pair, active, True), profiles)
            )

    @staticmethod
    def _conflict_target(target: Path, source: Path) -> Path:
        with source.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()[:12]
        return target.with_name(f"{target.name}.agenthop-conflict-{digest}")

    @staticmethod
    def _same_file_contents(first: Path, second: Path) -> bool:
        return (
            first.is_file()
            and second.is_file()
            and filecmp.cmp(first, second, shallow=False)
        )

    @staticmethod
    def _assert_safe_destination(root: Path, target: Path) -> None:
        relative = target.relative_to(root)
        current = root
        for part in relative.parts:
            current /= part
            if current.is_symlink():
                raise RuntimeError(
                    f"symlink inside shared-state destination: {current}"
                )

    def _merge_directory(self, source: Path, destination: Path) -> dict[Path, Path]:
        migrated: dict[Path, Path] = {}
        if destination.is_symlink():
            raise RuntimeError(f"unsafe shared-state destination: {destination}")
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.chmod(0o700)
        if not source.exists():
            return migrated
        if not source.is_dir() or source.is_symlink():
            raise RuntimeError(f"unsafe shared-state source: {source}")
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            target = destination / relative
            if item.is_symlink():
                raise RuntimeError(f"symlink inside shared state: {item}")
            if item.is_dir():
                self._assert_safe_destination(destination, target)
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                target.chmod(0o700)
                continue
            if not item.is_file():
                raise RuntimeError(f"non-regular file inside shared state: {item}")
            self._assert_safe_destination(destination, target.parent)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if target.exists():
                if target.is_symlink():
                    raise RuntimeError(
                        f"symlink inside shared-state destination: {target}"
                    )
                if self._same_file_contents(item, target):
                    migrated[item] = target
                    continue
                target = self._conflict_target(target, item)
                if target.exists():
                    if target.is_symlink():
                        raise RuntimeError(
                            f"symlink inside shared-state destination: {target}"
                        )
                    if self._same_file_contents(item, target):
                        migrated[item] = target
                        continue
                    raise RuntimeError(f"unresolved shared-state collision: {target}")
            shutil.copy2(item, target)
            target.chmod(0o600)
            migrated[item] = target
        return migrated

    def _share_profile_state(self, home: Path) -> dict[Path, Path]:
        migrated: dict[Path, Path] = {}
        for name in SHARED_STATE_DIRS:
            shared = self.default_home / name
            if shared.is_symlink():
                raise RuntimeError(f"unsafe shared-state destination: {shared}")
            shared.mkdir(mode=0o700, parents=True, exist_ok=True)
            if home == self.default_home:
                continue
            local = home / name
            if local.is_symlink():
                if local.resolve() != shared.resolve():
                    raise RuntimeError(f"unexpected shared-state link: {local}")
                continue
            migrated.update(self._merge_directory(local, shared))
            backup = home / f".{name}.agenthop-migration"
            if backup.exists() or backup.is_symlink():
                raise RuntimeError(f"migration backup already exists: {backup}")
            if local.exists():
                local.rename(backup)
            try:
                local.symlink_to(shared, target_is_directory=True)
            except Exception:
                if backup.exists():
                    backup.rename(local)
                raise
            if backup.exists():
                shutil.rmtree(backup)
        return migrated

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return '"' + value.replace('"', '""') + '"'

    def _merge_thread_index(self, home: Path, migrated: dict[Path, Path]) -> None:
        source_path = home / "state_5.sqlite"
        destination_path = self.default_home / "state_5.sqlite"
        if home == self.default_home or not source_path.is_file():
            return
        if source_path.is_symlink() or destination_path.is_symlink():
            raise RuntimeError("Codex session databases must not be symbolic links")
        if destination_path.exists() and os.path.samefile(
            source_path, destination_path
        ):
            raise RuntimeError("profile and shared session databases must be distinct")
        if not destination_path.exists():
            self._seed_thread_index(home, source_path, destination_path, migrated)
            return
        try:
            with (
                sqlite3.connect(source_path, timeout=5) as source,
                sqlite3.connect(destination_path, timeout=5) as destination,
            ):
                source_columns = {
                    row[1] for row in source.execute("PRAGMA table_info(threads)")
                }
                destination_columns = [
                    row[1] for row in destination.execute("PRAGMA table_info(threads)")
                ]
                columns = [
                    column for column in destination_columns if column in source_columns
                ]
                if "id" not in columns or "rollout_path" not in columns:
                    return
                quoted = ", ".join(self._quote_identifier(column) for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rollout_index = columns.index("rollout_path")
                updates = ", ".join(
                    f"{self._quote_identifier(column)} = excluded.{self._quote_identifier(column)}"
                    for column in columns
                    if column != "id"
                )
                conflict = (
                    f' ON CONFLICT("id") DO UPDATE SET {updates}'
                    if updates
                    else ' ON CONFLICT("id") DO NOTHING'
                )
                if "updated_at" in columns and updates:
                    conflict += ' WHERE excluded."updated_at" > threads."updated_at"'
                for original in source.execute(f"SELECT {quoted} FROM threads"):
                    row = list(original)
                    try:
                        original_path = Path(row[rollout_index])
                    except TypeError:
                        original_path = None
                    if original_path in migrated:
                        row[rollout_index] = str(migrated[original_path])
                    elif original_path is not None:
                        try:
                            relative = original_path.relative_to(home)
                            row[rollout_index] = str(self.default_home / relative)
                        except ValueError:
                            pass
                    destination.execute(
                        f"INSERT INTO threads ({quoted}) VALUES ({placeholders}){conflict}",
                        row,
                    )
        except sqlite3.Error as exc:
            raise RuntimeError(f"failed to merge Codex session index: {exc}") from exc

    def _seed_thread_index(
        self,
        home: Path,
        source_path: Path,
        destination_path: Path,
        migrated: dict[Path, Path],
    ) -> None:
        with tempfile.NamedTemporaryFile(
            dir=destination_path.parent,
            prefix=f".{destination_path.name}.agenthop-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
        try:
            with (
                sqlite3.connect(source_path, timeout=5) as source,
                sqlite3.connect(temporary) as destination,
            ):
                source.backup(destination)
                columns = {
                    row[1] for row in destination.execute("PRAGMA table_info(threads)")
                }
                if {"id", "rollout_path"}.issubset(columns):
                    rows = destination.execute(
                        "SELECT id, rollout_path FROM threads"
                    ).fetchall()
                    for thread_id, value in rows:
                        try:
                            original = Path(value)
                        except TypeError:
                            continue
                        target = migrated.get(original)
                        if target is None:
                            try:
                                target = self.default_home / original.relative_to(home)
                            except (TypeError, ValueError):
                                continue
                        destination.execute(
                            "UPDATE threads SET rollout_path = ? WHERE id = ?",
                            (str(target), thread_id),
                        )
            temporary.chmod(0o600)
            os.replace(temporary, destination_path)
        except sqlite3.Error as exc:
            raise RuntimeError(f"failed to seed Codex session index: {exc}") from exc
        finally:
            temporary.unlink(missing_ok=True)

    def _prepare_shared_state(self) -> None:
        with self._migration_lock:
            for _, home in self._profiles():
                migrated = self._share_profile_state(home)
                self._merge_thread_index(home, migrated)

    def sessions(self) -> list[SessionModel]:
        database = self.default_home / "state_5.sqlite"
        if not database.is_file():
            return []
        if database.is_symlink():
            raise RuntimeError("Codex session database must not be a symbolic link")
        try:
            uri = database.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=2) as connection:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(threads)")
                }
                if "id" not in columns:
                    return []
                title = "title" if "title" in columns else "NULL"
                updated = "updated_at" if "updated_at" in columns else "NULL"
                order = "updated_at DESC" if "updated_at" in columns else "rowid DESC"
                rows = connection.execute(
                    f"SELECT id, {title}, {updated} FROM threads ORDER BY {order} LIMIT 100"
                ).fetchall()
            sessions = []
            for thread_id, title_value, updated_at in rows:
                if not isinstance(thread_id, str) or not SESSION_RE.fullmatch(
                    thread_id
                ):
                    continue
                title = title_value[:500] if isinstance(title_value, str) else None
                updated = updated_at if isinstance(updated_at, int) else None
                sessions.append(
                    SessionModel(
                        provider=self.id, id=thread_id, title=title, updatedAt=updated
                    )
                )
            return sessions
        except sqlite3.Error as exc:
            raise RuntimeError(f"failed to read Codex sessions: {exc}") from exc

    def command(self, account: str, mode: str, session_id: str | None = None) -> str:
        home = self._home(account)
        if mode not in {"new", "resume"}:
            raise ValueError("mode must be 'new' or 'resume'")
        if mode == "new" and session_id is not None:
            raise ValueError("sessionId is only valid in resume mode")
        if session_id is not None and not SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid sessionId")
        self._prepare_shared_state()
        executable = self.binary or "codex"
        parts = [
            f"CODEX_HOME={shlex.quote(str(home))}",
            f"CODEX_SQLITE_HOME={shlex.quote(str(self.default_home))}",
            shlex.quote(executable),
        ]
        if mode == "resume":
            parts.extend(
                ["resume", shlex.quote(session_id) if session_id else "--last"]
            )
        return " ".join(parts)
