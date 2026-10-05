import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from cocotb_helpers import start_clock


@cocotb.test()
async def record_order_pop_boundary_backpressure_and_reset(dut):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.record.value = 0
    dut.empty.value = 1
    dut.sink_full.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0

    width = len(dut.record)
    halves = width // 16
    records = [
        sum((0xA000 + record * 0x100 + half) << (half * 16) for half in range(halves))
        for record in range(3)
    ]
    received = []
    head = 0
    for cycle in range(200):
        dut.record.value = records[head] if head < len(records) else 0
        dut.empty.value = head == len(records)
        # Stop at varied points, including between the final two halfwords.
        dut.sink_full.value = cycle % 7 in (0, 2, 3)
        await Timer(1, units="ns")
        valid = int(dut.valid.value)
        pop = int(dut.pop_record.value)
        if valid:
            assert not int(dut.sink_full.value)
            assert int(dut.be.value) == 3
            received.append(int(dut.data.value))
        else:
            assert int(dut.be.value) == 0
        if pop:
            assert valid
            # Pop on the low half of the last word, retain its high half.
            assert len(received) == (head + 1) * halves - 1
        await RisingEdge(dut.clk)
        await FallingEdge(dut.clk)
        if pop:
            head += 1
        if len(received) == len(records) * halves:
            break
    assert head == len(records)
    assert received == [0xA000 + record * 0x100 + half for record in range(3) for half in range(halves)]
    dut.empty.value = 1
    dut.sink_full.value = 0
    await Timer(1, units="ns")
    assert int(dut.valid.value) == int(dut.pop_record.value) == 0

    # A reset during a partly transmitted record restarts at its low half.
    dut.record.value = records[0]
    dut.empty.value = 0
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await Timer(1, units="ns")
    assert int(dut.valid.value) == 1
    assert int(dut.data.value) == 0xA000
