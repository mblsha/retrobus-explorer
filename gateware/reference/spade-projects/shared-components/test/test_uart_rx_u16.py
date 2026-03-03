# top = tb_uart_rx_u16

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


BIT_TIME = 10
WIDTH = 16


def _odd_parity(word: int) -> int:
    return bin(word & ((1 << WIDTH) - 1)).count("1") & 1


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
            events.append((int(dut.rx_parity_error.value), int(dut.rx_word.value)))


async def _drive_bit(dut, bit: int, events: list[tuple[int, int]]):
    dut.rx_line.value = bit
    await _tick_and_capture(dut, BIT_TIME, events)


async def _send_frame(
    dut,
    payload: int,
    events: list[tuple[int, int]],
    *,
    parity_enabled: bool,
    stop_bits: int,
    parity_bit: int | None = None,
):
    await _drive_bit(dut, 0, events)
    for bit_idx in range(WIDTH):
        await _drive_bit(dut, (payload >> bit_idx) & 1, events)

    if parity_enabled:
        bit = _odd_parity(payload) if parity_bit is None else parity_bit
        await _drive_bit(dut, bit, events)

    for _ in range(stop_bits):
        await _drive_bit(dut, 1, events)


@cocotb.test()
async def receives_back_to_back_u16_frames(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    events: list[tuple[int, int]] = []

    first = 0xA55A
    second = 0x1234
    await _send_frame(dut, first, events, parity_enabled=False, stop_bits=1)
    await _send_frame(dut, second, events, parity_enabled=False, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, first), (0, second)]


@cocotb.test()
async def parity_check_u16_frames(dut):
    await _init_test(dut, stop_bits=1, parity=1)
    events: list[tuple[int, int]] = []

    good = 0xBEEF
    bad = 0x00F0
    await _send_frame(dut, good, events, parity_enabled=True, stop_bits=1)
    await _send_frame(
        dut,
        bad,
        events,
        parity_enabled=True,
        stop_bits=1,
        parity_bit=_odd_parity(bad) ^ 1,
    )
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, good), (1, bad)]
