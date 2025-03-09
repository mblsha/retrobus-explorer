from z80bus.bus_parser import (
    SimpleBusParser,
    BusParser,
    PipelineBusParser,
    Event,
    ErrorType,
    Type,
    IOPort,
)
import z80bus.bus_parser as bus_parser

from typing import List, Tuple
import struct
import queue


def pipeline_parse(input: bytes):
    errors_queue = queue.Queue()
    out_ports_queue = queue.Queue()
    p = PipelineBusParser(errors_queue, out_ports_queue, save_all_events=True)

    buf = b""
    for b in input:
        buf += bytes([b])
        left_buf = p.parse(buf)
        buf = left_buf

    p.flush()

    errors = []
    while not errors_queue.empty():
        errors.append(errors_queue.get())
    if len(buf) > 0:
        errors.append(f"Trailing data")

    return p.all_events, errors


def normal_parse(b: bytes) -> Tuple[List[Event], List[str]]:
    normal_events, normal_errors = BusParser().parse(b)
    pipe_events, pipe_errors = pipeline_parse(b)
    assert len(normal_events) == len(pipe_events)
    assert normal_events == pipe_events
    assert len(normal_errors) == len(pipe_errors)
    assert normal_errors == pipe_errors
    return normal_events, normal_errors


def parse(b: bytes) -> Event:
    events, errors = normal_parse(b)
    assert not errors
    assert len(events) == 1
    return events[0]


def not_parse(b: bytes) -> Event:
    events, errors = normal_parse(b)
    assert len(events) == 0
    assert len(errors) > 0


def parsel(b: bytes) -> List[Event]:
    events, errors = normal_parse(b)
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


def error(type: ErrorType, value: int) -> bytes:
    assert type == ErrorType.BUFFER_FULL
    return (
        b"E"
        + struct.pack("B", value & 0xFF)
        + struct.pack("B", (value >> 8) & 0xFF)
        + struct.pack("B", (value >> 16) & 0xFF)
    )


def test_error() -> None:
    assert parse(b"E\xfer\x00") == Event(
        type=Type.ERROR,
        val=0x72FE,
        addr=0,
    )
    assert parse(error(ErrorType.BUFFER_FULL, 0x72FE)) == Event(
        type=Type.ERROR,
        val=0x72FE,
        addr=0,
    )


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
    assert parsel(fetch(0xCB, 0x1000) + fetch(0xCB, 0x1001) + fetch(0xCB, 0x1002)) == [
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
        Event(
            type=Type.FETCH,
            val=0xCB,
            addr=0x1002,
            pc=0x1002,
            instr=bus_parser.InstructionType.MULTI_PREFIX,
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


def test_call_unconditional():
    # this test is relatively complicated as the CALL instruction needs
    # three instructions to fetch, and only then it writes to the stack
    # before jumping to the target address.

    # cc5b8a CALL Z,0x8A5B
    data = (
        fetch(0xCC, 0x895F)
        + read(0x5B, 0x8960)
        + read(0x8A, 0x8961)
        + write(0x89, 0x7FEF)
        + write(0x62, 0x7FEE)
    )
    # 3e00 LD A,0x00
    data += fetch(0x3E, 0x8A5B) + read(0x00, 0x8A5C)

    assert parsel(data) == [
        Event(
            type=Type.FETCH,
            val=0xCC,
            addr=0x895F,
            pc=0x895F,
            bank=0,
            instr=bus_parser.InstructionType.CALL,
        ),
        Event(
            type=Type.READ,
            val=0x5B,
            addr=0x8960,
            bank=0,
            pc=0x895F,
        ),
        Event(
            type=Type.READ,
            val=0x8A,
            addr=0x8961,
            bank=0,
            pc=0x895F,
        ),
        Event(
            type=Type.WRITE_STACK,
            val=0x89,
            addr=0x7FEF,
            pc=0x895F,
        ),
        Event(
            type=Type.WRITE_STACK,
            val=0x62,
            addr=0x7FEE,
            pc=0x895F,
        ),
        Event(
            type=Type.FETCH,
            val=0x3E,
            addr=0x8A5B,
            bank=0,
            pc=0x8A5B,
        ),
        Event(
            type=Type.READ,
            val=0x00,
            addr=0x8A5C,
            bank=0,
            pc=0x8A5B,
        ),
    ]


def test_bank_number_for_address():
    assert bus_parser.bank_number_for_address(0x4000) == None
    assert bus_parser.bank_number_for_address(0x8000) == 0
    assert bus_parser.bank_number_for_address(0xC000) == 1
    assert bus_parser.bank_number_for_address(0xC000 + 0x100) == 1
    assert bus_parser.bank_number_for_address(0xC000 + 1 * bus_parser.BANK_SIZE) == 2
    assert bus_parser.bank_number_for_address(0xC000 + 2 * bus_parser.BANK_SIZE) == 3


def test_extend_address():
    assert bus_parser.extend_address(0x4000, 0x4000) == 0x4000
    assert bus_parser.extend_address(0x8000, 0x8100) == 0x8100
    assert bus_parser.extend_address(0xC000, 0xC100) == 0xC100
    assert bus_parser.extend_address(0xC000, 0xFFFF) == 0xFFFF
    assert bus_parser.extend_address(0xC000 + 1 * bus_parser.BANK_SIZE, 0xFFFF) == 0xFFFF + 1 * bus_parser.BANK_SIZE
