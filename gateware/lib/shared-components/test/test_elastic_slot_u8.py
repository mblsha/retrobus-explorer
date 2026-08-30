# top = tb_elastic_buffer_u8

import cocotb
from cocotb.triggers import Timer
from cocotb_helpers import start_clock
from cocotb_helpers import tick


def _assert_outputs(
    dut,
    *,
    pending_valid,
    pending_data,
    sink_wput,
    sink_data,
    accepted,
    dropped,
):
    assert int(dut.pending_valid.value) == pending_valid
    assert int(dut.pending_data.value) == pending_data
    assert int(dut.sink_wput.value) == sink_wput
    assert int(dut.sink_data.value) == sink_data
    assert int(dut.accepted.value) == accepted
    assert int(dut.dropped.value) == dropped


@cocotb.test()
async def elastic_slot_preserves_dequeue_refill_and_drop_semantics(dut):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.capture_valid.value = 0
    dut.capture_data.value = 0
    dut.sink_full.value = 1
    await tick(dut.clk)
    _assert_outputs(
        dut,
        pending_valid=0,
        pending_data=0,
        sink_wput=0,
        sink_data=0,
        accepted=0,
        dropped=0,
    )

    dut.rst.value = 0

    # An empty slot accepts a sample even while its downstream sink is full.
    dut.capture_valid.value = 1
    dut.capture_data.value = 0x11
    await Timer(1, units="ps")
    _assert_outputs(
        dut,
        pending_valid=0,
        pending_data=0,
        sink_wput=0,
        sink_data=0,
        accepted=1,
        dropped=0,
    )
    await tick(dut.clk)

    # Once occupied and blocked, a new sample is dropped and the old one is retained.
    dut.capture_data.value = 0x22
    await Timer(1, units="ps")
    _assert_outputs(
        dut,
        pending_valid=1,
        pending_data=0x11,
        sink_wput=0,
        sink_data=0x11,
        accepted=0,
        dropped=1,
    )
    await tick(dut.clk)
    assert int(dut.pending_data.value) == 0x11

    # When the sink becomes ready, the old sample is emitted and the new one
    # replaces it on the same edge, preserving one word per cycle throughput.
    dut.sink_full.value = 0
    dut.capture_data.value = 0x33
    await Timer(1, units="ps")
    _assert_outputs(
        dut,
        pending_valid=1,
        pending_data=0x11,
        sink_wput=1,
        sink_data=0x11,
        accepted=1,
        dropped=0,
    )
    await tick(dut.clk)
    _assert_outputs(
        dut,
        pending_valid=1,
        pending_data=0x33,
        sink_wput=1,
        sink_data=0x33,
        accepted=1,
        dropped=0,
    )

    # A dequeue without a replacement empties the slot.
    dut.capture_valid.value = 0
    await tick(dut.clk)
    _assert_outputs(
        dut,
        pending_valid=0,
        pending_data=0x33,
        sink_wput=0,
        sink_data=0x33,
        accepted=0,
        dropped=0,
    )


@cocotb.test()
async def elastic_slot_streams_continuously_when_sink_is_ready(dut):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.capture_valid.value = 0
    dut.capture_data.value = 0
    dut.sink_full.value = 0
    await tick(dut.clk)
    dut.rst.value = 0

    for value in (0x40, 0x41, 0x42, 0x43):
        dut.capture_valid.value = 1
        dut.capture_data.value = value
        await tick(dut.clk)
        assert int(dut.pending_valid.value) == 1
        assert int(dut.pending_data.value) == value
        assert int(dut.sink_wput.value) == 1
        assert int(dut.accepted.value) == 1
        assert int(dut.dropped.value) == 0

    dut.capture_valid.value = 0
    await tick(dut.clk)
    assert int(dut.pending_valid.value) == 0
    assert int(dut.sink_wput.value) == 0
