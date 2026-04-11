#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pc_e500_supervisor_client import DEFAULT_SOCKET, send_request

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PC-E500 experiment supervisor client")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET, help=f"unix socket path (default: {DEFAULT_SOCKET})")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON responses")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="query daemon/device status")
    subparsers.add_parser("stream-on", help="send F1 through the supervisor")
    subparsers.add_parser("stream-off", help="send F0 through the supervisor")
    subparsers.add_parser("stream-status", help="send F? through the supervisor")
    stream_config = subparsers.add_parser("stream-config", help="program FT stream cfg/mode through the supervisor")
    stream_config.add_argument("--cfg", required=True, type=lambda value: int(value, 0), help="FT_STREAM_CFG value")
    stream_config.add_argument("--mode", type=lambda value: int(value, 0), help="optional FT_STREAM_MODE value")
    subparsers.add_parser("arm-safe", help="program the safe supervisor image")

    debug_echo_short = subparsers.add_parser(
        "debug-echo-short",
        help="program the short echo payload and wait for OK\\r\\n after CALL &10100",
    )
    debug_echo_short.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="seconds to wait for OK\\r\\n after programming (default: 10)",
    )

    wait_ready = subparsers.add_parser("wait-ready", help="wait for XR,READY from the calculator")
    wait_ready.add_argument("--timeout", type=float, default=30.0, help="seconds to wait (default: 30)")

    run = subparsers.add_parser("run", help="run an experiment script")
    run.add_argument("script", type=Path, help="path to the experiment script")
    run.add_argument("script_args", nargs=argparse.REMAINDER, help="extra args forwarded to the experiment script after --")

    subparsers.add_parser("shutdown", help="stop the daemon")
    return parser

def build_request(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "status":
        return {"action": "status"}
    if args.command == "stream-on":
        return {"action": "stream_on"}
    if args.command == "stream-off":
        return {"action": "stream_off"}
    if args.command == "stream-status":
        return {"action": "stream_status"}
    if args.command == "stream-config":
        payload: dict[str, object] = {"action": "stream_config", "cfg": args.cfg}
        if args.mode is not None:
            payload["mode"] = args.mode
        return payload
    if args.command == "arm-safe":
        return {"action": "arm_safe"}
    if args.command == "debug-echo-short":
        return {"action": "debug_echo_short", "timeout_s": args.timeout}
    if args.command == "wait-ready":
        return {"action": "wait_ready", "timeout_s": args.timeout}
    if args.command == "run":
        script_args = list(args.script_args)
        if script_args and script_args[0] == "--":
            script_args = script_args[1:]
        return {
            "action": "run",
            "script": str(args.script.resolve()),
            "script_args": script_args,
        }
    if args.command == "shutdown":
        return {"action": "shutdown"}
    raise RuntimeError(f"unknown command {args.command!r}")


def main() -> int:
    args = build_parser().parse_args()
    response = send_request(args.socket, build_request(args))
    if args.pretty:
        print(json.dumps(response, indent=2, sort_keys=True))
    else:
        print(json.dumps(response, sort_keys=True))
    status = response.get("status")
    if status in {"error", "timeout"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
