"""SD writes through native DDR arbitration, followed by SD readback."""

import cocotb
from test_ddr_integration import memory_model
from test_integration import exercise_image
from test_sd_write import send_packet


@cocotb.test()
async def native_ddr_read_write_roundtrips(d):
    d.diagnostic_status.value = 0
    d.initialized.value = 1
    d.ddr_cmd_ready.value = 0
    d.ddr_wdata_ready.value = 0
    d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    memory = {}
    memory_clock = d.clk
    if hasattr(d, "memory_clk"):
        from cocotb.clock import Clock
        from cocotb.triggers import Timer

        async def start_memory():
            await Timer(3, units="ns")
            await Clock(d.memory_clk, 12.5, units="ns").start()

        cocotb.start_soon(start_memory())
        memory_clock = d.memory_clk
    task = cocotb.start_soon(memory_model(d, memory, clock=memory_clock))
    h, image = await exercise_image(d, writable=True, leave_armed=True)
    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        for lba in (0, 128, 16383, 524287):
            await h.command(24, lba * 512)
            expected = await send_packet(h, wide, lba + 43)
            await h.command(17, lba * 512)
            assert await h.data(wide=wide) == expected
        await h.command(25, 1000 * 512)
        expected_blocks = [await send_packet(h, wide, n) for n in (91, 92, 93, 94)]
        await h.command(12)
        for n, expected in enumerate(expected_blocks):
            await h.command(17, (1000 + n) * 512)
            assert await h.data(wide=wide) == expected
        # Exercise streaming through both native FIFOs and the sector cache,
        # including release/refill while CMD18 remains active.
        await h.command(18, 1000 * 512)
        for expected in expected_blocks:
            assert await h.data(wide=wide) == expected
        await h.command(12)
        before = dict(memory)
        await h.command(24, 128 * 512)
        await send_packet(h, wide, 244, corrupt=True)
        assert memory == before
        await h.command(13, 0x10000)
        await h.command(17, 127 * 512)
        assert await h.data(wide=wide) == image[127 * 512 : 128 * 512]
    # Cancel a read while the slower memory side is still fetching its sector,
    # then immediately request a new generation. Delayed responses must drain
    # without being accepted as the new sector.
    for _ in range(4):
        await h.command(17, 524287 * 512)
        await h.command(12)
        await h.command(17, 127 * 512)
        assert await h.data(wide=True) == image[127 * 512 : 128 * 512]
    task.kill()
