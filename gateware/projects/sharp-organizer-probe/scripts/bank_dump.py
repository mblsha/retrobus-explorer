"""Named, attributed bank plans for the organizer probe."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from organizer_probe import (
    BURST_CHUNK, CONTROL_BITS, PROTECTED_BITS, NC_BITS, Probe, Snapshot, bounded, cycle, run_dump,
    validate_cycle,
)


@dataclass(frozen=True)
class Bank:
    name: str
    start: int
    length: int
    idle: int
    active: int
    mask: int
    description: str | None


@dataclass(frozen=True)
class BankPlan:
    card_label: str
    banks: tuple[Bank, ...]
    source: bytes


def _check_keys(value: dict, allowed: set[str], required: set[str], where: str) -> None:
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown or missing:
        raise ValueError(f"{where}: unknown keys {sorted(unknown)}, missing keys {sorted(missing)}")


def _integer(value: object, label: str) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str):
        return int(value, 0)
    raise ValueError(f"{label} must be an integer or a 0x-prefixed string")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path: Path) -> BankPlan:
    source = path.read_bytes()
    document = json.loads(source, object_pairs_hook=_unique_object)
    if not isinstance(document, dict):
        raise ValueError("bank plan must be a JSON object")
    _check_keys(document, {"schema", "card_label", "banks"},
                {"schema", "card_label", "banks"}, "plan")
    if type(document["schema"]) is not int or document["schema"] != 1:
        raise ValueError("bank plan schema must be 1")
    label = document["card_label"]
    if not isinstance(label, str) or not label.strip():
        raise ValueError("card_label must be a nonempty string")
    entries = document["banks"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("banks must be a nonempty list")
    banks: list[Bank] = []
    used_names: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"banks[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{where} must be an object")
        _check_keys(entry, {"name", "start", "length", "pins", "description"},
                    {"name", "start", "length", "pins"}, where)
        name = entry["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError(f"{where}.name must use letters, digits, underscores or hyphens")
        if name in used_names:
            raise ValueError(f"duplicate bank name: {name}")
        used_names.add(name)
        start = bounded(_integer(entry["start"], f"{where}.start"), 20, "bank start")
        length = _integer(entry["length"], f"{where}.length")
        if length < 1 or start + length > 1 << 20:
            raise ValueError(f"{where} range must be nonempty and within 20 address bits")
        description = entry.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError(f"{where}.description must be a string")
        pins = entry["pins"]
        if not isinstance(pins, dict) or not pins:
            raise ValueError(f"{where}.pins must be a nonempty object")
        unexpected = set(pins) - set(CONTROL_BITS)
        if unexpected:
            raise ValueError(f"{where}.pins has unknown names: {sorted(unexpected)}")
        if pins.get("RW") != [1, 1]:
            raise ValueError(f"{where}.pins must drive RW high in both phases for a read")
        idle = active = mask = 0
        for bit, pin in enumerate(CONTROL_BITS):
            if pin not in pins:
                continue
            levels = pins[pin]
            if (not isinstance(levels, list) or len(levels) != 2 or
                    any(type(level) is not int or level not in (0, 1) for level in levels)):
                raise ValueError(f"{where}.pins.{pin} must be [idle, active] with 0/1 levels")
            mask |= 1 << bit
            idle |= levels[0] << bit
            active |= levels[1] << bit
        validate_cycle(idle, active, mask, 0)
        banks.append(Bank(name, start, length, idle, active, mask, description))
    return BankPlan(label, tuple(banks), source)


def pin_levels(bank: Bank) -> dict[str, dict[str, int | bool | None]]:
    return {
        pin: {
            "bit": bit,
            "driven": bool(bank.mask & (1 << bit)),
            "idle": (bank.idle >> bit) & 1 if bank.mask & (1 << bit) else None,
            "active": (bank.active >> bit) & 1 if bank.mask & (1 << bit) else None,
        }
        for bit, pin in enumerate(CONTROL_BITS)
    }


def bank_selection(bank: Bank) -> dict:
    levels = pin_levels(bank)
    return {
        "idle_control": bank.idle,
        "active_control": bank.active,
        "control_drive_mask": bank.mask,
        "pins": levels,
        "driven_low_during_read": [pin for pin, level in levels.items()
                                   if level["driven"] and level["active"] == 0],
        "undriven_pins": [pin for pin, level in levels.items() if not level["driven"]],
    }


def observed_snapshot(snapshot: Snapshot) -> dict:
    result = asdict(snapshot)
    result["control_pins"] = {
        pin: (snapshot.control >> bit) & 1 for bit, pin in enumerate(CONTROL_BITS)
    }
    result["protected_input_pins"] = {
        pin: (snapshot.protected >> bit) & 1 for bit, pin in enumerate(PROTECTED_BITS)
    }
    result["nc_contacts"] = {
        pin: {"observed": (snapshot.protected >> (bit + 3)) & 1,
              "driven": bool(snapshot.nc_oe & (1 << bit)),
              "drive": (snapshot.nc_drive >> bit) & 1 if snapshot.nc_oe & (1 << bit) else None}
        for bit, pin in enumerate(NC_BITS)
    }
    return result


def describe_plan(plan: BankPlan) -> dict:
    return {
        "schema": 1,
        "card_label_from_plan": plan.card_label,
        "plan_sha256": hashlib.sha256(plan.source).hexdigest(),
        "banks": [
            {"name": bank.name, "start": bank.start, "length": bank.length,
             "description": bank.description, "selection": bank_selection(bank)}
            for bank in plan.banks
        ],
    }


def run_plan(probe: Probe, plan: BankPlan, output_dir: Path, passes: int = 2,
             slow: bool = False, settle_us: int = 20) -> dict:
    if passes < 2:
        raise ValueError("bank dump requires at least two comparison passes")
    if output_dir.exists():
        raise FileExistsError(f"output directory already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    try:
        (stage / "plan.json").write_bytes(plan.source)
        manifest = describe_plan(plan)
        manifest.update({
            "gateware_protocol": probe.protocol or "unknown",
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "passes": passes,
            "mode": "slow" if slow else "burst",
            "uart_baud": getattr(probe.port, "baudrate", None),
            "burst_request_bytes": None if slow else getattr(probe, "burst_request_bytes", BURST_CHUNK),
            "burst_phase_us": None if slow else probe.burst_phase_ns / 1000,
            "source_plan": "plan.json",
            "banks": [],
        })
        for index, bank in enumerate(plan.banks):
            print(f"bank {index + 1}/{len(plan.banks)}: {bank.name}")
            probe.unlock()
            try:
                preflight = cycle(probe, bank.start, bank.idle, bank.active,
                                  bank.mask, settle_us)
            finally:
                probe.release()
            filename = f"bank-{index:02d}.bin"
            image = stage / filename
            run_dump(probe, SimpleNamespace(
                start=bank.start, length=bank.length, passes=passes,
                idle=bank.idle, active=bank.active, mask=bank.mask,
                settle_us=settle_us, slow=slow, output=image,
            ))
            data = image.read_bytes()
            if data[0] != preflight.data:
                raise RuntimeError(
                    f"{bank.name}: preflight byte 0x{preflight.data:02x} differs "
                    f"from first burst byte 0x{data[0]:02x}"
                )
            sidecar = image.with_suffix(".bin.json")
            record = json.loads(sidecar.read_text())
            record.update({
                "bank_name": bank.name,
                "description": bank.description,
                "image": filename,
                "plan_sha256": manifest["plan_sha256"],
                "selection": bank_selection(bank),
                "observed_active_preflight": observed_snapshot(preflight),
            })
            sidecar.write_text(json.dumps(record, indent=2) + "\n")
            manifest["banks"].append(record)
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        stage.rename(output_dir)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
