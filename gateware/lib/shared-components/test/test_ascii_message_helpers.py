# top = tb_ascii_message_helpers

import itertools

import cocotb
from cocotb.triggers import Timer


async def _settle():
    await Timer(1, units="ns")


@cocotb.test()
async def formatting_helpers_match_existing_application_conventions(dut):
    dut.text_idx.value = 0
    dut.highest_valid.value = 0
    dut.highest_byte.value = 0
    dut.high_valid.value = 0
    dut.high_byte.value = 0
    dut.low_valid.value = 0
    dut.low_byte.value = 0

    for nibble, expected in enumerate(b"0123456789ABCDEF"):
        dut.nibble.value = nibble
        await _settle()
        assert int(dut.hex_char_out.value) == expected

    for value in range(256):
        dut.value.value = value
        await _settle()
        expected = f"{value:02X}".encode("ascii")
        assert int(dut.byte_hex_high.value) == expected[0]
        assert int(dut.byte_hex_low.value) == expected[1]

    for digit in range(10):
        dut.digit.value = digit
        await _settle()
        assert int(dut.digit_char.value) == ord("0") + digit

    for flag in (0, 1):
        dut.flag.value = flag
        await _settle()
        assert int(dut.bool_char.value) == ord("1" if flag else "0")


@cocotb.test()
async def indexed_text_is_valid_only_inside_its_bounds(dut):
    dut.nibble.value = 0
    dut.value.value = 0
    dut.digit.value = 0
    dut.flag.value = 0
    dut.highest_valid.value = 0
    dut.highest_byte.value = 0
    dut.high_valid.value = 0
    dut.high_byte.value = 0
    dut.low_valid.value = 0
    dut.low_byte.value = 0

    for idx in range(8):
        dut.text_idx.value = idx
        await _settle()
        if idx < 3:
            assert int(dut.text_valid.value) == 1
            assert int(dut.text_byte.value) == b"ABC"[idx]
        else:
            assert int(dut.text_valid.value) == 0
            assert int(dut.text_byte.value) == 0


@cocotb.test()
async def tx_request_arbiter_uses_strict_highest_to_low_priority(dut):
    dut.nibble.value = 0
    dut.value.value = 0
    dut.digit.value = 0
    dut.flag.value = 0
    dut.text_idx.value = 0
    dut.highest_byte.value = 0xA1
    dut.high_byte.value = 0xB2
    dut.low_byte.value = 0xC3

    for highest_valid, high_valid, low_valid in itertools.product((0, 1), repeat=3):
        dut.highest_valid.value = highest_valid
        dut.high_valid.value = high_valid
        dut.low_valid.value = low_valid
        await _settle()

        expected_valid = highest_valid or high_valid or low_valid
        if highest_valid:
            expected_byte = 0xA1
        elif high_valid:
            expected_byte = 0xB2
        else:
            expected_byte = 0xC3

        assert int(dut.arbiter_valid.value) == int(expected_valid)
        assert int(dut.arbiter_byte.value) == expected_byte
