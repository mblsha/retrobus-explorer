#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path
from statistics import mean


DEFAULT_SOCKET = Path.home() / ".cache" / "pc-e500-expd.sock"
DEFAULT_COUNTS = [64, 128, 192, 224, 255, 256]
DEFAULT_QUANTUM = 130.879


def parse_counts(value: str) -> list[int]:
    counts: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        count = int(part, 0)
        if not 1 <= count <= 256:
            raise argparse.ArgumentTypeError("counts must be between 1 and 256")
        counts.append(count)
    if not counts:
        raise argparse.ArgumentTypeError("counts list may not be empty")
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a count sweep for a PC-E500 experiment and fit timing/counter slopes")
    parser.add_argument("--socket", type=Path, default=DEFAULT_SOCKET, help=f"unix socket path (default: {DEFAULT_SOCKET})")
    parser.add_argument("--counts", type=parse_counts, default=DEFAULT_COUNTS, help="comma-separated counts to run (default: 64,128,192,224,255,256)")
    parser.add_argument("--retries", type=int, default=3, help="retries per count on error/timeout (default: 3)")
    parser.add_argument("--retry-delay", type=float, default=1.0, help="seconds between retries (default: 1.0)")
    parser.add_argument("--quantum", type=float, default=DEFAULT_QUANTUM, help=f"tick quantum used for slope normalization (default: {DEFAULT_QUANTUM})")
    parser.add_argument("--save", type=Path, help="optional path to save the full JSON result")
    parser.add_argument("--pretty", action="store_true", help="pretty-print the resulting JSON")
    parser.add_argument("script", type=Path, help="path to the experiment script")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="extra args forwarded after the count; prefix with -- to separate")
    return parser


def send_request(socket_path: Path, payload: dict[str, object]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        response = bytearray()
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break
    if not response:
        raise RuntimeError("daemon returned no response")
    return json.loads(response.decode("utf-8"))


def build_run_request(script: Path, script_args: list[str]) -> dict[str, object]:
    return {
        "action": "run",
        "script": str(script.resolve()),
        "script_args": script_args,
    }


def fit_line(points: list[tuple[int, float]]) -> dict[str, float] | None:
    if len(points) < 2:
        return None
    xs = [float(x) for x, _ in points]
    ys = [float(y) for _, y in points]
    mx = mean(xs)
    my = mean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return {"intercept": intercept, "slope": slope}


def summarize_result(count: int, response: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {
        "count": count,
        "status": response.get("status"),
        "needs_reset": response.get("needs_reset", False),
    }
    if "error" in response:
        summary["error"] = response["error"]
    measurement = None
    measurements = response.get("measurement")
    if isinstance(measurements, list) and measurements:
        measurement = measurements[0]
        summary["measurement"] = measurement
        summary["ft_overflow_detected"] = bool(measurement.get("ft_overflow", 0))
    parsed = response.get("parsed")
    if isinstance(parsed, dict):
        summary["parsed"] = parsed
    ft_capture = response.get("ft_capture")
    if isinstance(ft_capture, dict):
        summary["ft_capture"] = {
            "enabled": ft_capture.get("enabled"),
            "health": ft_capture.get("health"),
            "word_count": ft_capture.get("word_count"),
            "raw_bytes": ft_capture.get("raw_bytes"),
            "chunk_count": ft_capture.get("chunk_count"),
            "max_retained_words": ft_capture.get("max_retained_words"),
            "truncated_head": ft_capture.get("truncated_head"),
        }
    return summary


def main() -> int:
    args = build_parser().parse_args()
    script_args = list(args.script_args)
    if script_args and script_args[0] == "--":
        script_args = script_args[1:]

    runs: list[dict[str, object]] = []
    failures = 0
    overflow_runs: list[dict[str, object]] = []
    for count in args.counts:
        last_response: dict[str, object] | None = None
        for attempt in range(1, args.retries + 1):
            response = send_request(args.socket, build_run_request(args.script, [str(count), *script_args]))
            last_response = response
            status = response.get("status")
            if status == "ok":
                break
            if attempt != args.retries:
                time.sleep(args.retry_delay)
        assert last_response is not None
        summary = summarize_result(count, last_response)
        summary["attempts"] = attempt
        runs.append(summary)
        if summary.get("status") != "ok":
            failures += 1
        elif summary.get("ft_overflow_detected"):
            overflow_runs.append(
                {
                    "count": summary["count"],
                    "attempts": summary["attempts"],
                    "ft_overflow": summary["measurement"]["ft_overflow"],
                }
            )

    tick_points: list[tuple[int, float]] = []
    ce_points: list[tuple[int, float]] = []
    au_points: list[tuple[int, float]] = []
    fo_points: list[tuple[int, float]] = []
    for run in runs:
        measurement = run.get("measurement")
        if run.get("status") != "ok" or not isinstance(measurement, dict):
            continue
        count = int(run["count"])
        tick_points.append((count, float(measurement["ticks"])))
        ce_points.append((count, float(measurement["ce_events"])))
        au_points.append((count, float(measurement["addr_uart"])))
        fo_points.append((count, float(measurement.get("ft_overflow", 0))))

    fits: dict[str, object] = {}
    tick_fit = fit_line(tick_points)
    if tick_fit is not None:
        tick_fit["slope_over_quantum"] = tick_fit["slope"] / args.quantum
        fits["ticks"] = tick_fit
    for name, points in (("ce_events", ce_points), ("addr_uart", au_points), ("ft_overflow", fo_points)):
        fit = fit_line(points)
        if fit is not None:
            fits[name] = fit

    payload = {
        "script": str(args.script.resolve()),
        "script_args": script_args,
        "counts": args.counts,
        "retries": args.retries,
        "quantum": args.quantum,
        "failures": failures,
        "overflow_detected": bool(overflow_runs),
        "overflow_runs": overflow_runs,
        "fits": fits,
        "runs": runs,
    }
    if overflow_runs:
        payload["note"] = (
            "FT overflow was observed in one or more runs. Treat those points as degraded, "
            "exclude them from timing fits, and use this as a signal to improve host-side "
            "FT600 capture throughput so future runs drain the stream fast enough to avoid overflow."
        )
    encoded = json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True)
    print(encoded)
    if args.save:
        args.save.write_text(encoded + ("\n" if not encoded.endswith("\n") else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
