from __future__ import annotations

from unittest.mock import patch

from agenthop import cli


def test_existing_server_arguments_stay_supported() -> None:
    with patch("agenthop.cli.uvicorn.run") as run:
        assert cli.main(["--reload", "--port", "8000"]) == 0
    run.assert_called_once_with("agenthop.api:app", host="127.0.0.1", port=8000, reload=True)


def test_desktop_delegates_to_system_gtk_python() -> None:
    with patch("agenthop.cli.subprocess.call", return_value=0) as call:
        assert cli.main(["desktop", "--port", "9123"]) == 0
    command = call.call_args.args[0]
    assert command[0] == "/usr/bin/python3"
    assert command[1].endswith("backend/agenthop/desktop.py")
    assert call.call_args.kwargs["env"]["AGENTHOP_DESKTOP_PORT"] == "9123"


def test_desktop_honors_packaged_project_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENTHOP_PROJECT_ROOT", str(tmp_path))
    with patch("agenthop.cli.subprocess.call", return_value=0) as call:
        assert cli.main(["desktop"]) == 0
    command = call.call_args.args[0]
    assert command[1] == str(tmp_path / "backend" / "agenthop" / "desktop.py")
    assert call.call_args.kwargs["env"]["AGENTHOP_PROJECT_ROOT"] == str(tmp_path)
