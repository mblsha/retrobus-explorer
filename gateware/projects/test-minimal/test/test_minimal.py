# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def reset_and_early_cycles_are_stable(dut):
    start_clock(dut.clk)

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
