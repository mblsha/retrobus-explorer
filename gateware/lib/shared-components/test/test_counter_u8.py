# top = tb_counter_u8

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def counter_u8_counts_and_resets(dut):
    start_clock(dut.clk)

    dut.rst.value = 1
    await tick(dut.clk, 2)
    assert int(dut.value_bits.value) == 0

    dut.rst.value = 0
    for expected in range(1, 17):
        await tick(dut.clk, 1)
        assert int(dut.value_bits.value) == expected

    dut.rst.value = 1
    await tick(dut.clk, 1)
    assert int(dut.value_bits.value) == 0
