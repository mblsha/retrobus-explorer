from .bus_parser import RawDataParser, Event, Type, IOPort
from . import bus_parser

from typing import List
import struct


def parse(b: bytes) -> Event:
    events, errors = RawDataParser().parse(b)
    assert not errors
    assert len(events) == 1
    return events[0]


def not_parse(b: bytes) -> Event:
    events, errors = RawDataParser().parse(b)
    assert len(events) == 0
    assert len(errors) > 0


def parsel(b: bytes) -> List[Event]:
    events, errors = RawDataParser().parse(b)
    assert not errors
    assert len(events) > 1
    return events


def test_invalid_parse() -> None:
    not_parse(b"X\x12\x34\x56")
    not_parse(b"R\x12\x34")
    not_parse(b"R\x12")
    not_parse(b"R")


# helper functions to construct fake transmitted bytes
def read(val: int, addr: int) -> bytes:
    return b"R" + struct.pack("B", val) + struct.pack("<H", addr)


def write(val: int, addr: int) -> bytes:
    return b"W" + struct.pack("B", val) + struct.pack("<H", addr)


def in_port(val: int, port: IOPort) -> bytes:
    return b"r" + struct.pack("B", val) + struct.pack("<H", port.value)


def out_port(val: int, port: IOPort) -> bytes:
    return b"w" + struct.pack("B", val) + struct.pack("<H", port.value)


def fetch(val: int, addr: int) -> bytes:
    return b"M" + struct.pack("B", val) + struct.pack("<H", addr)


def test_fetch() -> None:
    assert parse(b"M\x12\x34\x56") == Event(
        type=Type.FETCH,
        val=0x12,
        addr=0x5634,
        pc=0x5634,
    )
    assert parse(fetch(0x12, 0x5634)) == Event(
        type=Type.FETCH,
        val=0x12,
        addr=0x5634,
        pc=0x5634,
    )


def test_memory_read() -> None:
    assert parse(b"R\x12\x34\x56") == Event(
        type=Type.READ,
        val=0x12,
        addr=0x5634,
    )
    assert parse(read(0x12, 0x5634)) == Event(
        type=Type.READ,
        val=0x12,
        addr=0x5634,
    )


def test_memory_write() -> None:
    assert parse(b"W\x12\x34\x56") == Event(
        type=Type.WRITE,
        val=0x12,
        addr=0x5634,
    )
    assert parse(write(0x12, 0x5634)) == Event(
        type=Type.WRITE,
        val=0x12,
        addr=0x5634,
    )


def test_in_port() -> None:
    assert parse(b"r\x12\x40\xff") == Event(
        type=Type.IN_PORT,
        val=0x12,
        addr=0x40,
        port=IOPort.LCD_COMMAND,
    )
    assert parse(in_port(0x12, IOPort.LCD_COMMAND)) == Event(
        type=Type.IN_PORT,
        val=0x12,
        addr=0x40,
        port=IOPort.LCD_COMMAND,
    )


def test_out_port() -> None:
    assert parse(b"w\x12\x40\xff") == Event(
        type=Type.OUT_PORT,
        val=0x12,
        addr=0x40,
        port=IOPort.LCD_COMMAND,
    )
    assert parse(out_port(0x12, IOPort.LCD_COMMAND)) == Event(
        type=Type.OUT_PORT,
        val=0x12,
        addr=0x40,
        port=IOPort.LCD_COMMAND,
    )


def test_set_rom_bank() -> None:
    assert parsel(
        out_port(0x1, IOPort.ROM_BANK) + read(0x12, bus_parser.BANK_ADDR_START)
    ) == [
        Event(
            type=Type.OUT_PORT,
            val=0x1,
            addr=IOPort.ROM_BANK.value,
            port=IOPort.ROM_BANK,
        ),
        Event(
            type=Type.READ,
            val=0x12,
            addr=bus_parser.BANK_ADDR_START,
            bank=0x1,
        ),
    ]

    assert parsel(
        out_port(0x2, IOPort.ROM_BANK) + read(0x12, bus_parser.BANK_ADDR_START)
    ) == [
        Event(
            type=Type.OUT_PORT,
            val=0x2,
            addr=IOPort.ROM_BANK.value,
            port=IOPort.ROM_BANK,
        ),
        Event(
            type=Type.READ,
            val=0x12,
            addr=bus_parser.BANK_ADDR_START + bus_parser.BANK_SIZE,
            bank=0x2,
        ),
    ]

    # now use ROM_EX_BANK
    assert parsel(
        out_port(0x3, IOPort.ROM_EX_BANK) + read(0x12, bus_parser.BANK_ADDR_START)
    ) == [
        Event(
            type=Type.OUT_PORT,
            val=0x3,
            addr=IOPort.ROM_EX_BANK.value,
            port=IOPort.ROM_EX_BANK,
        ),
        Event(
            type=Type.READ,
            val=0x12,
            addr=bus_parser.BANK_ADDR_START + bus_parser.BANK_SIZE * 2,
            bank=0x3,
        ),
    ]


