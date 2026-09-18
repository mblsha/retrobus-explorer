import cocotb
from cocotb_helpers import tick


from sd_support import setup


@cocotb.test()
async def h700_data_launch_uses_prepared_full_cycle_pipeline(d):
    await setup(d)
    d.h700_mode.value = 1

    d.sd_clk.value = 0
    falling_launches = 0
    for _ in range(8):
        await tick(d.clk, 1)
        falling_launches += int(d.data_output_advance.value)
    assert falling_launches == 0

    d.sd_clk.value = 1
    rising_samples = 0
    rising_launches = 0
    for _ in range(8):
        await tick(d.clk, 1)
        rising_samples += int(d.sd_sample_tick.value)
        rising_launches += int(d.data_output_advance.value)
    assert rising_samples == 1
    assert rising_launches == 1

    d.h700_falling_phase.value = 1
    d.sd_clk.value = 0
    falling_launches = 0
    for _ in range(8):
        await tick(d.clk, 1)
        falling_launches += int(d.data_output_advance.value)
    assert falling_launches == 1


@cocotb.test()
async def h700_command_launch_phase_follows_early_command_option(d):
    await setup(d)
    d.h700_mode.value = 1

    # The default slow-command path advances after the external falling edge.
    d.sd_clk.value = 1
    for _ in range(8):
        await tick(d.clk, 1)
    assert not int(d.command_output_advance.value)
    d.sd_clk.value = 0
    late_launches = 0
    for _ in range(8):
        await tick(d.clk, 1)
        late_launches += int(d.command_output_advance.value)
    assert late_launches == 1

    # The diagnostic alternative advances after the external rising edge.
    d.h700_early_command.value = 1
    d.sd_clk.value = 1
    early_launches = 0
    for _ in range(8):
        await tick(d.clk, 1)
        early_launches += int(d.command_output_advance.value)
    assert early_launches == 1
    d.sd_clk.value = 0
    for _ in range(8):
        await tick(d.clk, 1)
    assert not int(d.command_output_advance.value)


@cocotb.test()
async def h700_idle_data_lines_hold_the_pull_up_level(d):
    """The H700 adapter has no effective pull-up, so a released DAT0 reads low
    and the host's R1b busy check never completes. This profile holds the idle
    high level while the host is clocking, and releases everything once the
    host clock stops so an armed FPGA cannot drive an unpowered target."""
    h = await setup(d)

    # The qualified profiles keep standards-compliant released data lines.
    for _ in range(4):
        assert (await h.cycle())[2] == 0

    d.h700_mode.value = 1
    # The liveness gate measures an edge rate, so give it a full window.
    for _ in range(120):
        oe, value = (await h.cycle())[2:]
    assert oe == 15, "the H700 profile must hold the idle data lines"
    assert value & oe == oe, "the idle level must be high, not busy"

    # The watchdog releases the lines shortly after the host clock stops.
    d.sd_clk.value = 0
    await tick(d.clk, 33000)
    assert int(d.dat_oe.value) == 0, "an idle host clock must release the lines"

    # Sparse transitions are noise, not a host. With the target unpowered the
    # floating SD_CLK input still produced a few hundred edges per second, so
    # an edge-rate gate must ignore them and keep the lines released.
    for _ in range(8):
        d.sd_clk.value = 1
        await tick(d.clk, 3000)
        d.sd_clk.value = 0
        await tick(d.clk, 3000)
        assert int(d.dat_oe.value) == 0, "noise engaged the compatibility drive"

    # Clocking again re-engages the compatibility level.
    for _ in range(120):
        oe, value = (await h.cycle())[2:]
    assert oe == 15 and value & oe == oe


@cocotb.test()
async def sd_selection_busy_never_leaves_the_data_line_low(d):
    """SD CMD7 answers R1b: the card pulses DAT0 low, and the host then polls
    that line for the end of busy. The H700 adapter has no pull-up, so a
    released line still reads low and the poll never completes."""
    h = await setup(d)
    d.h700_mode.value = 1
    await h.init()
    await h.command(7, 0x10000)

    busy_seen = False
    busy_cycles = 0
    for _ in range(4000):
        await tick(d.clk, 1)
        oe, value = int(d.dat_oe.value), int(d.dat_out.value)
        if oe & 1 and not value & 1:
            busy_seen = True
            busy_cycles += 1
        elif busy_seen:
            break
    assert busy_seen, "CMD7 never asserted DAT0 busy"
    # The pulse must end on its own even though the host has gated SD_CLK.
    assert busy_cycles < 4000, "DAT0 busy never released"
    # The pulse leaves the stale low in the final data register, which the next
    # SD edge refreshes. The card must therefore present the idle level as soon
    # as the host clocks again, which is what its busy poll needs to complete.
    for _ in range(4):
        oe, value = (await h.cycle())[2:]
    assert oe == 15, "the profile released the data lines"
    assert value == 15, "CMD7 left DAT0 low, which reads as a card still busy"


@cocotb.test()
async def sd_selection_busy_releases_in_the_qualified_profile(d):
    """The compatibility drive is H700-only; the qualified SD profile keeps
    standards-compliant released data lines after the same busy pulse."""
    h = await setup(d)
    await h.init()
    await h.command(7, 0x10000)
    for _ in range(400):
        await tick(d.clk, 1)
    assert int(d.dat_oe.value) == 0


