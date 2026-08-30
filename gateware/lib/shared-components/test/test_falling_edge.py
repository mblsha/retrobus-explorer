# top = tb_falling_edge

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


@cocotb.test()
async def falling_edge_pulses_between_transition_and_next_clock_edge(dut):
    dut.signal_in.value = 1
    start_clock(dut.clk)

    await tick(dut.clk, 2)
    assert int(dut.edge_pulse.value) == 0

    await FallingEdge(dut.clk)
    dut.signal_in.value = 0
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 1

    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0

    await tick(dut.clk, 1)
    await tick(dut.clk, 1)
    assert int(dut.edge_pulse.value) == 0


@cocotb.test()
async def falling_edge_handles_startup_opposite_edge_and_bounce(dut):
    dut.signal_in.value = 0
    start_clock(dut.clk)

    # Startup while already low should not generate a pulse.
    await tick(dut.clk, 1)
    assert int(dut.edge_pulse.value) == 0

    # Rising transitions must never create a falling pulse.
    await FallingEdge(dut.clk)
    dut.signal_in.value = 1
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0

    # Bounce high->low->high within one cycle: pulse rises then drops before clock edge.
    await tick(dut.clk, 1)
    await FallingEdge(dut.clk)
    dut.signal_in.value = 0
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 1
    await Timer(2, units="ns")
    dut.signal_in.value = 1
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0

    # A later high->low transition should produce a new pulse again.
    await FallingEdge(dut.clk)
    dut.signal_in.value = 0
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    assert int(dut.edge_pulse.value) == 0
