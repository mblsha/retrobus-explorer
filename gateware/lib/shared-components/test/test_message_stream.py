# top = tb_message_stream

import cocotb
from cocotb.triggers import Timer
from cocotb_helpers import start_clock
from cocotb_helpers import tick


def _assert_state(dut, *, current, index, pending, tx_valid, tx_byte, msg_none):
    assert int(dut.current_msg.value) == current
    assert int(dut.current_idx.value) == index
    assert int(dut.pending_msg.value) == pending
    assert int(dut.tx_valid.value) == tx_valid
    assert int(dut.tx_byte.value) == tx_byte
    assert int(dut.msg_none.value) == msg_none


def _clear_scheduler_inputs(dut):
    dut.schedule_current.value = 0
    dut.schedule_current_is_none.value = 1
    dut.schedule_pending.value = 0
    dut.schedule_pending_is_none.value = 1
    dut.schedule_incoming_valid.value = 0
    dut.schedule_incoming.value = 0
    dut.schedule_incoming_is_none.value = 1


async def _assert_schedule(
    dut,
    *,
    current,
    current_is_none,
    pending,
    pending_is_none,
    incoming_valid,
    incoming,
    incoming_is_none,
    expected_current,
    expected_current_is_none,
    expected_pending,
    expected_pending_is_none,
    expected_current_loaded,
):
    dut.schedule_current.value = current
    dut.schedule_current_is_none.value = current_is_none
    dut.schedule_pending.value = pending
    dut.schedule_pending_is_none.value = pending_is_none
    dut.schedule_incoming_valid.value = incoming_valid
    dut.schedule_incoming.value = incoming
    dut.schedule_incoming_is_none.value = incoming_is_none
    await Timer(1, units="ns")

    assert int(dut.scheduled_current.value) == expected_current
    assert int(dut.scheduled_current_is_none.value) == expected_current_is_none
    assert int(dut.scheduled_pending.value) == expected_pending
    assert int(dut.scheduled_pending_is_none.value) == expected_pending_is_none
    assert int(dut.scheduled_current_loaded.value) == expected_current_loaded


@cocotb.test()
async def pure_scheduler_promotes_current_and_keeps_only_latest_pending(dut):
    # An arrival fills an empty scheduler directly.
    await _assert_schedule(
        dut,
        current=0xA0,
        current_is_none=1,
        pending=0xB0,
        pending_is_none=1,
        incoming_valid=1,
        incoming=0x11,
        incoming_is_none=0,
        expected_current=0x11,
        expected_current_is_none=0,
        expected_pending=0xB0,
        expected_pending_is_none=1,
        expected_current_loaded=1,
    )

    # A pending item is promoted before the simultaneous arrival is queued.
    await _assert_schedule(
        dut,
        current=0,
        current_is_none=1,
        pending=0x22,
        pending_is_none=0,
        incoming_valid=1,
        incoming=0x33,
        incoming_is_none=0,
        expected_current=0x22,
        expected_current_is_none=0,
        expected_pending=0x33,
        expected_pending_is_none=0,
        expected_current_loaded=1,
    )

    # With both slots occupied, the incoming item replaces the pending item.
    await _assert_schedule(
        dut,
        current=0x44,
        current_is_none=0,
        pending=0x55,
        pending_is_none=0,
        incoming_valid=1,
        incoming=0x66,
        incoming_is_none=0,
        expected_current=0x44,
        expected_current_is_none=0,
        expected_pending=0x66,
        expected_pending_is_none=0,
        expected_current_loaded=0,
    )

    # Explicit none flags are authoritative: a valid sentinel arrival is ignored.
    await _assert_schedule(
        dut,
        current=0x77,
        current_is_none=0,
        pending=0x88,
        pending_is_none=1,
        incoming_valid=1,
        incoming=0x99,
        incoming_is_none=1,
        expected_current=0x77,
        expected_current_is_none=0,
        expected_pending=0x88,
        expected_pending_is_none=1,
        expected_current_loaded=0,
    )


