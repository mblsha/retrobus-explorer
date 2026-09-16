import cocotb
from cocotb_helpers import tick


from sd_support import setup


@cocotb.test()
async def mmc_fallback_enumerates_and_reads(d):
    h = await setup(d)
    # Match the observed H700 fallback: the SD operation-condition response
    # has already moved the internal card to READY before MMC CMD1 arrives.
    await h.command(0, length=0)
    await h.command(8, 0x1AA)
    await h.command(55)
    await h.command(41, 0x00FF8000)
    await h.command(0, length=0)
    assert (await h.command(1, 0))[1:5] == bytes.fromhex("c0ff8080")

    assert (await h.command(1, 0x40300000))[1:5] == bytes.fromhex("c0ff8080")
    assert b"SPADE" in await h.command(2, length=136)
    status = await h.command(3, 0x10000)
    assert not int.from_bytes(status[1:5], "big") & (1 << 22)
    await h.command(9, 0x10000, length=136)
    await h.command(7, 0x10000)
    await h.command(8, 0)
    ext_csd = await h.data()
    assert ext_csd[192] == 8
    assert ext_csd[196] == 0
    assert int.from_bytes(ext_csd[212:216], "little") == 524288
    await h.command(6, 0x03AF0100)
    await h.command(17, 9)
    assert int(d.request_lba.value) == 9
    await h.supply()
    assert await h.data() == h.sector

    # The H700 then selects 256-byte legacy MMC blocks. Consecutive logical
    # blocks expose the two halves of one physical 512-byte DDR sector.
    await h.command(16, 256)
    await h.command(17, 18)
    assert int(d.request_lba.value) == 9
    await h.supply()
    assert await h.data(256) == h.sector[:256]
    await h.command(17, 19)
    assert int(d.request_lba.value) == 9
    await h.supply()
    assert await h.data(256) == h.sector[256:]


@cocotb.test()
async def slow_writable_profile_forces_post_loader_mmc_fallback(d):
    h = await setup(d)
    d.writable.value = 1
    d.h700_mode.value = 1
    await h.init(writable=True)
    await h.command(17, 0)
    await h.supply()
    assert await h.data() == h.sector

    # A reset after successful loader reads starts the payload's fresh probe.
    # Its SD CMD8 and ACMD41 receive no reply, steering it to CMD1/MMC.
    await h.command(0, length=0)
    await h.command(8, 0x1AA, length=0)
    for _ in range(64):
        assert not (await h.cycle())[0]
    await h.command(55)
    await h.command(41, 0x00FF8000, length=0)
    for _ in range(64):
        assert not (await h.cycle())[0]
    await h.command(0, length=0)
    assert (await h.command(1, 0))[1:5] == bytes.fromhex("c0ff8080")

    # Exercise the complete H700 hybrid timing path, including the ordinary
    # R1 MMC selection response with DAT0 released.
    await h.init_mmc()


@cocotb.test()
async def mmc_only_profile_forces_initial_mmc_fallback(d):
    h = await setup(d)
    d.writable.value = 1
    d.mmc_only.value = 1

    await h.command(0, length=0)
    await h.command(8, 0x1AA, length=0)
    for _ in range(64):
        assert not (await h.cycle())[0]
    await h.command(55, length=0)
    for _ in range(64):
        assert not (await h.cycle())[0]
    await h.command(41, 0x00FF8000, length=0)
    for _ in range(64):
        assert not (await h.cycle())[0]

    await h.command(0, length=0)
    await h.init_mmc()


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
async def mmc_predefined_multiblock_count_stops_without_cmd12(d):
    h = await setup(d)
    d.writable.value = 1
    d.mmc_only.value = 1
    await h.init_mmc()

    response = await h.command(23, 3)
    assert not int.from_bytes(response[1:5], "big") & (1 << 22)
    await h.command(18, 40)
    for lba in (40, 41, 42):
        assert int(d.request_lba.value) == lba
        await h.supply()
        assert await h.data() == h.sector

    for _ in range(20):
        await h.cycle()
    assert not int(d.request_valid.value), "CMD23 count started a fourth read"
    assert not int(d.dat_oe.value), "CMD23 count left the data bus driven"

    # Unsupported CMD23 flag bits are rejected without affecting a later
    # ordinary single-block read.
    response = await h.command(23, 0x80000001)
    assert int.from_bytes(response[1:5], "big") & (1 << 22)
    await h.command(17, 43)
    assert int(d.request_lba.value) == 43
    await h.supply()
    assert await h.data() == h.sector


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
