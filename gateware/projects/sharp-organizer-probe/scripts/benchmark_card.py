#!/usr/bin/env python3
"""Qualify and benchmark read settings against a committed organizer capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from card_discovery import read
from card_write import verify_committed_capture, verify_committed_file
from organizer_probe import BAUD, Probe, open_port


DEFAULT_CASES = [(5000, 65535), (1000, 32768), (1000, 65535),
                 (500, 8192), (500, 32768), (500, 65535), (200, 65535)]


def parse_case(text: str) -> tuple[int, int]:
    try:
        phase, chunk = (int(value, 0) for value in text.split(":"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("case must be PHASE_NS:REQUEST_BYTES") from exc
    if phase % 50 or not 200 <= phase <= 5000 or not 1 <= chunk <= 65535:
        raise argparse.ArgumentTypeError("phase must be 200..5000 in 50 ns steps; request 1..65535")
    return phase, chunk


def check_bytes(actual: bytes, expected: bytes, name: str) -> None:
    if actual != expected:
        offset = next((index for index, pair in enumerate(zip(actual, expected))
                       if pair[0] != pair[1]), min(len(actual), len(expected)))
        raise RuntimeError(f"{name}: differs from committed baseline at 0x{offset:05x}")


def load_ram_references(capture: Path, manifest: dict, specifications: list[str]) -> tuple[dict, list]:
    """Use separately committed conservative snapshots when mutable RAM changes."""
    images, records = {}, []
    for specification in specifications:
        name, separator, filename = specification.partition("=")
        views = [view for view in manifest["views"] if view["image"] == name]
        if (not separator or not filename or name in images or not views
                or any(view.get("memory_select") not in ("SRAM1", "SRAM2") for view in views)):
            raise ValueError("reference must name a distinct SRAM-only capture image: bank-NN.bin=PATH")
        path = Path(filename).resolve()
        sidecar = path.with_suffix(path.suffix + ".json")
        verify_committed_file(path)
        verify_committed_file(sidecar)
        data = path.read_bytes()
        metadata = json.loads(sidecar.read_text())
        digest = hashlib.sha256(data).hexdigest()
        if (len(data) != len((capture / name).read_bytes())
                or metadata.get("passes", 0) < 2 or metadata.get("start") != 0
                or metadata.get("length") != len(data) or metadata.get("burst_phase_us") != 5
                or metadata.get("sha256") != digest
                or metadata.get("active") not in [view["selection"]["active_control"] for view in views]):
            raise ValueError("RAM reference needs matching length, hash and selection, and two conservative 5 us passes")
        images[name] = data
        records.append({"capture_image": name, "current_committed_image": str(path),
                        "current_metadata": str(sidecar), "sha256": digest,
                        "mirror_basis": "address period from capture; candidate scans compare every repeated byte"})
    return images, records


def benchmark_case(probe: Probe, references: list[tuple[dict, bytes]],
                   phase: int, chunk: int, scan_length: int, passes: int) -> dict:
    probe.set_read_timing(phase)
    probe.burst_request_bytes = chunk
    retry_start = len(probe.read_retry_events)
    result = {"read_phase_ns": phase, "burst_request_bytes": probe.burst_request_bytes,
              "requested_burst_bytes": chunk,
              "scan_length": scan_length, "passes": passes, "reads": []}
    started = time.perf_counter()
    for view, image in references:
        expected = (image * ((scan_length + len(image) - 1) // len(image)))[:scan_length]
        for pass_index in range(passes):
            before = time.perf_counter()
            actual = read(probe, 0, scan_length, view["selection"]["active_control"])
            seconds = time.perf_counter() - before
            check_bytes(actual, expected, view["name"])
            result["reads"].append({"view": view["name"], "pass": pass_index + 1,
                                    "seconds": seconds, "bytes": len(actual),
                                    "sha256": hashlib.sha256(actual).hexdigest()})
    result["elapsed_seconds"] = time.perf_counter() - started
    result["bytes_checked"] = sum(item["bytes"] for item in result["reads"])
    result["payload_bytes_per_second"] = result["bytes_checked"] / result["elapsed_seconds"]
    result["read_retry_events"] = probe.read_retry_events[retry_start:]
    result["status"] = "matched_committed_baseline"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--ft600-serial")
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--reference-image", action="append", default=[], metavar="BANK=PATH",
                        help="committed current SRAM dump with two 5 us passes, if capture SRAM changed")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", type=parse_case, action="append")
    parser.add_argument("--scan-length", type=int, default=1 << 20)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    if args.passes < 2 or not 256 <= args.scan_length <= 1 << 20:
        parser.error("need at least two passes and a scan length from 256 through 1048576")
    if args.output.exists():
        parser.error("output already exists; use a new benchmark filename")
    manifest = verify_committed_capture(args.capture_dir)
    replacements, reference_records = load_ram_references(args.capture_dir, manifest, args.reference_image)
    references = []
    seen = set()
    for view in manifest["views"]:
        if view["presence"] == "open_bus_or_echo" or view["observed_address_period"] <= 1:
            continue
        if view["start"] != 0 or args.scan_length > view["scanned_length"]:
            parser.error("benchmark range is not covered by the committed baseline")
        if view["image"] not in seen:
            seen.add(view["image"])
            references.append((view, replacements.get(view["image"],
                                (args.capture_dir / view["image"]).read_bytes())))
    if not references:
        parser.error("capture has no distinct stable memory images to benchmark")
    cases = args.case or DEFAULT_CASES
    report = {"schema": 1, "capture": str(args.capture_dir.resolve()),
              "reported_model": manifest["reported_model"], "uart_baud": args.baud,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "uart_8n1_payload_limit_bytes_per_second": args.baud / 10,
              "ram_reference_overrides": reference_records,
              "qualification": [], "cases": [], "status": "running"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ExitStack() as stack:
            port = stack.enter_context(open_port(args.port, args.baud))
            ft600 = None
            if args.ft600_serial:
                from ft600_transport import Ft600

                ft600 = stack.enter_context(Ft600(args.ft600_serial))
            probe = stack.enter_context(Probe(port, ft600))
            probe.identify()
            probe.park()
            if ft600 is not None:
                ft600.drain()
            report["gateware_protocol"] = probe.protocol
            report["uart_transport"] = getattr(port, "transport", "pyserial")
            report["data_transport"] = "ft600" if ft600 is not None else "uart"
            report["ft600_serial"] = getattr(ft600, "serial", None)
            try:
                phases = sorted({5000, *(phase for phase, _ in cases)}, reverse=True)
                for phase in phases:
                    probe.set_read_timing(phase)
                    probe.burst_request_bytes = 65535
                    for view, image in references:
                        for pass_index in range(args.passes):
                            actual = read(probe, 0, len(image), view["selection"]["active_control"])
                            check_bytes(actual, image, view["name"])
                            report["qualification"].append({"read_phase_ns": phase,
                                "view": view["name"], "pass": pass_index + 1,
                                "bytes_checked": len(image), "sha256": hashlib.sha256(actual).hexdigest()})
                    print(f"qualified {phase} ns against all complete memory images", flush=True)
                for phase, chunk in cases:
                    print(f"benchmark {phase} ns, {chunk} bytes/request", flush=True)
                    result = benchmark_case(probe, references, phase, chunk,
                                            args.scan_length, args.passes)
                    report["cases"].append(result)
                    args.output.write_text(json.dumps(report, indent=2) + "\n")
                    print(f"  {result['elapsed_seconds']:.3f} s, "
                          f"{result['payload_bytes_per_second'] / 1024:.1f} KiB/s, "
                          f"{len(result['read_retry_events'])} retries", flush=True)
            except Exception as exc:
                report["operation_error"] = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                report["read_retry_events"] = probe.read_retry_events
                # Leave later operations at the conservative hardware timing.
                try:
                    probe.park()
                    probe.set_read_timing(5000)
                    snapshot = probe.park()
                    report["final_park"] = {"armed": snapshot.armed,
                                            "address_oe": snapshot.address_oe,
                                            "control_oe": snapshot.control_oe}
                    report["final_read_phase_ns"] = probe.burst_phase_ns
                except Exception as exc:
                    report["cleanup_error"] = f"{type(exc).__name__}: {exc}"
                    raise
            report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