@cocotb.test()
async def message_stream_stalls_and_drains_in_order(dut):
    start_clock(dut.clk)
    _clear_scheduler_inputs(dut)
    dut.rst.value = 1
    dut.block_tx.value = 0
    dut.enqueue_valid.value = 0
    dut.enqueue_msg.value = 0
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0,
        index=0,
        pending=0,
        tx_valid=0,
        tx_byte=0,
        msg_none=1,
    )

    # Enqueueing into an idle stream loads the current slot on the next edge.
    dut.rst.value = 0
    dut.enqueue_valid.value = 1
    dut.enqueue_msg.value = 0x10
    await tick(dut.clk)
    dut.enqueue_valid.value = 0
    _assert_state(
        dut,
        current=0x10,
        index=0,
        pending=0,
        tx_valid=1,
        tx_byte=0x10,
        msg_none=0,
    )

    # Backpressure suppresses valid and leaves both message and index unchanged.
    dut.block_tx.value = 1
    await tick(dut.clk, 3)
    _assert_state(
        dut,
        current=0x10,
        index=0,
        pending=0,
        tx_valid=0,
        tx_byte=0,
        msg_none=0,
    )

    # Each message renders as [msg, msg + 1].
    dut.block_tx.value = 0
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x10,
        index=1,
        pending=0,
        tx_valid=1,
        tx_byte=0x11,
        # msg_none describes the post-step state, so it rises on the cycle
        # that presents the final byte when no replacement is queued.
        msg_none=1,
    )
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0,
        index=0,
        pending=0,
        tx_valid=0,
        tx_byte=0,
        msg_none=1,
    )


@cocotb.test()
async def message_stream_keeps_one_current_and_latest_pending(dut):
    start_clock(dut.clk)
    _clear_scheduler_inputs(dut)
    dut.rst.value = 1
    dut.block_tx.value = 0
    dut.enqueue_valid.value = 0
    dut.enqueue_msg.value = 0
    await tick(dut.clk)
    dut.rst.value = 0

    # Load A and block it so pending-slot behavior can be observed directly.
    dut.block_tx.value = 1
    dut.enqueue_valid.value = 1
    dut.enqueue_msg.value = 0x20
    await tick(dut.clk)
    dut.enqueue_msg.value = 0x30
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x20,
        index=0,
        pending=0x30,
        tx_valid=0,
        tx_byte=0,
        msg_none=0,
    )

    # With both slots occupied, a newer arrival replaces the pending message.
    dut.enqueue_msg.value = 0x40
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x20,
        index=0,
        pending=0x40,
        tx_valid=0,
        tx_byte=0,
        msg_none=0,
    )

    # Send A's first byte without another arrival.
    dut.block_tx.value = 0
    dut.enqueue_valid.value = 0
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x20,
        index=1,
        pending=0x40,
        tx_valid=1,
        tx_byte=0x21,
        msg_none=0,
    )

    # On A's final byte, C is promoted and D is accepted into pending in the
    # same cycle. This is the critical current-drain + pending-refill case.
    dut.enqueue_valid.value = 1
    dut.enqueue_msg.value = 0x50
    await tick(dut.clk)
    dut.enqueue_valid.value = 0
    _assert_state(
        dut,
        current=0x40,
        index=0,
        pending=0x50,
        tx_valid=1,
        tx_byte=0x40,
        msg_none=0,
    )

    # Drain C; D must follow without an idle state between messages.
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x40,
        index=1,
        pending=0x50,
        tx_valid=1,
        tx_byte=0x41,
        msg_none=0,
    )
    await tick(dut.clk)
    _assert_state(
        dut,
        current=0x50,
        index=0,
        pending=0,
        tx_valid=1,
        tx_byte=0x50,
        msg_none=0,
    )


@cocotb.test()
async def enqueue_on_final_byte_replaces_an_empty_current_slot(dut):
    start_clock(dut.clk)
    _clear_scheduler_inputs(dut)
    dut.rst.value = 1
    dut.block_tx.value = 0
    dut.enqueue_valid.value = 0
    dut.enqueue_msg.value = 0
    await tick(dut.clk)
    dut.rst.value = 0

    dut.enqueue_valid.value = 1
    dut.enqueue_msg.value = 0x60
    await tick(dut.clk)
    dut.enqueue_valid.value = 0
    await tick(dut.clk)
    assert int(dut.current_idx.value) == 1

    dut.enqueue_valid.value = 1
    dut.enqueue_msg.value = 0x70
    await tick(dut.clk)
    dut.enqueue_valid.value = 0
    _assert_state(
        dut,
        current=0x70,
        index=0,
        pending=0,
        tx_valid=1,
        tx_byte=0x70,
        msg_none=0,
    )
