import random
import cocotb
from cocotb_helpers import tick
from test_storage import initialize, read_buffer


@cocotb.test()
async def ddr_random_backpressure_sparse_and_late_cancelled_response(d):
    d.initialized.value = 0
    d.resident_bytes.value = 65536
    d.cmd_ready.value = 0
    d.rdata_valid.value = 0
    d.rdata.value = 0
    await initialize(d)
    d.armed.value = 1
    d.request_valid.value = 1
    d.request_lba.value = 127
    await tick(d.clk, 10)
    assert not int(d.cmd_valid.value)
    d.initialized.value = 1
    rng = random.Random(9901)
    expected = bytes((i * 59 + 7) & 255 for i in range(512))
    for word in range(32):
        for _ in range(100):
            await tick(d.clk)
            if int(d.cmd_valid.value):
                break
        else:
            assert False, "missing DDR command"
        address = int(d.cmd_address.value)
        assert address == 127 * 32 + word
        await tick(d.clk, rng.randrange(1, 10))
        assert int(d.cmd_valid.value) and int(d.cmd_address.value) == address
        d.cmd_ready.value = 1
        await tick(d.clk)
        d.cmd_ready.value = 0
        await tick(d.clk, rng.randrange(1, 15))
        assert int(d.rdata_ready.value)
        d.rdata.value = int.from_bytes(expected[word * 16 : (word + 1) * 16], "little")
        d.rdata_valid.value = 1
        await tick(d.clk)
        d.rdata_valid.value = 0
    await tick(d.clk, 20)
    assert int(d.sector_ready.value)
    assert await read_buffer(d) == expected
    d.request_valid.value = 0
    d.buffer_release.value = 1
    await tick(d.clk, 2)
    d.buffer_release.value = 0
    # A command already accepted by DDR cannot be cancelled at the PHY. Drain it.
    d.generation.value = 2
    d.request_lba.value = 0
    d.request_valid.value = 1
    d.cmd_ready.value = 1
    for _ in range(20):
        await tick(d.clk)
        if int(d.rdata_ready.value):
            break
    assert int(d.rdata_ready.value)
    d.cmd_ready.value = 0
    d.buffer_release.value = 1
    d.request_valid.value = 0
    await tick(d.clk)
    d.buffer_release.value = 0
    d.generation.value = 3
    d.request_lba.value = 128
    d.request_valid.value = 1
    await tick(d.clk, 20)
    assert int(d.rdata_ready.value) and not int(d.cmd_valid.value)
    assert not int(d.sector_ready.value)
    d.rdata.value = (1 << 128) - 1
    d.rdata_valid.value = 1
    await tick(d.clk)
    d.rdata_valid.value = 0
    for _ in range(600):
        await tick(d.clk)
        assert not int(d.cmd_valid.value), "sparse sector must not read DDR"
        if int(d.sector_ready.value):
            break
    assert int(d.sector_ready.value) and int(d.sector_generation.value) == 3
    assert await read_buffer(d) == bytes(512)


@cocotb.test()
async def out_of_physical_range_never_wraps_native_address(d):
    d.initialized.value = 1
    d.resident_bytes.value = 268435456
    d.cmd_ready.value = 1
    d.rdata_valid.value = 0
    d.rdata.value = 0
    await initialize(d)
    d.armed.value = 1
    d.request_valid.value = 1
    for lba in (524288, 0xffffffff):
        d.request_lba.value = lba
        for _ in range(20):
            await tick(d.clk)
            assert not int(d.cmd_valid.value)
            assert not int(d.sector_ready.value)
    d.request_lba.value = 524287
    for _ in range(10):
        await tick(d.clk)
        if int(d.cmd_valid.value):
            assert int(d.cmd_address.value) == 524287 * 32
            break
    else:
        assert False, "last physical sector must remain addressable"
