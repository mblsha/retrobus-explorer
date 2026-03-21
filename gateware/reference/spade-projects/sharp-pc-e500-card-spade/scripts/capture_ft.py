#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyftdi>=0.56"]
# ///
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from e500_ft import FT_RECORD_WORDS, iter_ft_records_from_path
from ft_to_vcd import write_vcd


FT_RECORD_BYTES = FT_RECORD_WORDS * 2


class ByteReader(Protocol):
    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class CaptureStats:
    raw_bytes: int
    aligned_bytes: int
    trimmed_bytes: int
    chunks: int


class PyFtdiReader:
    def __init__(self, url: str) -> None:
        from pyftdi.ftdi import Ftdi

        self._ftdi = Ftdi()
        self._ftdi.open_from_url(url=url)
        if hasattr(self._ftdi, "purge_buffers"):
            self._ftdi.purge_buffers()

    def read(self, size: int) -> bytes:
        return bytes(self._ftdi.read_data(size))

    def close(self) -> None:
        self._ftdi.close()


def _truncate_to_ft_records(path: Path, raw_bytes: int, chunks: int) -> CaptureStats:
    aligned_bytes = raw_bytes - (raw_bytes % FT_RECORD_BYTES)
    trimmed_bytes = raw_bytes - aligned_bytes
    if trimmed_bytes:
        with path.open("r+b") as handle:
            handle.truncate(aligned_bytes)
    return CaptureStats(
        raw_bytes=raw_bytes,
        aligned_bytes=aligned_bytes,
        trimmed_bytes=trimmed_bytes,
        chunks=chunks,
    )


def capture_stream(
    reader: ByteReader,
    raw_out: Path,
    *,
    chunk_size: int = 4096,
    duration_s: float | None = 5.0,
    idle_timeout_s: float | None = 0.25,
    max_bytes: int | None = None,
    poll_interval_s: float = 0.01,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> CaptureStats:
    if duration_s is None and idle_timeout_s is None and max_bytes is None:
        raise ValueError("capture needs at least one stop condition")

    raw_bytes = 0
    chunks = 0
    started_at = now()
    last_data_at = started_at

    with raw_out.open("wb") as handle:
        while True:
            if duration_s is not None and now() - started_at >= duration_s:
                break
            if max_bytes is not None and raw_bytes >= max_bytes:
                break

            data = reader.read(chunk_size)
            if data:
                if max_bytes is not None:
                    remaining = max_bytes - raw_bytes
                    if remaining <= 0:
                        break
                    data = data[:remaining]
                handle.write(data)
                raw_bytes += len(data)
                chunks += 1
                last_data_at = now()
                continue

            if idle_timeout_s is not None and now() - last_data_at >= idle_timeout_s:
                break
            sleep(poll_interval_s)

    return _truncate_to_ft_records(raw_out, raw_bytes, chunks)


def write_vcd_from_capture(raw_path: Path, vcd_path: Path) -> None:
    with vcd_path.open("w") as handle:
        write_vcd(iter_ft_records_from_path(raw_path), handle)


def capture_to_vcd(
    reader: ByteReader,
    *,
    raw_out: Path,
    vcd_out: Path | None,
    chunk_size: int = 4096,
    duration_s: float | None = 5.0,
    idle_timeout_s: float | None = 0.25,
    max_bytes: int | None = None,
    poll_interval_s: float = 0.01,
    now: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> CaptureStats:
    stats = capture_stream(
        reader,
        raw_out,
        chunk_size=chunk_size,
        duration_s=duration_s,
        idle_timeout_s=idle_timeout_s,
        max_bytes=max_bytes,
        poll_interval_s=poll_interval_s,
        now=now,
        sleep=sleep,
    )
    if vcd_out is not None:
        write_vcd_from_capture(raw_out, vcd_out)
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture PC-E500 FT stream to .ft16 and optional .vcd")
    parser.add_argument("--url", required=True, help="pyftdi URL, for example ftdi://ftdi:2232h/2")
    parser.add_argument("--raw-out", type=Path, required=True, help="output .ft16 capture path")
    parser.add_argument("--vcd-out", type=Path, help="optional output VCD path")
    parser.add_argument("--duration", type=float, default=5.0, help="capture duration in seconds")
    parser.add_argument("--idle-timeout", type=float, default=0.25, help="stop after this many idle seconds")
    parser.add_argument("--chunk-size", type=int, default=4096, help="host read chunk size in bytes")
    parser.add_argument("--max-bytes", type=int, help="optional hard cap on captured bytes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = PyFtdiReader(args.url)
    try:
        stats = capture_to_vcd(
            reader,
            raw_out=args.raw_out,
            vcd_out=args.vcd_out,
            chunk_size=args.chunk_size,
            duration_s=args.duration,
            idle_timeout_s=args.idle_timeout,
            max_bytes=args.max_bytes,
        )
    finally:
        reader.close()

    print(
        f"captured {stats.aligned_bytes} bytes in {stats.chunks} chunk(s)"
        + (f", trimmed {stats.trimmed_bytes} trailing byte(s)" if stats.trimmed_bytes else "")
    )
    if args.vcd_out is not None:
        print(f"wrote {args.vcd_out}")
    print(f"wrote {args.raw_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
