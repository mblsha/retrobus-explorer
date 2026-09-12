import cocotb
from cocotb.triggers import FallingEdge, Timer
from test_sd import setup
from test_sd_write import send_packet


@cocotb.test()
async def status_and_stop_preserve_accepted_programming(d):
    h = await setup(d)
    d.writable.value = 1
    await h.init(writable=True)
    await h.command(55, 0x10000)
    await h.command(6, 2)
    await h.command(25, 33 * 512)
    expected = await send_packet(h, True, 176, wait_complete=False)
    for _ in range(5):
        await h.cycle()
    assert int(d.write_busy.value)
    assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) & 1 == 0
    status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
    assert status & 0x1F00 == 7 << 9
    await h.command(12)
    assert int(d.write_busy.value)
    assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) & 1 == 0
    memory = {}

    async def collect():
        while True:
            await FallingEdge(d.clk)
            await Timer(1, units="ps")
            if int(d.write_cmd_valid.value):
                assert int(d.write_data_valid.value)
                assert int(d.write_mask.value) == 65535
                address = int(d.write_cmd_address.value)
                assert address not in memory
                memory[address] = int(d.write_data.value).to_bytes(16, "little")

    task = cocotb.start_soon(collect())
    # Enable acceptance on the same falling edge the collector observes,
    # rather than losing a first handshake before its coroutine starts.
    await FallingEdge(d.clk)
    d.write_cmd_ready.value = 1
    d.write_data_ready.value = 1
    # Fixed elapsed-time allowance, independent of SD clock speed.
    for _ in range(max(100, int(100_000 // (2 * h.half_ns)))):
        await h.cycle()
        if not int(d.write_busy.value) and not int(d.dat_oe.value):
            break
    else:
        assert False, "CMD12 interrupted completion or busy release"
    assert len(memory) == 32
    assert b"".join(memory[33 * 32 + n] for n in range(32)) == expected
    status = int.from_bytes((await h.command(13, 0x10000))[1:5], "big")
    assert status & 0x1F00 == 0x900
    task.kill()
