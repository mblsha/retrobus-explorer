import cocotb
from cocotb_helpers import tick


from sd_support import setup


@cocotb.test()
async def enumerate_read_single_and_scr_in_one_and_four_bit_modes(d):
    h = await setup(d)
    await h.init()
    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        await h.command(55, 0x10000)
        await h.command(51)
        assert await h.data(8, wide) == bytes.fromhex("0105000000000000")
        response = await h.command(17, 512 * 127)
        assert not int.from_bytes(response[1:5], "big") & 0xFFF80000
        assert int(d.request_lba.value) == 127
        for _ in range(20):
            assert not (await h.cycle())[2]
        await h.supply()
        assert await h.data(wide=wide) == h.sector


@cocotb.test()
async def bad_crc_ranges_write_protection_and_cancelled_backend(d):
    h = await setup(d)
    await h.init()
    await h.command(17, 0, length=0, corrupt=True)
    for _ in range(12):
        assert not (await h.cycle())[0]
        assert not int(d.request_valid.value)
    for command, arg, error in [
        (17, 1, 1 << 30),
        (17, 8388608, 1 << 31),
        (24, 0, 1 << 26),
        (25, 0, 1 << 26),
        (16, 1024, 1 << 22),
    ]:
        result = await h.command(command, arg)
        assert int.from_bytes(result[1:5], "big") & error
        assert not int(d.request_valid.value)
    await h.command(18, 0)
    old = int(d.generation.value)
    await h.command(12)
    assert not int(d.request_valid.value)
    d.sector_generation.value = old
    d.sector_ready.value = 1
    for _ in range(20):
        assert not (await h.cycle())[2]
    d.sector_ready.value = 0
    await h.command(17, 1024)
    assert int(d.generation.value) != old
    await h.supply()
    assert await h.data() == h.sector
    d.armed.value = 0
    await tick(d.clk, 4)
    assert not int(d.cmd_oe.value) and not int(d.dat_oe.value)


@cocotb.test()
async def multiblock_progress_and_stop_during_data(d):
    h = await setup(d)
    await h.init()
    await h.command(55, 0x10000)
    await h.command(6, 2)
    await h.command(18, 126 * 512)
    for lba in (126, 127):
        assert int(d.request_lba.value) == lba
        await h.supply()
        assert await h.data(wide=True) == h.sector
        await h.cycle()
    assert int(d.request_lba.value) == 128
    await h.supply()
    # Let a third block begin, then interrupt it with native CMD12 on CMD.
    for _ in range(20):
        await h.cycle()
    assert int(d.dat_oe.value) == 15
    await h.command(12)
    assert not int(d.dat_oe.value) and not int(d.request_valid.value)
    await h.command(0, length=0)
    await h.init()


@cocotb.test()
async def sd_status_reports_current_bus_width(d):
    h = await setup(d)
    await h.init()
    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        await h.command(55, 0x10000)
        response = await h.command(13, 0)
        assert not int.from_bytes(response[1:5], "big") & (1 << 22)
        assert await h.data(64, wide) == bytes([0x80 if wide else 0]) + bytes(63)
        assert not int(d.request_valid.value)
        response = await h.command(13, 0x10000)
        assert not int.from_bytes(response[1:5], "big") & (1 << 22)
        for _ in range(10):
            assert not (await h.cycle())[2]
