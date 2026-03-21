#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import ctypes
import sys
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


def find_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "py" / "d3xx").exists() and (parent / "gateware" / "reference").exists():
            return parent
    raise RuntimeError("failed to locate retrobus-explorer repo root")


def load_d3xx_modules() -> tuple[object, object]:
    d3xx_dir = find_repo_root() / "py" / "d3xx"
    if str(d3xx_dir) not in sys.path:
        sys.path.append(str(d3xx_dir))
    try:
        import _ftd3xx_linux as mft  # type: ignore
        import ftd3xx  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(f"failed to import D3XX modules from {d3xx_dir}") from exc
    return mft, ftd3xx


class D3xxReader:
    def __init__(self, device_index: int, channel: int, timeout_ms: int) -> None:
        mft, ftd3xx = load_d3xx_modules()
        self._mft = mft
        self._ftd3xx = ftd3xx
        self._channel = channel
        self._timeout_ms = timeout_ms
        self._dev = ftd3xx.create(device_index, mft.FT_OPEN_BY_INDEX)
        if self._dev is None:
            raise RuntimeError("failed to open FT600 device via D3XX")

    def read(self, size: int) -> bytes:
        bytes_transferred = self._mft.ULONG()
        data = ctypes.create_string_buffer(size)
        self._ftd3xx.call_ft(
            self._mft.FT_ReadPipeEx,
            self._dev.handle,
            self._mft.UCHAR(self._channel),
            data,
            self._mft.ULONG(size),
            ctypes.byref(bytes_transferred),
            self._timeout_ms,
        )
        return data.raw[:bytes_transferred.value]

    def close(self) -> None:
        if getattr(self, "_dev", None) is not None:
            self._dev.close()
            self._dev = None


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
    duration_s: float | None = 60.0,
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
    duration_s: float | None = 60.0,
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


def format_capture_start(
    *,
    raw_out: Path,
    vcd_out: Path | None,
    duration_s: float | None,
    idle_timeout_s: float | None,
    max_bytes: int | None,
) -> str:
    parts = [f"raw={raw_out}"]
    if vcd_out is not None:
        parts.append(f"vcd={vcd_out}")
    if duration_s is not None:
        parts.append(f"duration={duration_s:g}s")
    if idle_timeout_s is not None:
        parts.append(f"idle_timeout={idle_timeout_s:g}s")
    if max_bytes is not None:
        parts.append(f"max_bytes={max_bytes}")
    return "starting FT capture: " + ", ".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture PC-E500 FT600 stream to .ft16 and optional .vcd")
    parser.add_argument("--device-index", type=int, default=0, help="FT600 device index for D3XX open")
    parser.add_argument("--channel", type=int, default=0, help="FT600 FIFO channel")
    parser.add_argument("--read-timeout-ms", type=int, default=100, help="D3XX read timeout in milliseconds")
    parser.add_argument("--raw-out", type=Path, required=True, help="output .ft16 capture path")
    parser.add_argument("--vcd-out", type=Path, help="optional output VCD path")
    parser.add_argument("--duration", type=float, default=60.0, help="capture duration in seconds")
    parser.add_argument("--idle-timeout", type=float, help="optional stop after this many idle seconds")
    parser.add_argument("--chunk-size", type=int, default=32768, help="host read chunk size in bytes")
    parser.add_argument("--max-bytes", type=int, help="optional hard cap on captured bytes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = D3xxReader(
        device_index=args.device_index,
        channel=args.channel,
        timeout_ms=args.read_timeout_ms,
    )
    try:
        print(
            format_capture_start(
                raw_out=args.raw_out,
                vcd_out=args.vcd_out,
                duration_s=args.duration,
                idle_timeout_s=args.idle_timeout,
                max_bytes=args.max_bytes,
            ),
            flush=True,
        )
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
