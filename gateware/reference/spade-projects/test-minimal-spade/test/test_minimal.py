# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


@cocotb.test()
async def reset_and_early_cycles_are_stable(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    await tick(dut.clk, 3)
    assert dut.led.value.integer == 0

    dut.rst_n.value = 1
    await tick(dut.clk, 64)
    # With bits [18:25], LED should still be zero in early cycles.
    assert dut.led.value.integer == 0

    dut.rst_n.value = 0
    await tick(dut.clk, 2)
    assert dut.led.value.integer == 0