# want two FETCH events to be transformed to FETCH+READ
def test_multi_prefix() -> None:
    assert parsel(fetch(0xCB, 0x1000) + fetch(0xCB, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0xCB,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.MULTI_PREFIX,
        ),
        Event(
            type=Type.READ,
            val=0xCB,
            addr=0x1001,
            pc=0x1000,
        ),
    ]


def test_two_fetch() -> None:
    assert parsel(fetch(0x12, 0x1000) + fetch(0x34, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0x12,
            addr=0x1000,
            pc=0x1000,
        ),
        Event(
            type=Type.FETCH,
            val=0x34,
            addr=0x1001,
            pc=0x1001,
        ),
    ]


def test_call() -> None:
    assert parsel(fetch(0xCD, 0x1000) + fetch(0x34, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0xCD,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.CALL,
        ),
        Event(
            type=Type.FETCH,
            val=0x34,
            addr=0x1001,
            pc=0x1001,
        ),
    ]


def test_ret() -> None:
    assert parsel(fetch(0xC9, 0x1000) + fetch(0x34, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0xC9,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.RET,
        ),
        Event(
            type=Type.FETCH,
            val=0x34,
            addr=0x1001,
            pc=0x1001,
        ),
    ]


def test_conditional_call() -> None:
    assert parsel(fetch(0xDC, 0x1000) + fetch(0x34, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0xDC,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.CALL_CONDITIONAL,
        ),
        Event(
            type=Type.FETCH,
            val=0x34,
            addr=0x1001,
            pc=0x1001,
        ),
    ]

    # if it tries to write stack then it would be a CALL
    assert parsel(
        fetch(0xDC, 0x1000) + write(0x34, bus_parser.ROM_ADDR_START - 10)
    ) == [
        Event(
            type=Type.FETCH,
            val=0xDC,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.CALL,
        ),
        Event(
            type=Type.WRITE_STACK,
            val=0x34,
            addr=bus_parser.ROM_ADDR_START - 10,
            pc=0x1000,
        ),
    ]

    # reads don't count
    assert parsel(fetch(0xDC, 0x1000) + read(0x34, bus_parser.ROM_ADDR_START - 10)) == [
        Event(
            type=Type.FETCH,
            val=0xDC,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.CALL_CONDITIONAL,
        ),
        Event(
            type=Type.READ_STACK,
            val=0x34,
            addr=bus_parser.ROM_ADDR_START - 10,
            pc=0x1000,
        ),
    ]


def test_conditional_ret() -> None:
    assert parsel(fetch(0xD8, 0x1000) + fetch(0x34, 0x1001)) == [
        Event(
            type=Type.FETCH,
            val=0xD8,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.RET_CONDITIONAL,
        ),
        Event(
            type=Type.FETCH,
            val=0x34,
            addr=0x1001,
            pc=0x1001,
        ),
    ]

    # if it tries to read stack then it would be a RET
    assert parsel(fetch(0xD8, 0x1000) + read(0x34, bus_parser.ROM_ADDR_START - 10)) == [
        Event(
            type=Type.FETCH,
            val=0xD8,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.RET,
        ),
        Event(
            type=Type.READ_STACK,
            val=0x34,
            addr=bus_parser.ROM_ADDR_START - 10,
            pc=0x1000,
        ),
    ]

    # writes don't count
    assert parsel(
        fetch(0xD8, 0x1000) + write(0x34, bus_parser.ROM_ADDR_START - 10)
    ) == [
        Event(
            type=Type.FETCH,
            val=0xD8,
            addr=0x1000,
            pc=0x1000,
            instr=bus_parser.InstructionType.RET_CONDITIONAL,
        ),
        Event(
            type=Type.WRITE_STACK,
            val=0x34,
            addr=bus_parser.ROM_ADDR_START - 10,
            pc=0x1000,
        ),
    ]
