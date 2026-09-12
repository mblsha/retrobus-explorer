import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from test_write_rx import crc_bit


@cocotb.test()
async def crc_gated_commit_response_busy_and_cancel(d):
    cocotb.start_soon(Clock(d.clk, 12, units="ns").start())

    async def step(**values):
        await FallingEdge(d.clk)
        for name, value in values.items():
            getattr(d, name).value = value
        await RisingEdge(d.clk)
        await Timer(1, units="ps")

    await step(
        rst=1,
        prepared_mode=0,
        start=0,
        cancel=0,
        stop=0,
        wide=0,
        lba=0,
        sample=0,
        fall=0,
        dat=15,
        cmd_ready=0,
        wdata_ready=0,
    )
    await step(rst=0)
    allow = [False]
    memory = {}
    completed_words = []

    async def model():
        rng = random.Random(550)
        address = payload = None
        while True:
            await FallingEdge(d.clk)
            cr = allow[0] and rng.randrange(3) != 0
            wr = allow[0] and rng.randrange(3) != 0
            d.cmd_ready.value = cr
            d.wdata_ready.value = wr
            await Timer(1, units="ns")
            if cr and int(d.cmd_valid.value):
                assert address is None
                address = int(d.cmd_address.value)
            if wr and int(d.wdata_valid.value):
                assert payload is None and int(d.wdata_mask.value) == 0xFFFF
                payload = int(d.wdata.value)
            await RisingEdge(d.clk)
            if address is not None and payload is not None:
                memory[address] = payload.to_bytes(16, "little")
                completed_words.append(address)
                address = payload = None

    task = cocotb.start_soon(model())

    async def receive(wide, lba, corrupt=False):
        payload = bytes((i * 53 + lba + 9) & 255 for i in range(512))
        await step(start=1, wide=wide, lba=lba, sample=0, fall=0)
        await step(start=0, lba=777, sample=1, dat=0 if wide else 14)
        crcs = [0] * 4
        for byte in payload:
            for shift in range(4, -1, -4) if wide else range(7, -1, -1):
                value = byte >> shift & (15 if wide else 1)
                for lane in range(4):
                    crcs[lane] = crc_bit(crcs[lane], value >> lane & 1)
                await step(dat=value if wide else value | 14)
        for shift in range(15, -1, -1):
            value = sum((crc >> shift & 1) << lane for lane, crc in enumerate(crcs))
            if corrupt and shift == 7:
                value ^= 4 if wide else 1
            await step(dat=value if wide else value | 14)
        await step(dat=15)
        await step(sample=0)
        return payload

    for wide, lba in ((False, 0), (True, 16383)):
        allow[0] = False
        before = len(completed_words)
        expected = await receive(wide, lba)
        driven = []
        for _ in range(20):
            await step(fall=1)
            if int(d.dat_oe.value):
                assert int(d.dat_oe.value) == 1
                driven.append(int(d.dat_out.value) & 1)
        assert driven[:5] == [0, 0, 1, 0, 1]
        assert int(d.commit_busy.value) and not int(d.complete.value)
        assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) & 1 == 0
        allow[0] = True
        for _ in range(5000):
            await step()
            if int(d.complete.value):
                break
        else:
            assert False, "write response remained busy"
        assert int(d.good.value) and len(completed_words) == before + 32
        assert b"".join(memory[lba * 32 + i] for i in range(32)) == expected
        await step(fall=0)

    for lba, corrupt in ((127, True), (524288, False)):
        before = dict(memory)
        await receive(True, lba, corrupt=corrupt)
        driven = []
        for _ in range(30):
            await step(fall=1)
            if int(d.dat_oe.value):
                driven.append(int(d.dat_out.value) & 1)
            assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
            if int(d.complete.value):
                break
        assert driven[:5] == [0, 1, 0, 1, 1]
        assert not int(d.good.value) and memory == before
        await step(fall=0)

    # Canceling an incomplete packet cannot mutate storage.
    before = dict(memory)
    await step(start=1, wide=1, lba=64, sample=0)
    await step(start=0, sample=1, dat=0)
    await step(dat=5)
    await step(cancel=1)
    await step(cancel=0, sample=0)
    for _ in range(20):
        await step()
    assert memory == before and not int(d.active.value)

    # CMD12 during programming preserves the response and busy until DDR drains.
    allow[0] = False
    expected = await receive(True, 129)
    await step(stop=1, fall=1)
    await step(stop=0)
    for _ in range(20):
        await step()
    assert int(d.commit_busy.value)
    assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) & 1 == 0
    allow[0] = True
    for _ in range(5000):
        await step()
        if int(d.complete.value):
            break
    else:
        assert False, "stopped accepted commit did not finish its busy response"
    assert int(d.good.value)
    assert b"".join(memory[129 * 32 + i] for i in range(32)) == expected
    await step(fall=0)

    # Once CRC has been accepted, cancel releases SD pins but drains the commit.
    allow[0] = False
    expected = await receive(True, 128)
    await step(cancel=1)
    assert int(d.dat_oe.value) == 0 and int(d.commit_busy.value)
    allow[0] = True
    for _ in range(5000):
        await step()
        assert int(d.dat_oe.value) == 0
        if int(d.commit_complete.value):
            break
    else:
        assert False, "canceled accepted commit did not drain"
    assert b"".join(memory[128 * 32 + i] for i in range(32)) == expected
    task.kill()
