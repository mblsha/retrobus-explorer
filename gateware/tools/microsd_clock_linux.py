#!/usr/bin/env python3
"""Set a diagnostic clock on the verified external SPADE card, while idle.

Never run concurrently with a read/write test. This does not change the CSD;
clocks above its advertised rate are margin experiments, not qualified modes.
"""

import argparse
import json
from pathlib import Path
from microsd_verify_linux_rw import validate_target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clock-hz", type=int, required=True)
    p.add_argument("--bus-width", type=int, choices=(1, 4), required=True)
    p.add_argument("--max-request-kib", type=int, choices=(64, 256, 1024))
    p.add_argument("--keep-awake", action="store_true")
    a = p.parse_args()
    assert 400000 <= a.clock_hz <= 25000000
    base = Path("/sys/kernel/debug/mmc1")
    before = (base / "ios").read_text()
    fields = dict(line.split(":", 1) for line in before.splitlines())
    current = int(fields["clock"].strip().split()[0])
    actual = int(fields.get("actual clock", fields["clock"]).strip().split()[0])
    validate_target(a.bus_width, 256 << 20, current, actual)
    card = Path("/sys/class/mmc_host/mmc1/mmc1:0001")
    power = card / "power/control"
    limit = Path("/sys/class/block/mmcblk1/queue/max_sectors_kb")
    host_before = dict(
        power_control=power.read_text().strip(),
        max_sectors_kb=limit.read_text().strip(),
    )
    if a.keep_awake:
        power.write_text("on")
    if a.max_request_kib is not None:
        limit.write_text(str(a.max_request_kib))
    # The host may omit actual_clock until the requested clock changes.
    clock = base / "clock"
    if current == a.clock_hz:
        clock.write_text(str(400000 if current != 400000 else 1000000))
    clock.write_text(str(a.clock_hz))
    after = (base / "ios").read_text()
    fields = dict(line.split(":", 1) for line in after.splitlines())
    requested = int(fields["clock"].strip().split()[0])
    assert requested == a.clock_hz
    assert "actual clock" in fields, "Host did not expose the actual divider clock"
    actual = int(fields["actual clock"].strip().split()[0])
    validate_target(a.bus_width, 256 << 20, requested, actual)
    print(
        json.dumps(
            dict(
                requested_clock_hz=requested,
                actual_clock_hz=actual,
                host_settings_before=host_before,
                host_settings_after=dict(
                    power_control=power.read_text().strip(),
                    max_sectors_kb=limit.read_text().strip(),
                ),
                before=before,
                after=after,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
