import random

import cocotb
from cocotb_helpers import start_clock, tick
from microsd_probe import decode, request


async def init(dut, top=0):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.pmod.value = 255
    dut.top_header.value = top
    dut.rx_valid.value = 0
    dut.rx_byte.value = 0
    dut.tx_ready.value = 0
    await tick(dut.clk, 5)
    dut.rst.value = 0
    await tick(dut.clk, 12)


async def send(dut, packet):
    for byte in packet:
        dut.rx_valid.value = 1
        dut.rx_byte.value = byte
        await tick(dut.clk)
        dut.rx_valid.value = 0
        await tick(dut.clk)


async def receive(dut, stalls=False):
    rng = random.Random(312)
    packet = bytearray()
    for _ in range(500):
        if len(packet) == 64:
            break
        valid = int(dut.tx_valid.value)
        byte = int(dut.tx_byte.value)
        ready = int(not stalls or rng.randrange(3) != 0)
        dut.tx_ready.value = ready
        if valid and ready:
            packet.append(byte)
        await tick(dut.clk)
        if valid and not ready:
            assert int(dut.tx_valid.value)
            assert int(dut.tx_byte.value) == byte
    dut.tx_ready.value = 0
    assert len(packet) == 64
    return decode(bytes(packet)), bytes(packet)


async def query(dut, op=1, seq=7, stalls=False):
    await send(dut, request(op, seq))
    result, packet = await receive(dut, stalls)
    assert result["sequence"] == seq and result["opcode"] == op
    return result, packet


def sd_command(index, argument):
    body = bytes([0x40 | index]) + argument.to_bytes(4, "big")
    crc = 0
    for byte in body:
        for shift in range(7, -1, -1):
            crc = ((crc << 1) ^ (9 if ((crc >> 6) ^ (byte >> shift)) & 1 else 0)) & 127
    return body + bytes([(crc << 1) | 1])


async def emit_command(dut, packet, top):
    clk_mask = 1 << (6 if top else 2)
    cmd_mask = 1 << (2 if top else 6)
    pins = 255 & ~clk_mask
    for byte in packet:
        for shift in range(7, -1, -1):
            pins = (pins | cmd_mask) if byte & (1 << shift) else (pins & ~cmd_mask)
            dut.pmod.value = pins
            await tick(dut.clk, 8)
            dut.pmod.value = pins | clk_mask
            await tick(dut.clk, 8)
    dut.pmod.value = 255
    await tick(dut.clk, 12)


@cocotb.test()
async def isolated_lane_transitions_snapshot_crc_and_stalls(dut):
    await init(dut)
    await query(dut, op=2)
    expected = []
    for lane in range(8):
        expected.append(2 * (lane + 1))
        for _ in range(lane + 1):
            dut.pmod.value = 255 ^ (1 << lane)
            await tick(dut.clk, 6)
            dut.pmod.value = 255
            await tick(dut.clk, 6)
    result, _ = await query(dut, stalls=True)
    assert result["raw_transitions"] == expected
    assert result["raw_levels"] == 255
    assert all(x["seen_high"] and x["seen_low"] for x in result["signals"].values())
    assert not any(x["pinout_verified"] for x in result["signals"].values())
    # Start a snapshot and change input before serializing: payload must be atomic.
    await send(dut, request(1, 88))
    dut.pmod.value = 0
    await tick(dut.clk, 20)
    frozen, _ = await receive(dut, stalls=True)
    assert frozen["raw_levels"] == 255 and frozen["raw_transitions"] == expected
    now, _ = await query(dut)
    assert now["raw_levels"] == 0
    assert now["raw_transitions"] == [n + 1 for n in expected]


@cocotb.test()
async def corrupted_and_truncated_requests_have_no_effect(dut):
    await init(dut)
    bad = bytearray(request(2, 33))
    bad[4] ^= 1
    await send(dut, bad)
    assert not int(dut.tx_valid.value)
    await send(dut, request(1, 1)[:3])
    await tick(dut.clk, 100_010)
    assert not int(dut.tx_valid.value)
    result, _ = await query(dut, seq=99)
    assert result["cycles_mod_2_32"] > 100_000
    await query(dut, op=2)
    result, _ = await query(dut)
    assert result["raw_transitions"] == [0] * 8
    assert result["valid_sd_commands"] == 0


@cocotb.test()
async def native_cmd0_cmd8_crc_and_both_header_profiles(dut):
    await init(dut)
    assert sd_command(0, 0).hex() == "400000000095"
    assert sd_command(8, 0x1AA).hex() == "48000001aa87"
    for top in (0, 1, 2):
        dut.top_header.value = top
        await query(dut, op=2)
        for index, arg in [(0, 0), (8, 0x1AA), (55, 0), (41, 0x00FF8000)]:
            await emit_command(dut, sd_command(index, arg), top)
        corrupt = bytearray(sd_command(17, 0))
        corrupt[5] ^= 2
        await emit_command(dut, corrupt, top)
        result, _ = await query(dut)
        assert result["valid_sd_commands"] == 4
        assert result["last_command_hex"] == sd_command(41, 0x00FF8000).hex()
        assert (
            result["profile"]
            == ("bottom-header", "top-header-r180", "bottom-header-row-swap")[top]
        )
        assert result["signals"]["CLK"]["transitions"] > 0


@cocotb.test()
async def reset_cancels_partial_reply_and_unknown_opcode_is_rejected(dut):
    await init(dut)
    from microsd_probe import crc8

    body = bytes([1, 0xFF, 0x12])
    await send(dut, bytes([0xA5]) + body + bytes([crc8(body), 0x5A]))
    assert not int(dut.tx_valid.value)
    await send(dut, request(1, 3))
    assert int(dut.tx_valid.value)
    dut.rst.value = 1
    await tick(dut.clk, 4)
    assert not int(dut.tx_valid.value)
    dut.rst.value = 0
    await tick(dut.clk, 12)
    await query(dut)
