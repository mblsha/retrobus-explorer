import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from cocotb_helpers import start_clock


@cocotb.test()
async def enabled_byte_order_stalls_empty_and_invalid_words(dut):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.word.value = 0
    dut.be.value = 0
    dut.empty.value = 1
    dut.consume.value = 0
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0

    # A FIFO model supplies a new head only after the cursor pops this word.
    for word, be, expected in (
        (0x2211, 3, [0x11, 0x22]),
        (0x9933, 1, [0x33]),
        (0x4499, 2, [0x44]),
        (0xBEEF, 0, []),
        (0x8060, 3, [0x60, 0x80]),
    ):
        dut.word.value = word
        dut.be.value = be
        dut.empty.value = 0
        dut.consume.value = 0
        await Timer(1, units="ns")
        assert int(dut.packed_word.value) == word | (be << 16)
        assert int(dut.unpacked_word.value) == word
        assert int(dut.unpacked_be.value) == be
        if not expected:
            assert int(dut.pop_word.value) == 1
            await RisingEdge(dut.clk)
            await FallingEdge(dut.clk)
            assert int(dut.high.value) == 0
            continue
        for index, byte in enumerate(expected):
            # Merely presenting or holding a read must not advance the FIFO.
            for _ in range(3):
                await Timer(1, units="ns")
                assert int(dut.data.value) == byte
                assert int(dut.pop_word.value) == 0
                await RisingEdge(dut.clk)
                await FallingEdge(dut.clk)
            dut.consume.value = 1
            await Timer(1, units="ns")
            assert int(dut.data.value) == byte
            assert int(dut.pop_word.value) == (index == len(expected) - 1)
            await RisingEdge(dut.clk)
            await FallingEdge(dut.clk)
            dut.consume.value = 0
        assert int(dut.high.value) == 0

    dut.empty.value = 1
    dut.consume.value = 1
    await Timer(1, units="ns")
    assert int(dut.data.value) == int(dut.pop_word.value) == 0
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    assert int(dut.high.value) == 0

    # Reset a partially consumed word back to its first enabled byte.
    dut.empty.value = 0
    dut.word.value = 0xABCD
    dut.be.value = 3
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.consume.value = 0
    assert int(dut.high.value) == 1
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.rst.value = 0
    await Timer(1, units="ns")
    assert int(dut.data.value) == 0xCD