@cocotb.test()
async def h700_profile_declares_a_card_without_the_switch_function(d):
    """U-Boot issues the SD CMD6 switch, which this emulator does not
    implement, only for SD 1.10 and later. Declaring SD 1.01 makes
    sd_change_freq() return early instead of waiting for a status block."""
    h = await setup(d)
    d.h700_mode.value = 1
    await h.init()
    await h.command(55, 0x10000)
    await h.command(51)
    assert await h.data(8) == bytes.fromhex("0005000000000000")


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
    observed_data = int(d.trace_pin_data.value)
    assert observed_data & 0xFFFF == 4114
    assert (observed_data >> 16) & 0xFF >= 2
    assert not observed_data & (1 << 24)
    assert (observed_data >> 26) & 0xF == 1
    observed_mismatch = int(d.trace_pin_data_mismatch.value)
    assert observed_mismatch & 0xFFFF == 0
    assert observed_mismatch >> 16 == 0xFFFF

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
async def h700_profile_leaves_post_loader_sd_probe_available(d):
    h = await setup(d)
    d.writable.value = 1
    d.h700_mode.value = 1
    await h.init(writable=True)
    await h.command(17, 0)
    await h.supply()
    assert await h.data() == h.sector

    # A reset after successful loader reads starts the payload's fresh probe.
    # The H700 compatibility profile must keep answering SD negotiation; a
    # hardware control trial showed that the payload chooses MMC without the
    # emulator manufacturing that fallback.
    await h.command(0, length=0)
    assert (await h.command(8, 0x1AA))[1:5] == bytes.fromhex("000001aa")
    await h.command(55)
    assert (await h.command(41, 0x00FF8000))[1:5] == bytes.fromhex("80ff8000")

    # The host may still reset and choose the legacy MMC probe itself.
    await h.command(0, length=0)
    assert (await h.command(1, 0))[1:5] == bytes.fromhex("c0ff8080")

    # Fresh MMC selection uses ordinary R1 and never holds DAT0 busy. Reject a
    # four-bit switch in this diagnostic profile so H700 transfer testing stays
    # on the one data line already used during identification.
    await h.init_mmc()
    oe = int(d.dat_oe.value)
    assert oe == 0 or int(d.dat_out.value) & oe == oe, (
        "fresh MMC selection must not hold the data lines low"
    )
    response = await h.command(6, 0x03B70100)
    assert int.from_bytes(response[1:5], "big") & (1 << 22)
    status = await h.command(13, 0x10000)
    assert int.from_bytes(status[1:5], "big") & (1 << 7)
    cleared = await h.command(13, 0x10000)
    assert not int.from_bytes(cleared[1:5], "big") & (1 << 7)
    await h.command(17, 9)
    await h.supply()
    assert await h.data() == h.sector
    assert (int(d.trace_pin_data.value) >> 26) & 0xF == 1


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
    # Let a third block begin, then request stop with native CMD12 on CMD. The
    # card must finish this block rather than truncating its payload or CRC.
    for _ in range(20):
        await h.cycle()
    assert int(d.dat_oe.value) == 15
    await h.command(12)
    assert int(d.dat_oe.value) == 15
    for _ in range(1100):
        await h.cycle()
        if not int(d.dat_oe.value):
            break
    assert not int(d.dat_oe.value) and not int(d.request_valid.value)
    await h.command(0, length=0)
    await h.init()


@cocotb.test()
async def multiblock_stop_is_accepted_anywhere_in_a_block(d):
    """A CMD12 that lands mid-block must still stop the stream.

    On hardware roughly half the RG35XX boots show one CMD18 streaming far past
    the file, which is what a missed stop looks like from the card side: the
    host waits for a transfer that never ends while the card keeps sending. The
    existing coverage injects CMD12 at one fixed offset, so any offset-dependent
    miss would go unseen. A four-bit block is 1 start + 1024 payload + 16 CRC +
    1 end sampled edges, so these offsets cover the start bit, early and mid
    payload, the CRC window, the end bit and the gap that follows.
    """
    h = await setup(d)
    for offset in (0, 1, 7, 512, 1020, 1024, 1035, 1041, 1043):
        await h.init()
        await h.command(55, 0x10000)
        await h.command(6, 2)
        await h.command(18, 126 * 512)
        await h.supply()
        assert await h.data(wide=True) == h.sector
        await h.cycle()
        await h.supply()

        for _ in range(offset):
            await h.cycle()
        await h.command(12)

        stopped = False
        for _ in range(2200):
            if int(d.request_valid.value):
                await h.supply()
            await h.cycle()
            if not int(d.dat_oe.value):
                stopped = True
                break
        assert stopped, f"CMD12 at offset {offset} did not stop the stream"

        # It must stay stopped: no further block may start, and no further
        # sector may be requested from the backend.
        for _ in range(64):
            await h.cycle()
            assert not int(d.dat_oe.value), f"offset {offset} restarted a block"
            assert not int(d.request_valid.value), f"offset {offset} kept reading"
        await h.command(0, length=0)


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
