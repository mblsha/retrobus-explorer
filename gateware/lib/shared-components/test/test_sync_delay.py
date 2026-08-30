# top = tb_sync_delay

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def sync_delay_generic_depths_match_expected_latency(dut):
    start_clock(dut.clk)

    dut.input_signal.value = 0
    await tick(dut.clk, 8)
    assert int(dut.output_stage2.value) == 0
    assert int(dut.output_stage4.value) == 0
    assert int(dut.output_stage6.value) == 0

    dut.input_signal.value = 1
    # Stage-2 output rises after 2 clocks.
    await tick(dut.clk, 1)
    assert int(dut.output_stage2.value) == 0
    assert int(dut.output_stage4.value) == 0
    assert int(dut.output_stage6.value) == 0
    await tick(dut.clk, 1)
    assert int(dut.output_stage2.value) == 1
    assert int(dut.output_stage4.value) == 0
    assert int(dut.output_stage6.value) == 0

    # Stage-4 output rises after 4 clocks.
    await tick(dut.clk, 1)
    assert int(dut.output_stage4.value) == 0
    assert int(dut.output_stage6.value) == 0
    await tick(dut.clk, 1)
    assert int(dut.output_stage4.value) == 1
    assert int(dut.output_stage6.value) == 0

    # Stage-6 output rises after 6 clocks.
    await tick(dut.clk, 1)
    assert int(dut.output_stage6.value) == 0
    await tick(dut.clk, 1)
    assert int(dut.output_stage6.value) == 1

    dut.input_signal.value = 0
    await tick(dut.clk, 1)
    assert int(dut.output_stage2.value) == 1
    await tick(dut.clk, 1)
    assert int(dut.output_stage2.value) == 0
    assert int(dut.output_stage4.value) == 1
    assert int(dut.output_stage6.value) == 1
    await tick(dut.clk, 2)
    assert int(dut.output_stage4.value) == 0
    assert int(dut.output_stage6.value) == 1
    await tick(dut.clk, 2)
    assert int(dut.output_stage6.value) == 0
