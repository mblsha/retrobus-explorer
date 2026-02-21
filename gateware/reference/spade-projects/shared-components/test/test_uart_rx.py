# top = tb_uart_rx

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


BIT_TIME = 10


def _odd_parity(byte: int) -> int:
    return bin(byte & 0xFF).count("1") & 1


async def _init_test(dut, stop_bits: int, parity: int):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.rx_line.value = 1
    dut.bit_time.value = BIT_TIME
    dut.parity.value = parity
    dut.stop_bits.value = stop_bits

    await tick(dut.clk, 2)
    dut.rst.value = 0
    await tick(dut.clk, BIT_TIME)


async def _tick_and_capture(dut, cycles: int, events: list[tuple[int, int]]):
    for _ in range(cycles):
        await tick(dut.clk, 1)
        if int(dut.rx_valid.value) == 1:
            events.append((int(dut.rx_parity_error.value), int(dut.rx_byte.value)))


async def _drive_bit(dut, bit: int, events: list[tuple[int, int]]):
    dut.rx_line.value = bit
    await _tick_and_capture(dut, BIT_TIME, events)


async def _send_frame(
    dut,
    payload: int,
    events: list[tuple[int, int]],
    parity_enabled: bool,
    stop_bits: int,
    parity_bit: int | None = None,
):
    await _drive_bit(dut, 0, events)
    for bit_idx in range(8):
        await _drive_bit(dut, (payload >> bit_idx) & 1, events)

    if parity_enabled:
        bit = _odd_parity(payload) if parity_bit is None else parity_bit
        await _drive_bit(dut, bit, events)

    for _ in range(stop_bits):
        await _drive_bit(dut, 1, events)


@cocotb.test()
async def test(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    events: list[tuple[int, int]] = []
    await _tick_and_capture(dut, BIT_TIME * 2, events)
    assert events == []

    payload = 0x0A
    await _send_frame(dut, payload, events, parity_enabled=False, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)
    assert events == [(0, payload)]


@cocotb.test()
async def quick_succession_works(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(dut, first, events, parity_enabled=False, stop_bits=1)
    await _send_frame(dut, second, events, parity_enabled=False, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, first), (0, second)]


@cocotb.test()
async def correct_parity(dut):
    await _init_test(dut, stop_bits=1, parity=1)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(dut, first, events, parity_enabled=True, stop_bits=1)
    await _send_frame(dut, second, events, parity_enabled=True, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, first), (0, second)]


@cocotb.test()
async def incorrect_parity(dut):
    await _init_test(dut, stop_bits=1, parity=1)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(
        dut,
        first,
        events,
        parity_enabled=True,
        stop_bits=1,
        parity_bit=_odd_parity(first) ^ 1,
    )
    await _send_frame(
        dut,
        second,
        events,
        parity_enabled=True,
        stop_bits=1,
        parity_bit=_odd_parity(second) ^ 1,
    )
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(1, first), (1, second)]


@cocotb.test()
async def multiple_stop_bits_work(dut):
    await _init_test(dut, stop_bits=2, parity=0)
    events: list[tuple[int, int]] = []

    payload = 0x0A
    await _send_frame(dut, payload, events, parity_enabled=False, stop_bits=2)
    await _tick_and_capture(dut, BIT_TIME, events)
    assert events == [(0, payload)]

    await _tick_and_capture(dut, BIT_TIME * 4, events)
    assert events == [(0, payload)]
