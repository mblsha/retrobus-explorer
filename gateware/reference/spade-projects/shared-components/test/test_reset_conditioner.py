# top = tb_reset_conditioner

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def _assert_outputs(dut, stage2: int, stage4: int):
    assert int(dut.output_stage2.value) == stage2
    assert int(dut.output_stage4.value) == stage4


@cocotb.test()
async def reset_conditioner_async_assert_and_sync_release(dut):
    dut.in_reset.value = 0
    start_clock(dut.clk)

    await tick(dut.clk, 4)
    _assert_outputs(dut, 0, 0)

    # Assert reset between edges; output should rise immediately.
    await FallingEdge(dut.clk)
    dut.in_reset.value = 1
    await Timer(1, units="ps")
    _assert_outputs(dut, 1, 1)

    # Hold reset through one clock edge so the delayed-release chain is loaded.
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    _assert_outputs(dut, 1, 1)

    # Deassert between edges; release remains synchronized.
    dut.in_reset.value = 0
    await Timer(1, units="ps")
    _assert_outputs(dut, 1, 1)

    await tick(dut.clk, 1)
    _assert_outputs(dut, 1, 1)

    await tick(dut.clk, 1)
    _assert_outputs(dut, 0, 1)

    await tick(dut.clk, 2)
    _assert_outputs(dut, 0, 0)


@cocotb.test()
async def reset_conditioner_reassertion_reloads_all_stages(dut):
    dut.in_reset.value = 1
    start_clock(dut.clk)

    await tick(dut.clk, 3)
    _assert_outputs(dut, 1, 1)

    dut.in_reset.value = 0
    await tick(dut.clk, 1)
    _assert_outputs(dut, 1, 1)
    await tick(dut.clk, 1)
    _assert_outputs(dut, 0, 1)

    # Reassert during release; both outputs should immediately return high.
    await FallingEdge(dut.clk)
    dut.in_reset.value = 1
    await Timer(1, units="ps")
    _assert_outputs(dut, 1, 1)

    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    _assert_outputs(dut, 1, 1)

    dut.in_reset.value = 0
    await tick(dut.clk, 1)
    _assert_outputs(dut, 1, 1)
    await tick(dut.clk, 1)
    _assert_outputs(dut, 0, 1)
    await tick(dut.clk, 2)
    _assert_outputs(dut, 0, 0)
