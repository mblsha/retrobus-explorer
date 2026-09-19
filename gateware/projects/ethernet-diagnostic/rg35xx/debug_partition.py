"""The raw debug partition: its sector map and its record format.

Partition 2 deliberately carries no filesystem, so a write into it cannot
damage a boot file, and every writer addresses it by sector. Three parties
share those sectors -- the host, U-Boot's boot script and userspace's init --
and the only thing that keeps them from overwriting each other is this map.
It is therefore defined once here and imported by everything that writes or
reads the partition, rather than restated as a literal in each of them.
"""

from __future__ import annotations

import hashlib

SECTOR_SIZE = 512
MAGIC = "RG35DBG1"

# The partition the target sees this volume as. The boot script resolves the
# absolute LBAs it writes from this index and the real partition table, so a
# card partitioned differently still gets a correct script.
DEBUG_PARTITION = 2

# Sector 0 is the host's command to the target.
COMMAND_SECTOR = 0
# Sectors 1..7 are U-Boot's milestones. The EROFS boot script writes the first
# once the script is running, the third once the kernel is at kernel_addr_r
# and the fifth once the device tree is loaded.
UBOOT_BASE = 1
UBOOT_SECTORS = 7
SCRIPT_RUNNING = 1
KERNEL_LOADED = 3
DEVICE_TREE_LOADED = 5
# Sectors 8..15 hold an optional `env export` dump. The board has no console,
# so a variable U-Boot resolves at run time cannot be read any other way.
ENV_EXPORT_SECTOR = 8
ENV_EXPORT_SECTORS = 8
# Sectors 16..31 are userspace's. The first page holds its milestones, stage N
# at USERSPACE_BASE + N, so a U-Boot record and a userspace record from the same
# boot both survive to be read back together.
USERSPACE_BASE = 16
USERSPACE_SECTORS = 16
USERSPACE_STAGES = 8
# The second page is a flight recorder: the tail of the kernel log, rewritten
# several times a second while the target runs. The board has no console and
# the kernel no hung-task detector, so when bring-up wedges the machine this
# page is the only account of what the kernel was doing on the way in.
KERNEL_LOG_SECTOR = USERSPACE_BASE + USERSPACE_STAGES
KERNEL_LOG_SECTORS = USERSPACE_SECTORS - USERSPACE_STAGES
# What a host reads back to see one whole boot.
DEBUG_SECTORS = USERSPACE_BASE + USERSPACE_SECTORS

# The whole partition is 8 MiB, and everything above is in its first 16 KiB.
# The job exchange lives further up, with sectors 32..63 left free so the boot
# records can grow without moving it: a job region that moved would have to be
# moved in the same commit in the image, the host and the target's runner, and
# a host talking to a target built before the move would write a script over
# whatever now lives there.
PARTITION_SECTORS = 16384
# Sectors 64..127 are one job: a header sector naming the sequence number and
# the script's length and digest, then the script itself.
JOB_SECTOR = 64
JOB_SECTORS = 64
JOB_SCRIPT_BYTES = (JOB_SECTORS - 1) * SECTOR_SIZE
# Sectors 128..255 are the job's result: a header sector, then what the script
# wrote to its stdout and stderr.
RESULT_SECTOR = 128
RESULT_SECTORS = 128
RESULT_OUTPUT_BYTES = (RESULT_SECTORS - 1) * SECTOR_SIZE
# Sectors 256..263 are the runner's own scratch. The first is where a job's
# card check writes its pattern and reads it back, which is how a resumed
# target proves the card still answers. The second is written immediately
# before a suspend and again immediately after it, which is how the host --
# which cannot read the partition while the card is armed -- sees in the FPGA's
# passive trace that the target has gone to sleep and come back.
SCRATCH_SECTOR = 256
SCRATCH_SECTORS = 8
CARD_CHECK_SECTOR = SCRATCH_SECTOR
SLEEP_MARK_SECTOR = SCRATCH_SECTOR + 1


def absolute_lba(debug_start_lba: int, sector: int) -> int:
    """Return the card LBA of a debug sector in a partition starting there."""
    if not 0 <= sector < PARTITION_SECTORS:
        raise ValueError(f"sector {sector} is outside the debug partition")
    return debug_start_lba + sector


def encode_command(command: str) -> bytes:
    record = f"{MAGIC}\ndirection=host-to-target\ncommand={command}\n".encode()
    if len(record) > SECTOR_SIZE:
        raise ValueError("debug command does not fit in one sector")
    return record.ljust(SECTOR_SIZE, b"\0")


