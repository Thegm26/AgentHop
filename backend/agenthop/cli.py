from __future__ import annotations

import argparse

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not 1 <= args.port <= 65535:
        build_parser().error("--port must be between 1 and 65535")
    uvicorn.run("agenthop.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0
