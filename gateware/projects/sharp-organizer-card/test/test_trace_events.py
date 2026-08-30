import cocotb
from cocotb.triggers import Timer


TRACE_TAGS = {
    "addr_word": ord("A"),
    "data_word": ord("D"),
    "misc_word": ord("M"),
    "overflow_word": ord("O"),
}


@cocotb.test()
async def trace_events_pack_exact_tagged_words(dut):
    for payload in (0x000000, 0x000001, 0xA5C3E7, 0xFFFFFF):
        dut.payload.value = payload
        await Timer(1, units="ns")

        for signal_name, tag in TRACE_TAGS.items():
            actual = int(getattr(dut, signal_name).value)
            expected = (tag << 24) | payload
            assert actual == expected, (
                f"{signal_name} packed 0x{actual:08X}; expected 0x{expected:08X}"
            )


@cocotb.test()
async def trace_event_requests_preserve_valid_semantics(dut):
    dut.payload.value = 0x5A3C81
    await Timer(1, units="ns")

    assert int(dut.none_valid.value) == 0
    assert int(dut.none_word.value) == ord("A") << 24
    assert int(dut.addr_valid.value) == 1
    assert int(dut.data_valid.value) == 1
    assert int(dut.misc_valid.value) == 1
    assert int(dut.overflow_valid.value) == 1
