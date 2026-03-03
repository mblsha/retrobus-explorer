# top = tb_stream_counter

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def stream_counter_advances_only_on_advance_flag(dut):
    start_clock(dut.clk)

    dut.rst.value = 1
    dut.advance.value = 0
    await tick(dut.clk, 2)
    assert dut.value_bits.value.integer == 0

    dut.rst.value = 0
    expected = 0
    pattern = [0, 1, 0, 1, 1, 0, 0, 1]
    for value in pattern:
        dut.advance.value = value
        await tick(dut.clk, 1)
        if value:
            expected = (expected + 1) & 0xFF
        assert dut.value_bits.value.integer == expected