def decode_records(data: bytes) -> list[dict[str, str]]:
    if len(data) % SECTOR_SIZE:
        raise ValueError("debug data must contain whole 512-byte sectors")
    records = []
    for offset in range(0, len(data), SECTOR_SIZE):
        text = data[offset : offset + SECTOR_SIZE].rstrip(b"\0").decode(
            errors="replace"
        )
        if not text.startswith(f"{MAGIC}\n"):
            continue
        fields = {"sector": str(offset // SECTOR_SIZE)}
        for line in text.splitlines()[1:]:
            key, separator, value = line.partition("=")
            if separator:
                fields[key] = value
        records.append(fields)
    return records


def _header(fields: dict[str, str]) -> bytes:
    """Pack one record's fields into the sector that introduces a region."""
    text = MAGIC + "\n" + "".join(f"{key}={value}\n" for key, value in fields.items())
    encoded = text.encode()
    if len(encoded) > SECTOR_SIZE:
        raise ValueError("record header does not fit in one sector")
    return encoded.ljust(SECTOR_SIZE, b"\0")


def _digest(payload: bytes) -> str:
    """The digest the target checks a payload against.

    MD5 because BusyBox has `md5sum` and nothing stronger; this guards against
    a torn or stale region, not against an adversary.
    """
    return hashlib.md5(payload).hexdigest()


def encode_job(sequence: int, script: str, name: str = "") -> bytes:
    """Pack one job: a header sector and the script the runner is to run.

    The digest is what makes the exchange safe to run against a live target.
    The runner reads this region on its own schedule, the host writes it on
    its own, and neither can see the other; a script whose bytes do not match
    the digest its header carries is a region caught mid-write, and the runner
    waits rather than running half a script.
    """
    payload = script.encode()
    if len(payload) > JOB_SCRIPT_BYTES:
        raise ValueError(
            f"job script is {len(payload)} bytes; the region holds {JOB_SCRIPT_BYTES}"
        )
    if not 0 <= sequence <= 0xFFFFFFFF:
        raise ValueError("job sequence must be a 32-bit unsigned integer")
    header = _header(
        {
            "direction": "host-to-target",
            "kind": "job",
            "sequence": str(sequence),
            "name": name,
            "script_bytes": str(len(payload)),
            "script_md5": _digest(payload),
        }
    )
    sectors = -(-len(payload) // SECTOR_SIZE)
    return header + payload.ljust(sectors * SECTOR_SIZE, b"\0")


def decode_job(data: bytes) -> dict | None:
    """Read back a job region; None if it holds no complete job."""
    records = decode_records(data[:SECTOR_SIZE])
    if not records or records[0].get("kind") != "job":
        return None
    fields = records[0]
    try:
        length = int(fields["script_bytes"])
        sequence = int(fields["sequence"])
    except (KeyError, ValueError):
        return None
    payload = data[SECTOR_SIZE : SECTOR_SIZE + length]
    if len(payload) != length or _digest(payload) != fields.get("script_md5"):
        return None
    return {
        "sequence": sequence,
        "name": fields.get("name", ""),
        "script": payload.decode(errors="replace"),
    }


def encode_result(fields: dict[str, str], output: str) -> bytes:
    """Pack one result the way the target's runner writes it.

    Only the host uses this, to build the fixtures its tests decode and to
    clear the region before a run; the runner writes the same bytes with dd.
    """
    payload = output.encode()
    truncated = len(payload) > RESULT_OUTPUT_BYTES
    payload = payload[:RESULT_OUTPUT_BYTES]
    header = _header(
        {
            "direction": "target-to-host",
            "kind": "result",
            **fields,
            "output_bytes": str(len(payload)),
            "truncated": "1" if truncated else "0",
        }
    )
    sectors = -(-len(payload) // SECTOR_SIZE)
    return header + payload.ljust(sectors * SECTOR_SIZE, b"\0")


def decode_result(data: bytes) -> dict | None:
    """Read a result region; None if the runner has not written one.

    The output is bounded by the byte count in the header rather than by the
    NUL padding, so a result shorter than the one before it does not come back
    with the tail of its predecessor attached.
    """
    records = decode_records(data[:SECTOR_SIZE])
    if not records or records[0].get("kind") != "result":
        return None
    fields = dict(records[0])
    fields.pop("sector", None)
    try:
        length = min(int(fields.get("output_bytes", 0)), RESULT_OUTPUT_BYTES)
    except ValueError:
        return None
    result = {
        key: value for key, value in fields.items() if key not in ("direction", "kind")
    }
    for key in ("sequence", "exit", "output_bytes", "truncated"):
        if key in result:
            try:
                result[key] = int(result[key])
            except ValueError:
                pass
    result["output"] = data[SECTOR_SIZE : SECTOR_SIZE + length].decode(errors="replace")
    return result


def clear_region(sectors: int) -> bytes:
    """Zeroes to write over a region so a stale record cannot be read as new."""
    return bytes(sectors * SECTOR_SIZE)


def kernel_log(dump: bytes) -> str:
    """Return the flight recorder's text from a dump of the debug partition.

    The page is raw log text, not a record, so that all of it is log; the
    padding dd adds and the erased flash behind a short first snapshot are
    dropped rather than shown.
    """
    start = KERNEL_LOG_SECTOR * SECTOR_SIZE
    page = dump[start : start + KERNEL_LOG_SECTORS * SECTOR_SIZE]
    return page.replace(b"\xff", b"").replace(b"\0", b"").decode("utf-8", "replace")
