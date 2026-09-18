import cocotb
import binascii
from cocotb.clock import Clock
from cocotb.triggers import Timer


async def pulse(dut, name):
    getattr(dut, name).value = 1
    await Timer(10, units="ns")
    getattr(dut, name).value = 0
    await Timer(10, units="ns")


async def snapshot(dut):
    words = []
    for index in range(64):
        dut.word_index.value = index
        await Timer(20, units="ns")
        words.append(int(dut.word.value))
    return words


@cocotb.test()
async def records_clock_commands_and_backend_activity(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.armed.value = 0
    dut.initialized.value = 1
    dut.clock_tick.value = 0
    dut.command_frame.value = 0
    dut.command_valid.value = 0
    dut.command_index.value = 0
    dut.command_argument.value = 0
    dut.response.value = 0
    dut.response_complete.value = 0
    dut.protocol_status.value = 0
    dut.response_payload.value = 0
    dut.data_release.value = 0
    dut.h700_falling_phase.value = 0
    dut.h700_early_command.value = 0
    dut.capture_lba.value = 0
    dut.cmd_pin.value = 1
    dut.data_pins.value = 15
    dut.pin_response.value = 0
    dut.pin_response_mismatch.value = 0
    dut.pin_data.value = 0
    dut.pin_data_mismatch.value = 0
    dut.read_request.value = 0
    dut.read_lba.value = 0
    dut.write_busy.value = 0
    dut.word_index.value = 0
    await Timer(40, units="ns")
    dut.rst.value = 0
    dut.armed.value = 1

    for _ in range(100):
        await pulse(dut, "clock_tick")
    dut.command_index.value = 18
    dut.command_argument.value = 0x200
    await pulse(dut, "command_valid")
    for lba in range(0x200, 0x203):
        dut.read_lba.value = lba
        await pulse(dut, "read_request")
    dut.command_index.value = 12
    dut.command_argument.value = 0
    await pulse(dut, "command_valid")
    for index in range(1, 9):
        dut.command_index.value = index
        dut.command_argument.value = 0x100 + index
        dut.command_valid.value = 1
        dut.command_frame.value = 1 if index == 1 else 0
        await Timer(10, units="ns")
        dut.command_valid.value = 0
        dut.command_frame.value = 0
        await Timer(10, units="ns")
    await pulse(dut, "response")
    await pulse(dut, "response_complete")
    dut.protocol_status.value = 0xE2879425
    dut.pin_response.value = 0x90ABCDEF
    dut.pin_response_mismatch.value = 0x00AA0302
    dut.pin_data.value = 0x05123456
    dut.pin_data_mismatch.value = 0x002A0003
    await pulse(dut, "command_frame")
    dut.read_lba.value = 33
    dut.read_request.value = 1
    await Timer(20, units="ns")
    dut.read_request.value = 0
    dut.write_busy.value = 1
    await Timer(20, units="ns")
    dut.write_busy.value = 0
    await Timer(30, units="ns")

    words = await snapshot(dut)
    assert words[0] == 0x31544453
    assert words[1] & 3 == 3
    assert words[2] == 100
    assert words[3:6] == [2, 10, 1]
    assert words[6] == 8
    assert words[7] == 0x108
    assert words[8:11] == [4, 33, 1]
    assert words[11:16] == [1, 0x001461C8, 1, 0xE2879425, 0x90ABCDEF]
    assert words[16] == 0x05123456
    assert words[17] == 0x002A0003
    assert words[18] == 0x000420C4
    assert words[19:27] == list(range(0x101, 0x109))
    assert words[27:31] == [0, 0, 0, (0x200 << 12) | 3]
    assert words[31] == 0x00AA0302
    assert words[32] == 0x32435453


@cocotb.test()
async def independently_captures_mmc_negotiation_r2_and_first_block(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for name, value in {
        "rst": 1,
        "armed": 0,
        "initialized": 1,
        "clock_tick": 0,
        "command_frame": 0,
        "command_valid": 0,
        "command_index": 0,
        "command_argument": 0,
        "response": 0,
        "response_complete": 0,
        "protocol_status": 1 << 12,
        "response_payload": 0,
        "data_release": 0,
        "h700_falling_phase": 1,
        "h700_early_command": 1,
        "capture_lba": 96,
        "cmd_pin": 1,
        "data_pins": 15,
        "pin_response": 0,
        "pin_response_mismatch": 0,
        "pin_data": 0,
        "pin_data_mismatch": 0,
        "read_request": 0,
        "read_lba": 0,
        "write_busy": 0,
        "word_index": 0,
    }.items():
        getattr(dut, name).value = value
    await Timer(40, units="ns")
    dut.rst.value = 0
    dut.armed.value = 1
    await Timer(20, units="ns")

    # Unsupported four-bit switch followed by the status U-Boot actually
    # inspects. The observer records both response payloads.
    dut.command_index.value = 6
    dut.command_argument.value = 0x03B70100
    dut.response_payload.value = 1 << 22
    await pulse(dut, "command_valid")
    dut.command_index.value = 13
    dut.command_argument.value = 0x10000
    dut.response_payload.value = (1 << 8) | (4 << 9) | (1 << 7)
    await pulse(dut, "command_valid")

    # Complete raw-pin R2 capture. The first low is found independently after
    # CMD9; the remaining 135 bits are then sampled from CMD.
    expected_r2 = bytes.fromhex("3fd0260008135913ffffffffe79240002f")
    dut.command_index.value = 9
    dut.command_argument.value = 0x10000
    await pulse(dut, "command_valid")
    r2_bits = [byte >> shift & 1 for byte in expected_r2 for shift in range(7, -1, -1)]
    for bit in r2_bits:
        dut.cmd_pin.value = bit
        await pulse(dut, "clock_tick")
    dut.cmd_pin.value = 1

    # Arm on a backend read of the chosen sector, record the R1 completion, then
    # present a complete one-bit block on raw DAT0. Only its first 32 bytes are
    # retained, but CRC is calculated across the complete observed payload.
    # Arming on the backend LBA rather than an MMC CMD18 is what lets these
    # timestamps measure the SD boot path, where CMD18 never carries mmc_mode.
    dut.command_index.value = 18
    dut.command_argument.value = 16
    dut.response_payload.value = (1 << 8) | (4 << 9)
    await pulse(dut, "command_valid")
    dut.read_lba.value = 96
    await pulse(dut, "read_request")
    await pulse(dut, "response_complete")
    payload = bytes(range(32)) + bytes(512 - 32)
    crc = binascii.crc_hqx(payload, 0)
    dut.pin_data.value = 1 << 25
    dut.data_pins.value = 14
    await pulse(dut, "clock_tick")
    for byte in payload:
        for shift in range(7, -1, -1):
            dut.data_pins.value = 14 | (byte >> shift & 1)
            await pulse(dut, "clock_tick")
    for shift in range(15, -1, -1):
        dut.data_pins.value = 14 | (crc >> shift & 1)
        await pulse(dut, "clock_tick")
    dut.data_pins.value = 15
    await pulse(dut, "clock_tick")
    dut.pin_data.value = 0
    await pulse(dut, "data_release")
    dut.command_index.value = 12
    dut.command_argument.value = 0
    await pulse(dut, "command_valid")

    words = await snapshot(dut)
    assert words[33] & 0xFFFF == 0x0101
    assert words[33] & (1 << 16)
    assert words[33] & (1 << 17)
    assert words[33] & (1 << 18)
    assert words[34:37] == [0x03B70100, 1 << 22, (1 << 8) | (4 << 9) | (1 << 7)]
    assert words[37] == (3 << 8) | 136
    captured_r2 = bytes([words[38]]) + b"".join(
        word.to_bytes(4, "big") for word in words[39:43]
    )
    assert captured_r2 == expected_r2
    assert words[43] & 7 == 5
    assert words[43] >> 8 & 0x1FFF == 4096
    assert words[43] & (1 << 3)
    assert words[43] & (1 << 4)
    assert words[44] == 96, "the capture records the sector that armed it"
    assert words[45] == crc | crc << 16
    assert b"".join(word.to_bytes(4, "big") for word in words[48:56]) == payload[:32]
    assert words[47] == 4113
    assert words[56] < words[57] < words[58] < words[59]
    assert words[60] > words[59]


@cocotb.test()
async def independently_decodes_a_four_bit_block(dut):
    """The RG35XX boot runs SD at four bits, so a one-lane decoder measured
    nothing there. Each lane carries its own CRC16 over its own bits, and lane
    zero is the one followed through both the payload and the CRC window."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for name, value in {
        "rst": 1,
        "armed": 0,
        "initialized": 1,
        "clock_tick": 0,
        "command_frame": 0,
        "command_valid": 0,
        "command_index": 0,
        "command_argument": 0,
        "response": 0,
        "response_complete": 0,
        # wide_bus is bit 30; mmc_mode deliberately left clear, as on the SD
        # boot path where the old arming condition never fired.
        "protocol_status": 1 << 30,
        "response_payload": 0,
        "data_release": 0,
        "h700_falling_phase": 0,
        "h700_early_command": 0,
        "capture_lba": 32985,
        "cmd_pin": 1,
        "data_pins": 15,
        "pin_response": 0,
        "pin_response_mismatch": 0,
        "pin_data": 0,
        "pin_data_mismatch": 0,
        "read_request": 0,
        "read_lba": 0,
        "write_busy": 0,
        "word_index": 0,
    }.items():
        getattr(dut, name).value = value
    await Timer(40, units="ns")
    dut.rst.value = 0
    dut.armed.value = 1

    # A backend read of another sector must not arm the capture.
    dut.read_lba.value = 32984
    await pulse(dut, "read_request")
    dut.read_lba.value = 32985
    await pulse(dut, "read_request")

    payload = bytes((index * 7 + 3) & 0xFF for index in range(512))
    lane0 = 0
    for byte in payload:
        for bit in ((byte >> 4) & 1, byte & 1):
            lane0 = (lane0 << 1) | bit
    crc = binascii.crc_hqx(lane0.to_bytes(128, "big"), 0)

    dut.data_pins.value = 0          # start bit on every lane
    await pulse(dut, "clock_tick")
    for byte in payload:
        for nibble in ((byte >> 4) & 0xF, byte & 0xF):
            dut.data_pins.value = nibble
            await pulse(dut, "clock_tick")
    for index in range(16):
        dut.data_pins.value = ((crc >> (15 - index)) & 1) * 15
        await pulse(dut, "clock_tick")
    dut.data_pins.value = 15         # end bit
    await pulse(dut, "clock_tick")
    await pulse(dut, "clock_tick")

    words = await snapshot(dut)
    assert words[43] & 7 == 5, "the four-bit block did not complete"
    assert words[43] >> 8 & 0x1FFF == 1024, "payload was not counted in nibbles"
    assert words[43] & (1 << 3), "end bit was not observed"
    assert words[44] == 32985, "the capture recorded the wrong sector"
    assert words[45] == crc | crc << 16, "lane-zero CRC mismatch"
    captured = b"".join(word.to_bytes(4, "big") for word in words[48:56])
    assert captured == payload[:32]
