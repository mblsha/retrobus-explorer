#!/usr/bin/env python3
"""Capture read-only organizer views with replayable selection preambles."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import time
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from bank_dump import Bank, bank_selection, observed_snapshot
from card_discovery import address_period
from organizer_probe import BAUD, Probe, bounded, number, open_port, validate_cycle


@dataclass(frozen=True)
class Step:
    operation: str
    value: int


@dataclass(frozen=True)
class Profile:
    bank: Bank
    steps: tuple[Step, ...]
    mode: str = "burst"


@dataclass(frozen=True)
class Plan:
    reported_model: str
    profiles: tuple[Profile, ...]
    source: bytes


def read_control(value: int) -> int:
    bounded(value, 8, "control")
    if value & 1 == 0:
        raise ValueError("transition experiments must keep RW high")
    if ((~value & 0xf0) >> 4).bit_count() > 1:
        raise ValueError("transition experiments may select at most one memory")
    return value


def integer(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError("values must be integers or hexadecimal strings")


def keys(value: object, required: set[str], optional: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or set(value) - required - optional or required - set(value):
        raise ValueError(f"expected keys {sorted(required)}, optional {sorted(optional)}")
    return value


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path: Path) -> Plan:
    source = path.read_bytes()
    doc = keys(json.loads(source, object_pairs_hook=unique_object),
               {"schema", "reported_model", "profiles"})
    if type(doc["schema"]) is not int or doc["schema"] != 1:
        raise ValueError("transition plan schema must be 1")
    if not isinstance(doc["reported_model"], str) or not doc["reported_model"].strip():
        raise ValueError("reported_model must be a nonempty string")
    if not isinstance(doc["profiles"], list) or not doc["profiles"]:
        raise ValueError("profiles must be a nonempty list")
    profiles, names = [], set()
    for entry in doc["profiles"]:
        keys(entry, {"name", "steps", "read"}, {"description"})
        name = entry["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("profile names must be nonempty and unique")
        names.add(name)
        description = entry.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError("description must be a string")
        if not isinstance(entry["steps"], list) or len(entry["steps"]) > 128:
            raise ValueError("steps must be a list of at most 128 commands")
        steps = []
        for item in entry["steps"]:
            keys(item, {"operation", "value"})
            operation, value = item["operation"], integer(item["value"])
            if operation == "address":
                bounded(value, 20, "address")
            elif operation == "control":
                read_control(value)
            elif operation == "hold_us":
                if not 0 <= value <= 100_000:
                    raise ValueError("hold_us must be 0..100000, within the watchdog interval")
            else:
                raise ValueError("operations are address, control or hold_us; no data or protected-pin drive")
            steps.append(Step(operation, value))
        read = keys(entry["read"], {"start", "length", "idle_control", "active_control"}, {"mode"})
        mode = read.get("mode", "burst")
        if mode not in ("burst", "held_select"):
            raise ValueError("read mode must be burst or held_select")
        start, length = integer(read["start"]), integer(read["length"])
        bounded(start, 20, "start")
        if length < 1 or start + length > 1 << 20:
            raise ValueError("read must be nonempty and within the 20-bit address range")
        idle, active = (read_control(integer(read[key]))
                        for key in ("idle_control", "active_control"))
        validate_cycle(idle, active, 0xff, 0)
        if active & 2 or (~active & 0xf0) == 0:
            raise ValueError("active read must assert OE and exactly one memory select")
        if mode == "held_select" and next((step.value for step in reversed(steps)
                                              if step.operation == "control"), 0xff) != active:
            raise ValueError("held_select preamble must end with the active read controls")
        profiles.append(Profile(Bank(name, start, length, idle, active, 0xff, description), tuple(steps), mode))
    return Plan(doc["reported_model"], tuple(profiles), source)


def replay(probe: Probe, steps: tuple[Step, ...], events: list[dict]) -> None:
    """Begin parked, then initialize deselected controls before driving address."""
    events.append({"operation": "park", "observed": observed_snapshot(probe.park())})
    probe.unlock()
    commands = (Step("control", 0xff), Step("address", 0), *steps)
    address, control = None, None
    for step in commands:
        before = time.perf_counter_ns()
        event = {"operation": step.operation, "value": step.value, "status": "started"}
        events.append(event)
        if step.operation == "control":
            control = read_control(step.value)
            probe.control(control, 0xff)
        elif step.operation == "address":
            address = bounded(step.value, 20, "address")
            probe.address(address, 0xfffff)
        else:
            time.sleep(step.value / 1_000_000)
        sample = probe.snapshot()
        if (not sample.armed or (address is not None and
                (sample.address != address or sample.address_oe != 0xfffff)) or
                (control is not None and (sample.control != control or sample.control_oe != 0xff))):
            raise RuntimeError("selection preamble lost drive or observed pins differ from commands")
        event.update(status="observed", host_elapsed_ns_including_snapshot=time.perf_counter_ns() - before,
                     observed=observed_snapshot(sample))


def held_read(probe: Probe, start: int, count: int, active: int, samples: list[dict]) -> bytes:
    """Change only address after the preamble, preserving the selected controls."""
    result = bytearray()
    for address in range(start, start + count):
        probe.address(address, 0xfffff)
        sample = probe.snapshot()
        samples.append(observed_snapshot(sample))
        if (not sample.armed or sample.address_oe != 0xfffff or sample.control_oe != 0xff
                or sample.address != address or sample.control != active):
            raise RuntimeError("held-select read lost drive or observed pins differ")
        result.append(sample.data)
    return bytes(result)


def capture(probe: Probe, plan: Plan, output_dir: Path, *, passes: int = 2) -> dict:
    if passes < 2:
        raise ValueError("transition captures require at least two complete comparison passes")
    if not 1 <= probe.burst_request_bytes <= 65535:
        raise ValueError("invalid burst request size")
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "plan.json").write_bytes(plan.source)
    report = {"schema": 1, "kind": "read_only_transition_experiment", "status": "running",
              "reported_model": plan.reported_model, "captured_utc": datetime.now(timezone.utc).isoformat(),
              "plan": "plan.json", "plan_sha256": hashlib.sha256(plan.source).hexdigest(),
              "gateware_protocol": probe.protocol, "read_phase_ns": probe.burst_phase_ns,
              "passes": passes, "burst_request_bytes": probe.burst_request_bytes,
              "data_transport": "ft600" if probe.ft600 else "uart",
              "uart_baud": getattr(probe.port, "baudrate", None),
              "ft600_serial": getattr(probe.ft600, "serial", None),
              "tool_sources_sha256": {
                  filename: hashlib.sha256(Path(__file__).with_name(filename).read_bytes()).hexdigest()
                  for filename in ("transition_probe.py", "organizer_probe.py", "bank_dump.py", "card_discovery.py")},
              "observations": "observations.jsonl.gz", "profiles": [], "images": [],
              "boundary_contract": {
                  "initialization": "park, unlock, control=0xff/mask=0xff, address=0/mask=0xfffff",
                  "preamble_replayed": "before every chunk of every pass",
                  "burst_entry": "gateware applies read idle controls and chunk address before selected sampling",
                  "held_select_entry": "only address changes after preamble; selected controls remain driven until chunk park",
                  "held_select_timing": "host command and snapshot latency; not controlled by read_phase_ns",
                  "burst_exit": "FT600 releases before payload transmission; host verifies park after each chunk",
                  "timing": "preamble is host-timed with a snapshot after every command; elapsed values are not pin-edge timestamps",
                  "power_on_reset": "not performed; parking is not proof of a card latch reset",
                  "limitations": "burst mode cannot test continuous drive across burst entry; both modes park between chunks; no writes or unknown-pin drive",
              }}
    started, image_ids = time.perf_counter(), {}
    try:
        with gzip.open(output_dir / "observations.jsonl.gz", "wt", encoding="utf-8") as observations:
            for profile_index, profile in enumerate(plan.profiles):
                bank, baseline, pass_records = profile.bank, None, []
                print(f"profile {profile_index + 1}/{len(plan.profiles)}: {bank.name}", flush=True)
                for pass_index in range(passes):
                    current = bytearray()
                    for offset in range(0, bank.length, probe.burst_request_bytes):
                        count = min(probe.burst_request_bytes, bank.length - offset)
                        record = {"profile": bank.name, "pass": pass_index + 1,
                                  "start": bank.start + offset, "length": count,
                                  "mode": profile.mode, "sequence": [], "status": "running"}
                        try:
                            replay(probe, profile.steps, record["sequence"])
                            if profile.mode == "held_select":
                                record["held_samples"] = []
                                data = held_read(probe, bank.start + offset, count, bank.active, record["held_samples"])
                            else:
                                data = probe.burst(bank.start + offset, count, bank.idle, bank.active, bank.mask)
                            if len(data) != count:
                                raise RuntimeError("incomplete burst payload")
                            record["sha256"] = hashlib.sha256(data).hexdigest()
                            if baseline is not None and data != baseline[offset:offset + count]:
                                mismatch = next(i for i, pair in enumerate(zip(data, baseline[offset:offset + count]))
                                                if pair[0] != pair[1])
                                record["mismatch_address"] = bank.start + offset + mismatch
                                raise RuntimeError(f"{bank.name}: pass {pass_index + 1} differs at 0x{record['mismatch_address']:05x}")
                            current.extend(data)
                            record["status"] = "matched" if baseline is not None else "first_pass"
                        except BaseException as exc:
                            record.update(status="failed", error=str(exc))
                            raise
                        finally:
                            try:
                                record["park"] = observed_snapshot(probe.park())
                            except BaseException as exc:
                                record.update(status="failed", park_error=str(exc))
                                raise
                            finally:
                                observations.write(json.dumps(record) + "\n")
                                observations.flush()
                    baseline = bytes(current)
                    pass_records.append({"pass": pass_index + 1, "length": len(baseline),
                                         "sha256": hashlib.sha256(baseline).hexdigest()})
                period = address_period(baseline)
                canonical = baseline[:period]
                digest = hashlib.sha256(canonical).hexdigest()
                identity = (len(canonical), digest)
                if identity not in image_ids:
                    filename = f"bank-{len(image_ids):02d}.bin"
                    image_ids[identity] = filename
                    (output_dir / filename).write_bytes(canonical)
                    report["images"].append({"image": filename, "length": len(canonical), "sha256": digest})
                report["profiles"].append({"name": bank.name, "description": bank.description, "mode": profile.mode,
                    "start": bank.start, "scanned_length": bank.length, "observed_address_period": period,
                    "selection": bank_selection(bank), "steps": [step.__dict__ for step in profile.steps],
                    "image": image_ids[identity], "sha256": digest,
                    "full_scan_sha256": pass_records[0]["sha256"], "passes": pass_records,
                    "relationship": "equal captured bytes; physical bank identity unqualified"})
        report["status"] = "complete"
    except BaseException as exc:
        report.update(status="failed", error=str(exc))
        raise
    finally:
        try:
            report["final_park"] = observed_snapshot(probe.park())
        except BaseException as exc:
            report.update(status="failed", park_error=str(exc))
            raise
        finally:
            report["elapsed_seconds"] = time.perf_counter() - started
            (output_dir / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--port")
    parser.add_argument("--baud", type=int, default=BAUD)
    parser.add_argument("--ft600-serial")
    parser.add_argument("--read-phase-ns", type=number, default=5000)
    parser.add_argument("--burst-bytes", type=number, default=65535)
    parser.add_argument("--passes", type=int, default=2)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    if args.dry_run:
        print(json.dumps({"reported_model": plan.reported_model, "profiles": len(plan.profiles),
                          "plan_sha256": hashlib.sha256(plan.source).hexdigest()}, indent=2))
        return
    if (not args.port or not args.output_dir or args.output_dir.exists() or args.passes < 2
            or not 1 <= args.burst_bytes <= 65535 or args.read_phase_ns % 50
            or not 200 <= args.read_phase_ns <= 5000):
        parser.error("need --port, a new --output-dir, passes>=2, burst 1..65535 and phase 200..5000 in steps of 50 ns")
    with ExitStack() as stack:
        port = stack.enter_context(open_port(args.port, args.baud))
        ft = None
        if args.ft600_serial:
            from ft600_transport import Ft600

            ft = stack.enter_context(Ft600(args.ft600_serial))
        probe = stack.enter_context(Probe(port, ft))
        probe.identify()
        probe.park()
        if ft:
            ft.drain()
        probe.set_read_timing(args.read_phase_ns)
        probe.burst_request_bytes = args.burst_bytes
        result = capture(probe, plan, args.output_dir, passes=args.passes)
        print(json.dumps({"status": result["status"], "profiles": len(result["profiles"]),
                          "images": len(result["images"]), "elapsed_seconds": result["elapsed_seconds"]}, indent=2))


if __name__ == "__main__":
    main()
