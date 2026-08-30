# top = tb_uart_tx_tap_equiv

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def _bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


async def _tick_and_compare(dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert _bit(dut.tap_line) == _bit(dut.core_line)
    assert _bit(dut.tap_busy) == _bit(dut.core_busy)


@cocotb.test()
async def typed_uart_tap_preserves_core_line_and_busy(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.block.value = 0
    dut.tx_valid.value = 0
    dut.tx_byte.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)

    dut.rst.value = 0
    rng = random.Random(0x7A90_2026)
    saw_busy = False
    saw_start_bit = False
    for _ in range(800):
        dut.block.value = rng.randrange(2)
        dut.tx_valid.value = rng.randrange(2)
        dut.tx_byte.value = rng.randrange(256)
        await _tick_and_compare(dut)
        saw_busy |= bool(_bit(dut.core_busy))
        saw_start_bit |= _bit(dut.core_line) == 0

    assert saw_busy
    assert saw_start_bit
