import cocotb
from cocotb_helpers import start_clock, tick


@cocotb.test()
async def physical_bounds_and_last_byte_mask(d):
    start_clock(d.clk, 12)
    d.rst.value = 1
    d.enabled.value = 1
    d.load_valid.value = 0
    d.load_address.value = d.load_byte.value = 0
    d.cmd_ready.value = d.wdata_ready.value = 0
    await tick(d.clk, 4)
    d.rst.value = 0
    d.load_valid.value = 1
    for address in (0x10000000, 0xFFFFFFFF):
        d.load_address.value = address
        for _ in range(8):
            await tick(d.clk)
            assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
            assert not int(d.load_ready.value)
    d.load_address.value = 0x0FFFFFFF
    d.load_byte.value = 0xA5
    await tick(d.clk)
    assert int(d.cmd_valid.value) and int(d.wdata_valid.value)
    assert int(d.cmd_address.value) == 0xFFFFFF
    assert int(d.wdata_mask.value) == 0x8000
    assert int(d.wdata.value) == 0xA5 << 120
    d.cmd_ready.value = 1
    await tick(d.clk)
    d.cmd_ready.value = 0
    assert not int(d.load_ready.value)
    d.wdata_ready.value = 1
    await tick(d.clk)
    d.wdata_ready.value = 0
    await tick(d.clk)
    assert int(d.load_ready.value)
    d.load_valid.value = 0
    await tick(d.clk, 2)
    assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
