#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator


FT_RECORD_WORDS = 5
FT_RECORD_BITS = 80
FT_WORD_MASK = 0xFFFF
FT_KIND_SHIFT = 72
FT_DELTA_SHIFT = 40
FT_ADDR_SHIFT = 22
FT_DATA_SHIFT = 14
FT_AUX_MASK = 0x3FFF
FT_DELTA_MASK = 0xFFFFFFFF
FT_ADDR_MASK = 0x3FFFF
FT_DATA_MASK = 0xFF
FT_STREAM_VERSION = 1
TICK_NS = 10


class FtKind(IntEnum):
    CE1_READ = 0x01
    CE1_WRITE = 0x02
    CE6_READ = 0x03
    CE6_WRITE_ATTEMPT = 0x04
    SYNC = 0xF0
    OVERFLOW = 0xF1
    CONFIG = 0xF2


class FtStreamVersionError(ValueError):
    pass


@dataclass(frozen=True)
class FtAux:
    rw: bool
    oe: bool
    ce1: bool
    ce6: bool
    same_addr: bool
    same_data: bool
    classified_after_delay: bool
    raw: int


@dataclass(frozen=True)
class FtRecord:
    kind: FtKind
    delta_ticks: int
    addr: int
    data: int
    aux: FtAux
    raw: int


@dataclass(frozen=True)
class TimedFtRecord:
    tick: int
    record: FtRecord


def decode_ft_aux(raw: int) -> FtAux:
    return FtAux(
        rw=bool(raw & (1 << 0)),
        oe=bool(raw & (1 << 1)),
        ce1=bool(raw & (1 << 2)),
        ce6=bool(raw & (1 << 3)),
        same_addr=bool(raw & (1 << 4)),
        same_data=bool(raw & (1 << 5)),
        classified_after_delay=bool(raw & (1 << 6)),
        raw=raw & FT_AUX_MASK,
    )


def decode_ft_record(raw: int) -> FtRecord:
    kind = FtKind((raw >> FT_KIND_SHIFT) & 0xFF)
    delta_ticks = (raw >> FT_DELTA_SHIFT) & FT_DELTA_MASK
    addr = (raw >> FT_ADDR_SHIFT) & FT_ADDR_MASK
    data = (raw >> FT_DATA_SHIFT) & FT_DATA_MASK
    aux = decode_ft_aux(raw & FT_AUX_MASK)
    return FtRecord(kind=kind, delta_ticks=delta_ticks, addr=addr, data=data, aux=aux, raw=raw)


def ft_record_from_words(words: Iterable[int]) -> FtRecord:
    record = 0
    words_list = list(words)
    if len(words_list) != FT_RECORD_WORDS:
        raise ValueError(f"expected {FT_RECORD_WORDS} FT words, got {len(words_list)}")
    for idx, word in enumerate(words_list):
        record |= (word & FT_WORD_MASK) << (16 * idx)
    return decode_ft_record(record)


def iter_ft_words_from_bytes(raw: bytes) -> Iterator[int]:
    if len(raw) % 2 != 0:
        raise ValueError(f"expected even number of bytes, got {len(raw)}")
    for idx in range(0, len(raw), 2):
        yield int.from_bytes(raw[idx:idx + 2], "little")


def iter_ft_words_from_stream(stream: BinaryIO, chunk_bytes: int = 8192) -> Iterator[int]:
    if chunk_bytes <= 0 or chunk_bytes % 2 != 0:
        raise ValueError(f"chunk_bytes must be a positive even number, got {chunk_bytes}")
    trailing = b""
    while True:
        chunk = stream.read(chunk_bytes)
        if not chunk:
            break
        data = trailing + chunk
        if len(data) % 2 != 0:
            trailing = data[-1:]
            data = data[:-1]
        else:
            trailing = b""
        yield from iter_ft_words_from_bytes(data)
    if trailing:
        raise ValueError("expected even number of bytes at end of FT stream")


def iter_ft_records_from_words(words: Iterable[int]) -> Iterator[FtRecord]:
    chunk: list[int] = []
    for word in words:
        chunk.append(word)
        if len(chunk) == FT_RECORD_WORDS:
            yield ft_record_from_words(chunk)
            chunk.clear()
    if chunk:
        raise ValueError(f"incomplete FT record: got {len(chunk)} trailing words")


def iter_ft_records_from_bytes(raw: bytes) -> Iterator[FtRecord]:
    yield from iter_ft_records_from_words(iter_ft_words_from_bytes(raw))


def iter_ft_records_from_path(path: str | Path) -> Iterator[FtRecord]:
    with Path(path).open("rb") as handle:
        yield from iter_ft_records_from_words(iter_ft_words_from_stream(handle))


def iter_timed_records(records: Iterable[FtRecord]) -> Iterator[TimedFtRecord]:
    tick = 0
    for record in records:
        tick += record.delta_ticks
        yield TimedFtRecord(tick=tick, record=record)


def overflow_count(record: FtRecord) -> int:
    if record.kind != FtKind.OVERFLOW:
        raise ValueError("overflow_count only applies to OVERFLOW records")
    return record.addr | (record.data << 18)


def config_delay_ticks(record: FtRecord) -> int:
    if record.kind != FtKind.CONFIG:
        raise ValueError("config_delay_ticks only applies to CONFIG records")
    return record.addr


def config_enabled(record: FtRecord) -> bool:
    if record.kind != FtKind.CONFIG:
        raise ValueError("config_enabled only applies to CONFIG records")
    return bool(record.aux.raw & 0x1)


def sync_version(record: FtRecord) -> int:
    if record.kind != FtKind.SYNC:
        raise ValueError("sync_version only applies to SYNC records")
    return record.data


def iter_validated_ft_records(records: Iterable[FtRecord]) -> Iterator[FtRecord]:
    records_iter = iter(records)
    try:
        first = next(records_iter)
    except StopIteration as exc:
        raise FtStreamVersionError("empty FT capture") from exc
    if first.kind != FtKind.SYNC:
        raise FtStreamVersionError(f"expected first FT record to be SYNC, got {first.kind.name}")
    version = sync_version(first)
    if version != FT_STREAM_VERSION:
        raise FtStreamVersionError(f"unsupported FT stream version {version}, expected {FT_STREAM_VERSION}")
    yield first
    yield from records_iter


def validate_ft_records(records: Iterable[FtRecord]) -> list[FtRecord]:
    records_list = list(iter_validated_ft_records(records))
    if not records_list:
        raise FtStreamVersionError("empty FT capture")
    return records_list


def read_ft_records(path: str | Path) -> list[FtRecord]:
    return validate_ft_records(iter_ft_records_from_path(path))


def pack_ft_record(kind: FtKind, delta_ticks: int, addr: int, data: int, aux_raw: int) -> int:
    return (
        ((int(kind) & 0xFF) << FT_KIND_SHIFT)
        | ((delta_ticks & FT_DELTA_MASK) << FT_DELTA_SHIFT)
        | ((addr & FT_ADDR_MASK) << FT_ADDR_SHIFT)
        | ((data & FT_DATA_MASK) << FT_DATA_SHIFT)
        | (aux_raw & FT_AUX_MASK)
    )


def pack_ft_words(record: int) -> list[int]:
    return [(record >> (16 * idx)) & FT_WORD_MASK for idx in range(FT_RECORD_WORDS)]
