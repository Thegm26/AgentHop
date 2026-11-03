"""Exercise Ctrl-C through the real Node launcher in an isolated terminal."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pty
import select
import signal
import sys
import termios
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", ["running", "raw-key", "no-capacity", "initial-probe", "running-probe", "selection"])
def test_ctrl_c_cleans_up_launcher_and_restores_shell(tmp_path: Path, phase: str) -> None:
    metadata = json.loads((ROOT / "package.json").read_text())
    cache = tmp_path / "cache"
    runtime_bin = cache / "agenthop" / metadata["version"] / "bin"
    runtime_bin.mkdir(parents=True)
    commands = tmp_path / "commands"
    commands.mkdir()
    fake_codex = commands / "codex"
    fake_codex.write_text(f"#!{sys.executable}\n" + '''
import os, signal, sys, termios, time
from pathlib import Path
root = Path(os.environ["AUTO_PTY_ROOT"])
if "--version" in sys.argv:
    raise SystemExit(0)
if "app-server" in sys.argv:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    (root / ("rpc-" + str(os.getpid()) + ".pid")).write_text(str(os.getpid()))
    (root / "probe-ready").touch()
else:
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    attrs = termios.tcgetattr(0)
    attrs[3] &= ~(termios.ECHO | termios.ICANON)
    if os.environ["AUTO_PTY_PHASE"] == "raw-key":
        attrs[3] &= ~termios.ISIG
    termios.tcsetattr(0, termios.TCSANOW, attrs)
    (root / "child.pid").write_text(str(os.getpid()))
    (root / "child-ready").touch()
    if os.environ["AUTO_PTY_PHASE"] == "raw-key":
        while os.read(0, 1) != b"\\x03":
            pass
        raise SystemExit(130)
while True:
    time.sleep(60)
''')
    fake_codex.chmod(0o755)
    runner = tmp_path / "runner.py"
    runner.write_text('''
import os
from pathlib import Path
from agenthop.auto import AutoSupervisor
from agenthop.models import AccountModel, UsageModel
from agenthop.providers.codex import CodexAdapter
root = Path(os.environ["AUTO_PTY_ROOT"])
adapter = CodexAdapter(default_home=root / "home", profile_root=root / "profiles", binary=str(root / "commands" / "codex"))
adapter._active = lambda: "one"
adapter.launch_environment = lambda _name: {}
if os.environ["AUTO_PTY_PHASE"] == "no-capacity":
    adapter.accounts = lambda **_kwargs: [AccountModel(provider="codex", id="one", active=True, authenticated=True, usage=UsageModel(status="blocked", fiveHourUsed=100))]
if os.environ["AUTO_PTY_PHASE"] == "selection":
    profiles = []
    for index in range(5):
        home = root / "profiles" / str(index)
        home.mkdir(parents=True)
        (home / "auth.json").touch()
        profiles.append((str(index), home))
    adapter._profiles = lambda: profiles
calls = 0
def account(_name, *, refresh=False):
    global calls
    calls += 1
    phase = os.environ["AUTO_PTY_PHASE"]
    if phase == "raw-key":
        with (root / "probe-count").open("a") as count:
            count.write("probe\\n")
        # Two existing startup checks are permitted; an exit probe would hang.
        if calls > 2:
            adapter._rpc_call(root / "home")
    if phase == "initial-probe" or (phase == "running-probe" and calls > 1):
        adapter._rpc_call(root / "home")
    status = "blocked" if phase == "selection" or (phase == "no-capacity" and calls > 1) else "ready"
    return AccountModel(provider="codex", id="one", active=True, authenticated=True, usage=UsageModel(status=status, fiveHourUsed=100 if status == "blocked" else 85))
adapter.account = account
raise SystemExit(AutoSupervisor(adapter, initial_arguments=["resume", "root-42"]).run())
''')
    python = runtime_bin / "python"
    python.write_text(f"#!{sys.executable}\n" + '''
import os, runpy, sys
if sys.argv[1:2] == ["-c"]:
    raise SystemExit(0)
runpy.run_path(os.path.join(os.environ["AUTO_PTY_ROOT"], "runner.py"), run_name="__main__")
''')
    python.chmod(0o755)
    shell, terminal = pty.fork()
    if shell == 0:
        os.environ.update({
            "PATH": str(commands) + ":" + os.environ["PATH"],
            "XDG_CACHE_HOME": str(cache),
            "PYTHONPATH": str(ROOT / "backend"),
            "AUTO_PTY_ROOT": str(tmp_path),
            "AUTO_PTY_PHASE": phase,
            "PS1": "TEST_SHELL> ",
        })
        os.chdir(ROOT)
        os.execv("/bin/sh", ["sh", "-i"])
    output = bytearray()
    owned_group = None

    def read_until(marker: bytes, timeout: float = 6) -> None:
        deadline = time.monotonic() + timeout
        while marker not in output and time.monotonic() < deadline:
            if select.select([terminal], [], [], 0.05)[0]:
                output.extend(os.read(terminal, 65536))
        assert marker in output, output.decode(errors="replace")

    try:
        read_until(b"TEST_SHELL> ")
        baseline = termios.tcgetattr(terminal)
        # The shell itself stays outside the launched command's foreground group.
        os.write(terminal, b'node bin/codex-auto.js resume root-42; printf "\\nAUTO_EXIT:%s\\n" "$?"\n')
        ready = tmp_path / ("child-ready" if phase in {"running", "raw-key", "no-capacity"} else "probe-ready")
        deadline = time.monotonic() + 6
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "isolated fake CLI did not reach requested phase"
        if phase == "no-capacity":
            read_until(b"keeping Codex interactive with rotation disabled")
            assert Path("/proc", (tmp_path / "child.pid").read_text()).exists()
        if phase == "raw-key":
            while len((tmp_path / "probe-count").read_text().splitlines()) < 2 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert len((tmp_path / "probe-count").read_text().splitlines()) == 2
        if phase == "selection":
            while len(list(tmp_path.glob("rpc-*.pid"))) < 4 and time.monotonic() < deadline:
                time.sleep(0.02)
            assert len(list(tmp_path.glob("rpc-*.pid"))) == 4
        owned_group = os.tcgetpgrp(terminal)
        assert owned_group not in {shell, os.getpgrp()}
        started = time.monotonic()
        if phase == "raw-key":
            os.write(terminal, b"\x03")
        else:
            os.killpg(owned_group, signal.SIGINT)
        # A duplicate arrives while Python is unwinding/cleaning up.
        time.sleep(0.03)
        if phase != "raw-key":
            try:
                os.killpg(owned_group, signal.SIGINT)
            except ProcessLookupError:
                pass
        read_until(b"AUTO_EXIT:130", timeout=4)
        assert time.monotonic() - started < 4
        assert termios.tcgetattr(terminal) == baseline
        if phase == "raw-key":
            assert not list(tmp_path.glob("rpc-*.pid"))
            assert len((tmp_path / "probe-count").read_text().splitlines()) == 2
        for pid_file in [tmp_path / "child.pid", *tmp_path.glob("rpc-*.pid")]:
            if pid_file.exists():
                assert not Path("/proc", pid_file.read_text()).exists()
        os.write(terminal, b"printf 'NEXT_COMMAND_OK\\n'\n")
        read_until(b"NEXT_COMMAND_OK\r\n")
    finally:
        if owned_group is not None:
            try:
                os.killpg(owned_group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for pid_file in [tmp_path / "child.pid", *tmp_path.glob("rpc-*.pid")]:
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        os.kill(shell, signal.SIGKILL)
        os.waitpid(shell, 0)
        os.close(terminal)
