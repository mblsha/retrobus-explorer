# top = tb_uart_tx_adapter_equiv

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


CLK_PER_BIT = (100_000_000 + 1_000_000) // 1_000_000 - 1
FRAME_BUSY_CYCLES = (1 + 8 + 1) * CLK_PER_BIT


def _bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


async def _tick_and_compare(dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert _bit(dut.adapter_line) == _bit(dut.direct_line)
    assert _bit(dut.adapter_busy) == _bit(dut.direct_busy)


async def _init(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.block.value = 0
    dut.tx_valid.value = 0
    dut.tx_byte.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    for _ in range(4):
        await _tick_and_compare(dut)
    assert _bit(dut.direct_line) == 1
    assert _bit(dut.direct_busy) == 0


@cocotb.test()
async def adapter_matches_direct_uart_when_block_is_false(dut):
    await _init(dut)
    rng = random.Random(0x7A17_2026)

    dut.tx_byte.value = 0xA5
    dut.tx_valid.value = 1
    await _tick_and_compare(dut)
    dut.tx_valid.value = 0

    assert _bit(dut.direct_busy) == 1
    assert _bit(dut.direct_line) == 1, "acceptance cycle precedes the start bit"

    busy_cycles = 1
    saw_start_bit = False
    while _bit(dut.direct_busy):
        # Requests presented while busy are ignored by both paths. Randomizing
        # them protects that acceptance behavior while comparing every cycle.
        dut.tx_valid.value = rng.randrange(2)
        dut.tx_byte.value = rng.randrange(256)
        await _tick_and_compare(dut)
        saw_start_bit |= _bit(dut.direct_line) == 0
        if _bit(dut.direct_busy):
            busy_cycles += 1

    dut.tx_valid.value = 0
    assert saw_start_bit
    assert busy_cycles == FRAME_BUSY_CYCLES, (
        f"unexpected busy duration: expected={FRAME_BUSY_CYCLES} got={busy_cycles}"
    )


@cocotb.test()
async def adapter_filters_same_cycle_valid_when_block_is_asserted(dut):
    await _init(dut)

    # The request adapter intentionally gates same-cycle block+valid even though
    # the raw UART registers block internally and would accept that request.
    dut.block.value = 1
    dut.tx_valid.value = 1
    dut.tx_byte.value = 0x3C
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")

    dut.tx_valid.value = 0
    dut.block.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")

    assert _bit(dut.adapter_line) == 1, "blocked adapter request must not start a frame"
    assert _bit(dut.adapter_busy) == 0
    assert _bit(dut.direct_busy) == 1, (
        "raw UART accepts same-cycle block+valid because block is registered"
    )
    assert _bit(dut.direct_line) == 0
