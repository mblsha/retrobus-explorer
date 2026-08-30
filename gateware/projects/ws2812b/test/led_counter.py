# top = led_counter

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


@cocotb.test()
async def resets_and_counts_with_configurable_max(dut):
    clk = dut.clk_i

    await cocotb.start(Clock(clk, period=10, units="ns").start())

    dut.max_i.value = 3
    dut.rst_i.value = 1
    await tick(clk, 3)
    assert dut.output__.value == 0

    dut.rst_i.value = 0
    await tick(clk, 1)
    assert dut.output__.value == 1

    await tick(clk, 4)
    assert dut.output__.value == 2

    await tick(clk, 4)
    assert dut.output__.value == 3
