"""Native command, data CRC and multi-block write protocol integration."""

import random

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from sd_support import setup


from sd_support import send_packet


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
