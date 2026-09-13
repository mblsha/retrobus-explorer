import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


from sd_support import crc_bit


@cocotb.test()
async def sector_crc_width_errors_and_cancel(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())

    async def tick(**values):
        await FallingEdge(d.clk)
        for name, value in values.items():
            getattr(d, name).value = value
        await RisingEdge(d.clk)
        await Timer(1, units="ns")

    await tick(rst=1, start=0, cancel=0, wide=0, sample=0, dat=15, byte_index=0)
    await tick(rst=0)

    async def receive(wide, corrupt=None, end_bad=False):
        payload = bytes((i * 37 + (i >> 8) * 11 + 17) & 255 for i in range(512))
        await tick(start=1, wide=wide, sample=0)
        await tick(start=0, dat=15, sample=1)
        await tick(dat=0 if wide else 14)
        crcs = [0] * 4
        for byte in payload:
            for shift in range(4, -1, -4) if wide else range(7, -1, -1):
                value = (byte >> shift) & (15 if wide else 1)
                for lane in range(4):
                    crcs[lane] = crc_bit(crcs[lane], value >> lane & 1)
                await tick(dat=value if wide else value | 14)
        for shift in range(15, -1, -1):
            value = sum(((crc >> shift) & 1) << lane for lane, crc in enumerate(crcs))
            if corrupt is not None and shift == 7:
                value ^= 1 << corrupt
            await tick(dat=value if wide else (value & 1) | 14)
        await tick(dat=0 if end_bad else 15)
        assert int(d.complete.value) == 1
        assert int(d.good.value) == int(corrupt is None and not end_bad)
        assert int(d.active.value) == 0
        await tick(sample=0)
        assert int(d.complete.value) == 0
        if corrupt is None and not end_bad:
            for i, byte in enumerate(payload):
                await tick(byte_index=i)
                assert int(d.sector_byte.value) == byte, (wide, i)

    await receive(False)
    await receive(True)
    for lane in range(4):
        await receive(True, corrupt=lane)
    await receive(False, corrupt=0)
    await receive(True, end_bad=True)
    await tick(start=1, wide=1, sample=0)
    await tick(start=0, sample=1, dat=0)
    await tick(dat=5)
    await tick(cancel=1)
    assert not int(d.active.value)
    assert not int(d.complete.value)
    assert not int(d.good.value)
    await tick(cancel=0, sample=0)
    await receive(True)
