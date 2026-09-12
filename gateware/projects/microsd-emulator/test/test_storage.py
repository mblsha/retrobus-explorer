import cocotb
from cocotb_helpers import start_clock, tick


async def initialize(d):
    start_clock(d.clk)
    d.rst.value = 1
    d.armed.value = 0
    d.request_valid.value = 0
    d.request_lba.value = 0
    d.generation.value = 1
    d.buffer_release.value = 0
    d.byte_index.value = 0
    await tick(d.clk, 5)
    d.rst.value = 0
    await tick(d.clk)


async def read_buffer(d):
    data = bytearray()
    for i in range(512):
        d.byte_index.value = i
        await tick(d.clk)
        data.append(int(d.sector_byte.value))
    return bytes(data)


@cocotb.test()
async def bram_sparse_no_alias_and_disarmed_loading(d):
    d.load_valid.value = 0
    d.load_address.value = 0
    d.load_byte.value = 0
    await initialize(d)
    patterns = {
        0: bytes((i * 11) & 255 for i in range(512)),
        127: bytes((i * 23 + 1) & 255 for i in range(512)),
    }
    for lba, data in patterns.items():
        for i, b in enumerate(data):
            d.load_valid.value = 1
            d.load_address.value = lba * 512 + i
            d.load_byte.value = b
            assert int(d.load_ready.value)
            await tick(d.clk)
    d.load_address.value = 65536
    await tick(d.clk)
    assert not int(d.load_ready.value)
    d.load_valid.value = 0
    d.armed.value = 1
    for epoch, lba in enumerate((0, 127, 128, 16383), 2):
        d.generation.value = epoch
        d.request_lba.value = lba
        d.request_valid.value = 1
        for _ in range(1100):
            await tick(d.clk)
            if int(d.sector_ready.value):
                break
        else:
            assert False, "backend timeout"
        assert int(d.sector_generation.value) == epoch
        d.request_valid.value = 0
        assert await read_buffer(d) == patterns.get(lba, bytes(512))
        d.buffer_release.value = 1
        await tick(d.clk, 2)
        d.buffer_release.value = 0
    d.load_valid.value = 1
    d.load_address.value = 0
    d.load_byte.value = 0xFF
    await tick(d.clk, 4)
    assert not int(d.load_ready.value)
