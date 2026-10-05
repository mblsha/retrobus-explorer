"""Committed-backup-gated SRAM probing and writes for discovered card views."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from card_discovery import read, validate_capture_files
from organizer_probe import Probe


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def verify_committed_file(path: Path) -> None:
    path = path.resolve()
    root = Path(_git(path.parent, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    relative = path.relative_to(root).as_posix()
    try:
        committed = _git(root, "show", f"HEAD:{relative}")
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"file is not committed at HEAD: {path}") from exc
    if committed != path.read_bytes():
        raise ValueError(f"file differs from HEAD: {path}")


def verify_committed_capture(capture_dir: Path) -> dict:
    capture_dir = capture_dir.resolve()
    manifest_path = capture_dir / "manifest.json"
    manifest = validate_capture_files(capture_dir)
    paths = [manifest_path]
    for image in manifest["images"]:
        path = capture_dir / image["image"]
        sidecar = capture_dir / f"{image['image']}.json"
        paths.extend((path, sidecar))
    for path in paths:
        verify_committed_file(path)
    return manifest


def commit_directory(directory: Path, message: str) -> str:
    directory = directory.resolve()
    root = Path(_git(directory, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    relative = directory.relative_to(root).as_posix()
    _git(root, "add", "--", relative)
    _git(root, "commit", "--only", "-m", message, "--", relative)
    return _git(root, "rev-parse", "HEAD").decode().strip()


def commit_capture(capture_dir: Path) -> str:
    commit = commit_directory(capture_dir, f"Back up Sharp organizer card capture {capture_dir.name}")
    verify_committed_capture(capture_dir)
    return commit


def _view(manifest: dict, name: str) -> dict:
    matches = [view for view in manifest["views"] if view["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"unknown or duplicate view: {name}")
    return matches[0]


def _backup(capture_dir: Path, view: dict) -> bytes:
    return (capture_dir / view["image"]).read_bytes()


def _active(view: dict) -> int:
    return view["selection"]["active_control"]


def _fingerprint_view(manifest: dict) -> dict:
    for view in manifest["views"]:
        if (view["memory_select"] == "EPROM" and view["name"].endswith("ci1-e21")
                and view["presence"] != "open_bus_or_echo"):
            return view
    for view in manifest["views"]:
        if view["presence"] != "open_bus_or_echo" and view["observed_address_period"] > 1:
            return view
    raise ValueError("no stable read view for card identity; refuse automatic writes")


def verify_live_identity(probe: Probe, capture_dir: Path, manifest: dict) -> None:
    view = _fingerprint_view(manifest)
    expected = _backup(capture_dir, view)
    actual = read(probe, 0, len(expected), _active(view))
    if actual != expected:
        raise RuntimeError("live card fingerprint view does not match committed capture")


def _write(probe: Probe, view: dict, address: int, value: int) -> None:
    probe.unlock()
    try:
        probe.write_profiled_byte(address, value,
                                  _active(view) | 0x02)
        snapshot = probe.snapshot()
        if snapshot.armed or snapshot.address_oe or snapshot.control_oe or snapshot.nc_oe:
            raise RuntimeError("write left pins driven")
    finally:
        probe.release()


def _after_priming(probe: Probe, manifest: dict, capture_dir: Path,
                   view: dict, address: int, avoid: int) -> tuple[int | None, int]:
    rom = next((candidate for candidate in manifest["views"]
                if candidate["memory_select"] in ("EPROM", "MSKROM") and
                candidate["presence"] != "open_bus_or_echo" and
                candidate["observed_address_period"] > 1), None)
    if rom is None:
        return None, read(probe, address, 1, _active(view))[0]
    data = _backup(capture_dir, rom)
    primer = next(((index, value) for index, value in enumerate(data[:256]) if value != avoid), None)
    if primer is None:
        return None, read(probe, address, 1, _active(view))[0]
    index, value = primer
    read(probe, index, 1, _active(rom))
    return value, read(probe, address, 1, _active(view))[0]


def _physical_alias_groups(probes: list[dict]) -> list[list[str]]:
    confirmed = {entry["view"]: entry for entry in probes
                 if entry.get("result") == "writable_ram_confirmed"}
    parent = {name: name for name in confirmed}

    def root(name: str) -> str:
        while parent[name] != name:
            name = parent[name]
        return name

    for name, entry in confirmed.items():
        for other in entry.get("physical_aliases_confirmed", []):
            if other in confirmed and name in confirmed[other].get("physical_aliases_confirmed", []):
                parent[root(other)] = root(name)
    groups: dict[str, list[str]] = {}
    for name in confirmed:
        groups.setdefault(root(name), []).append(name)
    return [sorted(group) for group in groups.values()]


def probe_ram(probe: Probe, capture_dir: Path, result_dir: Path) -> dict:
    """Try reversible writes only to stable, backed-up SRAM-select views."""
    if probe.protocol not in ("OBP4", "OBP5", "OBP6"):
        raise RuntimeError("automatic SRAM probes require OBP4 or newer gateware")
    manifest = verify_committed_capture(capture_dir)
    verify_live_identity(probe, capture_dir, manifest)
    if result_dir.exists():
        raise FileExistsError(result_dir)
    root = Path(_git(capture_dir, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    try:
        result_dir.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("SRAM probe result directory must be inside the capture repository") from exc
    result_dir.mkdir(parents=True)
    result = {"schema": 1, "capture": str(capture_dir.resolve()),
              "capture_commit": _git(capture_dir, "rev-parse", "HEAD").decode().strip(),
              "recorded_utc": datetime.now(timezone.utc).isoformat(), "probes": []}
    try:
        for view in manifest["views"]:
            if view["memory_select"] not in ("SRAM1", "SRAM2"):
                continue
            item = {"view": view["name"], "selection": view["selection"],
                    "backup_image": view["image"], "backup_sha256": view["image_sha256"]}
            result["probes"].append(item)
            if view["presence"] == "open_bus_or_echo":
                item["result"] = "open_bus_or_echo_no_write"
                continue
            expected = _backup(capture_dir, view)
            if read(probe, 0, len(expected), _active(view)) != expected:
                item["result"] = "live_differs_from_backup_no_write"
                continue
            other_views = [other for other in manifest["views"]
                           if other["memory_select"] in ("SRAM1", "SRAM2") and
                           other["name"] != view["name"] and
                           other["presence"] != "open_bus_or_echo"]
            addresses = [0, len(expected) - 1] if len(expected) > 1 else [0, 1]
            item["trials"] = []
            for index, address in enumerate(addresses):
                original = expected[address % len(expected)]
                trial = original ^ (0x5a if index == 0 else 0xa5)
                trial_record = {"address": address, "original": original, "trial": trial,
                                "cross_views": {}}
                item["trials"].append(trial_record)
                try:
                    _write(probe, view, address, trial)
                    trial_record["immediate"] = read(probe, address, 1, _active(view))[0]
                    primer, observed = _after_priming(probe, manifest, capture_dir, view, address, trial)
                    trial_record["primer_value"] = primer
                    trial_record["after_priming"] = observed
                    for other in other_views:
                        other_backup = _backup(capture_dir, other)
                        other_address = address % len(other_backup)
                        _, value = _after_priming(probe, manifest, capture_dir, other,
                                                  other_address, trial)
                        trial_record["cross_views"][other["name"]] = {
                            "before": other_backup[other_address], "during": value}
                finally:
                    _write(probe, view, address, original)
                trial_record["after_restore"] = _after_priming(
                    probe, manifest, capture_dir, view, address, trial)[1]
                for other in other_views:
                    other_backup = _backup(capture_dir, other)
                    other_address = address % len(other_backup)
                    trial_record["cross_views"][other["name"]]["after_restore"] = _after_priming(
                        probe, manifest, capture_dir, other, other_address, trial)[1]
            item["restored_full_images"] = {
                other["name"]: read(probe, 0, len(_backup(capture_dir, other)), _active(other)) ==
                               _backup(capture_dir, other)
                for other in (view, *other_views)
            }
            item["physical_aliases_confirmed"] = [
                other["name"] for other in other_views
                if all(trial["cross_views"][other["name"]]["during"] == trial["trial"] and
                       trial["cross_views"][other["name"]]["before"] != trial["trial"] and
                       trial["cross_views"][other["name"]]["after_restore"] ==
                           trial["cross_views"][other["name"]]["before"]
                       for trial in item["trials"])
            ]
            item["result"] = (
                "writable_ram_confirmed" if all(
                    trial.get("immediate") == trial["trial"] and
                    trial.get("after_priming") == trial["trial"] and
                    trial.get("primer_value") is not None and
                    trial.get("after_restore") == trial["original"]
                    for trial in item["trials"]
                ) and all(item["restored_full_images"].values())
                else "write_not_persistent_or_inconclusive"
            )
            (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    finally:
        probe.release()
        result["physical_alias_groups"] = _physical_alias_groups(result["probes"])
        (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def write_sram(probe: Probe, capture_dir: Path, probe_result: Path, view_name: str,
               address: int, replacement: bytes, result_dir: Path,
               expected_image: Path | None = None) -> dict:
    if probe.protocol not in ("OBP4", "OBP5", "OBP6"):
        raise RuntimeError("profiled SRAM writes require OBP4 or newer gateware")
    manifest = verify_committed_capture(capture_dir)
    view = _view(manifest, view_name)
    if view["memory_select"] not in ("SRAM1", "SRAM2"):
        raise ValueError("writes require an SRAM-select view")
    verify_committed_file(probe_result)
    probe_record = json.loads(probe_result.read_text())
    if Path(probe_record["capture"]).resolve() != capture_dir.resolve():
        raise ValueError("SRAM probe result belongs to another capture")
    if not any(entry["view"] == view_name and entry["result"] == "writable_ram_confirmed"
               for entry in probe_record["probes"]):
        raise ValueError("SRAM view has no successful persistent write probe")
    if expected_image is None:
        expected_image = capture_dir / view["image"]
    verify_committed_file(expected_image)
    expected = expected_image.read_bytes()
    if len(expected) != len(_backup(capture_dir, view)):
        raise ValueError("expected SRAM image length differs from captured bank period")
    if not replacement or address < 0 or address + len(replacement) > len(expected):
        raise ValueError("write range is outside the committed SRAM image")
    if result_dir.exists():
        raise FileExistsError(result_dir)
    root = Path(_git(capture_dir, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    try:
        result_dir.resolve().relative_to(root)
    except ValueError as exc:
        raise ValueError("SRAM write result directory must be inside the capture repository") from exc
    verify_live_identity(probe, capture_dir, manifest)
    if read(probe, 0, len(expected), _active(view)) != expected:
        raise RuntimeError("live SRAM differs from committed backup")
    result_dir.mkdir(parents=True)
    result = {"schema": 1, "capture": str(capture_dir.resolve()), "view": view_name,
              "selection": view["selection"], "address": address,
              "expected_image": str(expected_image.resolve()),
              "length": len(replacement), "backup_sha256": hashlib.sha256(expected).hexdigest(),
              "requested_sha256": hashlib.sha256(replacement).hexdigest(),
              "recorded_utc": datetime.now(timezone.utc).isoformat(), "status": "started"}
    (result_dir / "before.bin").write_bytes(expected)
    changed = []
    try:
        for offset, value in enumerate(replacement):
            changed.append(address + offset)
            _write(probe, view, address + offset, value)
        after = read(probe, 0, len(expected), _active(view))
        intended = bytearray(expected)
        intended[address:address + len(replacement)] = replacement
        if after != intended:
            raise RuntimeError("full SRAM readback differs from requested image")
        (result_dir / "after.bin").write_bytes(after)
        result.update({"status": "verified", "after_sha256": hashlib.sha256(after).hexdigest()})
    except Exception as exc:
        result.update({"status": "restoring_after_error", "error": str(exc)})
        try:
            for changed_address in reversed(changed):
                _write(probe, view, changed_address, expected[changed_address])
            result["restore_verified"] = read(probe, 0, len(expected), _active(view)) == expected
        except Exception as restore_exc:
            result["restore_error"] = str(restore_exc)
        raise
    finally:
        probe.release()
        (result_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
