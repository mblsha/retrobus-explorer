"""Native command, data CRC and multi-block write protocol integration."""

import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from test_sd import setup
from test_write_rx import crc_bit


async def send_packet(
    h, wide, seed, corrupt=False, wait_complete=True, expect_response=True
):
    d = h.d
    data = bytes((i * 37 + seed) & 255 for i in range(512))
    d.dat_in.value = 0 if wide else 14
    assert not (await h.cycle())[2]
    crcs = [0] * (4 if wide else 1)
    for byte in data:
        for shift in range(4, -1, -4) if wide else range(7, -1, -1):
            val = (byte >> shift) & (15 if wide else 1)
            for lane in range(len(crcs)):
                crcs[lane] = crc_bit(crcs[lane], (val >> lane) & 1)
            d.dat_in.value = val if wide else val | 14
            assert not (await h.cycle())[2], "DAT contention during host packet"
    for shift in range(15, -1, -1):
        val = sum(((crc >> shift) & 1) << lane for lane, crc in enumerate(crcs))
        if corrupt and shift == 5:
            val ^= 1
        d.dat_in.value = val if wide else val | 14
        assert not (await h.cycle())[2]
    d.dat_in.value = 15
    await h.cycle()
    if not expect_response:
        for _ in range(100):
            assert not (await h.cycle())[2], "unexpected response beyond card capacity"
        return data
    token = []
    # Keep a 100 us commit allowance as the SD clock changes; 100 clocks
    # at 10 MHz would expire before the ~14 us sector commit can finish.
    for _ in range(max(100, int(100_000 // (2 * h.half_ns)))):
        _, _, oe, val = await h.cycle()
        if oe:
            assert oe == 1
            token.append(val & 1)
        if len(token) >= 5 and not oe:
            break
        if len(token) == 5 and not wait_complete:
            break
    else:
        assert False, "CRC/busy response did not finish"
    assert token[:5] == ([0, 1, 0, 1, 1] if corrupt else [0, 0, 1, 0, 1])
    assert token[-1] == 1
    return data


@cocotb.test()
async def single_multi_crc_range_and_stop(d):
    h = await setup(d)
    d.writable.value = 1
    await h.init(writable=True)
    memory = {}
    allow = [True]

    async def native():
        rng = random.Random(310)
        address = data = None
        while True:
            await FallingEdge(d.clk)
            cr = allow[0] and rng.randrange(4) != 0
            wr = allow[0] and rng.randrange(3) != 0
            d.write_cmd_ready.value = cr
            d.write_data_ready.value = wr
            await Timer(1, units="ps")
            if cr and int(d.write_cmd_valid.value):
                assert address is None
                address = int(d.write_cmd_address.value)
            if wr and int(d.write_data_valid.value):
                assert data is None and int(d.write_mask.value) == 65535
                data = int(d.write_data.value)
            await RisingEdge(d.clk)
            if address is not None and data is not None:
                memory[address] = data.to_bytes(16, "little")
                address = data = None

    task = cocotb.start_soon(native())

    def sector(lba):
        return b"".join(memory[lba * 32 + i] for i in range(32))

    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        response = await h.command(24, 127 * 512)
        assert int.from_bytes(response[1:5], "big") >> 16 == 0
        expected = await send_packet(h, wide, 21 + wide)
        assert sector(127) == expected
        status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
        assert status & 0x1F00 == 0x900

        await h.command(25, 128 * 512)
        for lba in (128, 129, 130, 131):
            expected = await send_packet(h, wide, lba)
            assert sector(lba) == expected
        await h.command(12)
        status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
        assert status & 0x1F00 == 0x900

        before = dict(memory)
        await h.command(24, 127 * 512)
        await send_packet(h, wide, 77, corrupt=True)
        assert memory == before
        status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
        assert status & (1 << 23)
        status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
        assert not status & (1 << 23)

        # Stop a partial next block without committing any of its bytes.
        await h.command(25, 200 * 512)
        d.dat_in.value = 0 if wide else 14
        await h.cycle()
        d.dat_in.value = 5 if wide else 15
        await h.cycle()
        await h.command(12)
        d.dat_in.value = 15
        assert memory == before

    for arg, error in ((1, 1 << 30), (268435456, 1 << 31)):
        status = int.from_bytes((await h.command(24, arg))[1:5], "big")
        assert status & error
        assert not int(d.write_cmd_valid.value)

    await h.command(25, 524287 * 512)
    expected = await send_packet(h, True, 123)
    assert sector(524287) == expected
    assert max(memory) == 16777215
    before = dict(memory)
    await send_packet(h, True, 124, expect_response=False)
    assert memory == before, "multiblock write wrapped beyond the last sector"
    assert not int(d.write_busy.value)
    task.kill()
