#!/usr/bin/env python3
"""Measure existing DDR reads and cached replies; requires already disarmed SD."""

import argparse
import hashlib
import json
import time

from images import CAPACITY_SECTORS, DEFAULT_WINDOW, MAX_WINDOW, SECTOR_BYTES, Images

# Preamble/SFD + Ethernet + IPv4 + UDP + application header/CRC + FCS + IFG.
FRAME_OVERHEAD_BYTES = 8 + 14 + 20 + 8 + 24 + 4 + 4 + 12
LEGACY_FRAME_BYTES = SECTOR_BYTES + FRAME_OVERHEAD_BYTES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--bulk", action="store_true")
    parser.add_argument(
        "--window", type=int, default=DEFAULT_WINDOW, choices=range(1, MAX_WINDOW + 1)
    )
    parser.add_argument("--blocks", type=int, default=8192)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    if not 1 <= args.blocks <= CAPACITY_SECTORS or not 1 <= args.repeats <= 10:
        parser.error("Require 1..524288 blocks and 1..10 repeats")
    client = Images(state=args.state)
    results = []
    try:
        for run in range(args.repeats):
            retries = client.retries
            start = time.monotonic()
            data = (
                client.bulk_download(args.blocks, window=args.window)
                if args.bulk
                else client.download(args.blocks)
            )
            elapsed = time.monotonic() - start
            digest = hashlib.sha256(data).hexdigest()
            if digest != args.expected_sha256:
                raise RuntimeError("DDR data differs from expected image")
            results.append(
                dict(
                    mode="bulk_download" if args.bulk else "ddr_download",
                    window=args.window if args.bulk else 1,
                    run=run,
                    bytes=len(data),
                    seconds=elapsed,
                    payload_mbps=len(data) * 8 / elapsed / 1e6,
                    retries=client.retries - retries,
                    sha256=digest,
                )
            )
        # Exact replay measures the same MAC/IP/UDP path without new DDR reads
        # or per-request session-file writes. It does not measure unique data.
        if not args.bulk:
            request = client.last_request
            expected = (0, data[-SECTOR_BYTES:])
            retries = client.retries
            start = time.monotonic()
            for _ in range(args.blocks):
                if client.exchange(request) != expected:
                    raise RuntimeError("Cached reply differs from expected image")
            elapsed = time.monotonic() - start
            results.append(
                dict(
                    mode="cached_reply",
                    replies=args.blocks,
                    seconds=elapsed,
                    payload_mbps=args.blocks * SECTOR_BYTES * 8 / elapsed / 1e6,
                    retries=client.retries - retries,
                )
            )
        # Each successful transaction has a 540-byte UDP payload in each
        # direction: 8 preamble/SFD + 14 Ethernet + 20 IP + 8 UDP + 540
        # application + 4 FCS + 12 IFG = 606 byte-times. Do not sum directions
        # when comparing with a 100 Mbps full-duplex link.
        for result in results:
            if args.bulk:
                requests = (args.blocks + 1) // 2
                result["request_wire_mbps"] = (
                    requests * FRAME_OVERHEAD_BYTES * 8 / result["seconds"] / 1e6
                )
                result["reply_wire_mbps"] = (
                    (args.blocks * SECTOR_BYTES + requests * FRAME_OVERHEAD_BYTES)
                    * 8
                    / result["seconds"]
                    / 1e6
                )
            else:
                result["successful_frames_wire_mbps_per_direction"] = (
                    result["payload_mbps"] * LEGACY_FRAME_BYTES / SECTOR_BYTES
                )
        print(
            json.dumps(
                dict(
                    results=results,
                    image_unchanged=True,
                    wire_rate_note="Calculated from validated replies and "
                    "frame sizes plus preamble/FCS/IFG; excludes retries/background traffic.",
                ),
                indent=2,
            )
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
