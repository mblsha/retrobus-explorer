from pathlib import Path
import argparse
import tempfile
import subprocess
import hashlib
import json
from microsd_verify_linux_rw import validate_target

p = argparse.ArgumentParser(
    description="Read-only persistence check of the standard SPADE filesystem test files"
)
p.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
p.add_argument("--clock-hz", type=int, required=True)
p.add_argument("--actual-clock-hz", type=int, required=True)
a = p.parse_args()
validate_target(a.bus_width, 256 << 20, a.clock_hz, a.actual_clock_hz)
expected = [
    {
        "path": "CHECK.TXT",
        "bytes": 51,
        "sha256": "b857c8995919c5b4df7e6fd1122899dcf5c8c9a4c57f09f3a777c543a7908713",
        "passed": True,
    },
    {
        "path": "TESTDIR/RENAMED.BIN",
        "bytes": 65536,
        "sha256": "35b0dc347f758ccebf78aadbf7538ce4e093df7b9049e908c5a688bdb944ab27",
        "passed": True,
    },
    {
        "path": "TESTDIR/SMALL.BIN",
        "bytes": 4096,
        "sha256": "e601b829ed9aa8388f71e8c70e9a388a14270ba82d49617cde6638fe9678bf0d",
        "passed": True,
    },
]
point = Path(tempfile.mkdtemp(prefix="codex-spade-persistence-"))
subprocess.run(
    ["mount", "-t", "vfat", "-o", "ro,nodev,nosuid,noexec", "/dev/mmcblk1", str(point)],
    check=True,
)
try:
    for row in expected:
        data = (point / row["path"]).read_bytes()
        assert (
            len(data) == row["bytes"]
            and hashlib.sha256(data).hexdigest() == row["sha256"]
        )
finally:
    subprocess.run(["umount", str(point)], check=True)
    point.rmdir()
print(json.dumps(dict(checks=expected, unmounted=True, passed=True), indent=2))
