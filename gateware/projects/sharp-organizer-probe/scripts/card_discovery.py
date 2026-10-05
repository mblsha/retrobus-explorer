"""Bounded read-only discovery of organizer card select and address views."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from bank_dump import Bank, bank_selection, observed_snapshot
from organizer_probe import BURST_CHUNK, Probe, cycle, read_burst, run_dump


ADDRESS_LIMIT = 1 << 20
SELECT_BITS = {"EPROM": 0x80, "SRAM1": 0x20, "SRAM2": 0x40, "MSKROM": 0x10}


@dataclass(frozen=True)
class Selection:
    select: str
    ci: int = 1
    e2: int = 1

    @property
    def name(self) -> str:
        return f"{self.select.lower()}-ci{self.ci}-e2{self.e2}"

    @property
    def active(self) -> int:
        return 0xff ^ 0x02 ^ SELECT_BITS[self.select] ^ (0x04 if self.ci == 0 else 0) ^ (0x08 if self.e2 == 0 else 0)

    def bank(self, length: int) -> Bank:
        return Bank(self.name, 0, length, 0xff, self.active, 0xff, None)


def selections() -> tuple[Selection, ...]:
    return tuple(Selection(select, ci, e2)
                 for ci, e2 in ((1, 1), (0, 1), (1, 0), (0, 0))
                 for select in SELECT_BITS)


def read(probe: Probe, start: int, count: int, active: int) -> bytes:
    if count < 1 or start < 0 or start + count > ADDRESS_LIMIT:
        raise ValueError("read is outside the 20-bit address range")
    result = bytearray()
    chunk_bytes = getattr(probe, "burst_request_bytes", BURST_CHUNK)
    try:
        for offset in range(0, count, chunk_bytes):
            size = min(chunk_bytes, count - offset)
            result.extend(read_burst(probe, start + offset, size, 0xff, active, 0xff))
    finally:
        probe.release()
    return bytes(result)


def address_period(data: bytes) -> int:
    """Smallest period matching the whole scan, including a partial final repeat."""
    if not data:
        raise ValueError("scan must be nonempty")
    prefix = array("I", [0]) * len(data)
    matched = 0
    for index in range(1, len(data)):
        while matched and data[index] != data[matched]:
            matched = prefix[matched - 1]
        if data[index] == data[matched]:
            matched += 1
        prefix[index] = matched
    return len(data) - prefix[-1]


def volume_header(data: bytes) -> dict | None:
    if len(data) < 24 or data[:2] != b"\x10\x12":
        return None
    return {
        "volume_id": data[6:17].decode("ascii", errors="replace").rstrip(),
        "capacity_units_2k": int.from_bytes(data[2:4], "little"),
        "capacity_hint_bytes": int.from_bytes(data[2:4], "little") * 2048,
        "note": "On-card volume metadata, not a printed card model or physical chip-size measurement",
    }


def find_primers(probe: Probe, candidates: tuple[Selection, ...]):
    for candidate in candidates:
        sample = read(probe, 0, 256, candidate.active)
        first = sample[0]
        for address, value in enumerate(sample):
            if value != first:
                return ((candidate, 0, first), (candidate, address, value))
    return None


def bus_echo_test(probe: Probe, candidate: Selection, primers, limit: int) -> dict:
    if primers is None:
        return {"result": "no_distinct_primers", "observations": []}
    observations = []
    echoes = True
    for address in sorted({0, limit // 2, limit - 1}):
        values = []
        for primer, primer_addr, primer_value in primers:
            read(probe, primer_addr, 1, primer.active)
            observed = read(probe, address, 1, candidate.active)[0]
            values.append({"primer": primer.name, "primer_address": primer_addr,
                           "primer_value": primer_value, "observed": observed})
        observations.append({"address": address, "after_primers": values})
        echoes &= all(item["observed"] == item["primer_value"] for item in values)
    return {"result": "bus_echo_observed" if echoes else "not_bus_echo_at_test_points",
            "observations": observations}


def validate_capture_files(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("schema") != 2 or manifest.get("bus_family") != "sharp-organizer":
        raise ValueError("not a schema-2 organizer discovery capture")
    images = {item["image"]: item for item in manifest["images"]}
    if len(images) != len(manifest["images"]):
        raise ValueError("capture contains duplicate image filenames")
    for filename, item in images.items():
        if Path(filename).name != filename or not filename.endswith(".bin"):
            raise ValueError(f"invalid image filename: {filename}")
        data = (directory / filename).read_bytes()
        if len(data) != item["length"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"capture image fails size/hash validation: {filename}")
        sidecar = json.loads((directory / f"{filename}.json").read_text())
        if sidecar != item:
            raise ValueError(f"capture image sidecar differs from manifest: {filename}")
    if not manifest["views"]:
        raise ValueError("capture has no views")
    for view in manifest["views"]:
        if view["image"] not in images:
            raise ValueError("capture view references a missing image")
        item = images[view["image"]]
        if (view["observed_address_period"] != item["length"] or
                view["image_sha256"] != item["sha256"]):
            raise ValueError(f"capture view image metadata differs: {view['name']}")
        size = view["scanned_length"]
        if not 0 < size <= ADDRESS_LIMIT:
            raise ValueError(f"invalid scan size: {view['name']}")
        data = (directory / view["image"]).read_bytes()
        scan = (data * ((size + len(data) - 1) // len(data)))[:size]
        if hashlib.sha256(scan).hexdigest() != view["full_scan_sha256"]:
            raise ValueError(f"capture view does not reproduce its full scan: {view['name']}")
    return manifest


def capture(probe: Probe, output_dir: Path, *, limit: int = ADDRESS_LIMIT,
            passes: int = 2, candidates: tuple[Selection, ...] | None = None,
            reported_model: str | None = None) -> dict:
    if limit < 256 or limit > ADDRESS_LIMIT or limit & (limit - 1):
        raise ValueError("scan limit must be a power of two from 256 through 1048576")
    if passes < 2:
        raise ValueError("capture requires at least two matching passes")
    if output_dir.exists():
        raise FileExistsError(output_dir)
    candidates = candidates if candidates is not None else selections()
    if len({item.name for item in candidates}) != len(candidates):
        raise ValueError("duplicate select states")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-", dir=output_dir.parent))
    retry_start = len(getattr(probe, "read_retry_events", []))
    try:
        primers = find_primers(probe, candidates)
        manifest = {
            "schema": 2,
            "bus_family": "sharp-organizer",
            "reported_model": reported_model,
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "gateware_protocol": probe.protocol,
            "uart_baud": getattr(probe.port, "baudrate", None),
            "uart_transport": getattr(probe.port, "transport", "pyserial"),
            "data_transport": "ft600" if getattr(probe, "ft600", None) is not None else "uart",
            "ft600_serial": getattr(getattr(probe, "ft600", None), "serial", None),
            "burst_request_bytes": getattr(probe, "burst_request_bytes", BURST_CHUNK),
            "read_phase_ns": probe.burst_phase_ns,
            "address_scan_length": limit,
            "passes": passes,
            "discovery_scope": "single memory select with CI/E2 at all four levels; 20 address bits maximum",
            "primers": None if primers is None else [
                {"selection": selection.name, "address": address, "value": value}
                for selection, address, value in primers
            ],
            "images": [], "views": [], "write_probes": [],
        }
        known: dict[tuple[int, str], str] = {}
        for index, selection in enumerate(candidates):
            print(f"discovery view {index + 1}/{len(candidates)}: {selection.name}", flush=True)
            bank = selection.bank(limit)
            echo = bus_echo_test(probe, selection, primers, limit)
            probe.unlock()
            try:
                preflight = cycle(probe, 0, bank.idle, bank.active, bank.mask, 20)
            finally:
                probe.release()
            scan = stage / f"scan-{index:02d}.bin"
            run_dump(probe, SimpleNamespace(
                start=0, length=limit, passes=passes, idle=bank.idle,
                active=bank.active, mask=bank.mask, settle_us=20, slow=False, output=scan,
            ))
            data = scan.read_bytes()
            period = address_period(data)
            canonical = data[:period]
            digest = hashlib.sha256(canonical).hexdigest()
            key = (period, digest)
            image = known.get(key)
            if image is None or (stage / image).read_bytes() != canonical:
                image = f"bank-{len(manifest['images']):02d}.bin"
                (stage / image).write_bytes(canonical)
                known[key] = image
                sidecar = {"schema": 2, "image": image, "length": period, "sha256": digest,
                           "first_observed_view": selection.name}
                (stage / f"{image}.json").write_text(json.dumps(sidecar, indent=2) + "\n")
                manifest["images"].append(sidecar)
            view = {
                "name": selection.name,
                "memory_select": selection.select,
                "media_kind": "sram_candidate" if selection.select.startswith("SRAM") else "rom_candidate",
                "selection": bank_selection(bank),
                "observed_active_preflight": observed_snapshot(preflight),
                "bus_echo": echo,
                "presence": "open_bus_or_echo" if echo["result"] == "bus_echo_observed" else "read_response_unconfirmed",
                "start": 0, "scanned_length": limit,
                "observed_address_period": period,
                "mirror_relation": "verified_full_address_mirror" if period < limit else "none_observed",
                "full_scan_sha256": hashlib.sha256(data).hexdigest(),
                "image": image, "image_sha256": digest,
                "duplicate_data_of": next((v["name"] for v in manifest["views"] if v["image"] == image), None),
                "volume_header": volume_header(canonical),
            }
            manifest["views"].append(view)
            scan.unlink()
            scan.with_suffix(".bin.json").unlink()
        manifest["read_retry_events"] = getattr(probe, "read_retry_events", [])[retry_start:]
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        stage.rename(output_dir)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        try:
            probe.release()
        except (OSError, RuntimeError, TimeoutError):
            pass
