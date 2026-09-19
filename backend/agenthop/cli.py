from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenthop", description="Run the local AgentHop API"
    )
    parser.add_argument(
        "--host",
        choices=("127.0.0.1", "localhost", "::1"),
        default="127.0.0.1",
        help="local bind address (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8765, help="bind port (default: 8765)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="reload on source changes"
    )
    subcommands = parser.add_subparsers(dest="command")
    desktop = subcommands.add_parser("desktop", help="open the Linux desktop application")
    desktop.add_argument("--port", type=int, default=0, help="loopback port (0 chooses one)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "desktop":
        if not 0 <= args.port <= 65535:
            build_parser().error("--port must be between 0 and 65535")
        # The npm launcher runs the installed package from a private Python
        # environment, so this module's location is no longer the application
        # root. Keep the source checkout fallback for direct Python installs.
        root = Path(
            os.environ.get("AGENTHOP_PROJECT_ROOT", Path(__file__).resolve().parents[2])
        )
        shell = root / "backend" / "agenthop" / "desktop.py"
        environment = os.environ | {
            "AGENTHOP_BACKEND_PYTHON": sys.executable,
            "AGENTHOP_PROJECT_ROOT": str(root),
            "AGENTHOP_DESKTOP_PORT": str(args.port),
        }
        return subprocess.call(["/usr/bin/python3", str(shell)], env=environment)
    if not 1 <= args.port <= 65535:
        build_parser().error("--port must be between 1 and 65535")
    uvicorn.run("agenthop.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0
