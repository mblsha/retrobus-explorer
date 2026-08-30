# top = tb_wait_hold

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def hold_wait_pulses_for_configured_window(dut):
    start_clock(dut.clk)

    dut.rst.value = 1
    dut.mreq_fall.value = 0
    dut.iorq_fall.value = 0
    await tick(dut.clk, 2)
    assert int(dut.hold_wait.value) == 0

    dut.rst.value = 0
    await tick(dut.clk, 1)
    assert int(dut.hold_wait.value) == 0

    dut.mreq_fall.value = 1
    await tick(dut.clk, 1)
    assert int(dut.hold_wait.value) == 1
    dut.mreq_fall.value = 0

    states = []
    for _ in range(4):
        await tick(dut.clk, 1)
        states.append(int(dut.hold_wait.value))
    assert states == [1, 1, 0, 0]

    dut.iorq_fall.value = 1
    await tick(dut.clk, 1)
    assert int(dut.hold_wait.value) == 1
