# top = tb_sync2

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def sync2_adds_two_clock_latency(dut):
    start_clock(dut.clk)

    dut.input_signal.value = 0
    await tick(dut.clk, 3)
    assert int(dut.output_signal.value) == 0

    dut.input_signal.value = 1
    await tick(dut.clk, 1)
    assert int(dut.output_signal.value) == 0
    await tick(dut.clk, 1)
    assert int(dut.output_signal.value) == 1

    dut.input_signal.value = 0
    await tick(dut.clk, 1)
    assert int(dut.output_signal.value) == 1
    await tick(dut.clk, 1)
    assert int(dut.output_signal.value) == 0
