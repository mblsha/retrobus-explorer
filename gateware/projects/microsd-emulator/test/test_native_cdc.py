import random
import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, Combine, with_timeout


async def transfer(
    src_clk, dst_clk, valid, ready, inputs, out_valid, out_ready, outputs, values, seed
):
    async def producer():
        rng = random.Random(seed)
        for value in values:
            await FallingEdge(src_clk)
            while rng.randrange(5) == 0:
                valid.value = 0
                await FallingEdge(src_clk)
            for signal, word in zip(inputs, value):
                signal.value = word
            valid.value = 1
            while True:
                await Timer(1, units="ns")
                accepted = int(ready.value)
                await RisingEdge(src_clk)
                if accepted:
                    break
                await FallingEdge(src_clk)
        await FallingEdge(src_clk)
        valid.value = 0

    async def consumer():
        rng = random.Random(seed + 100)
        for _ in range(50):
            await FallingEdge(dst_clk)
        for expected in values:
            while True:
                await FallingEdge(dst_clk)
                out_ready.value = int(rng.randrange(3) != 0)
                await Timer(1, units="ns")
                accepted = int(out_valid.value) and int(out_ready.value)
                actual = tuple(int(s.value) for s in outputs)
                await RisingEdge(dst_clk)
                if accepted:
                    assert actual == expected
                    break
        await FallingEdge(dst_clk)
        out_ready.value = 0

    await Combine(cocotb.start_soon(producer()), cocotb.start_soon(consumer()))


@cocotb.test()
async def independent_native_channels_backpressure_and_common_reset(d):
    cocotb.start_soon(
        Clock(
            d.s_clk, float(os.environ.get("MICROSD_CDC_SRC_NS", "10")), units="ns"
        ).start()
    )

    async def other_clock():
        phase = float(os.environ.get("MICROSD_CDC_PHASE_NS", "3"))
        if phase:
            await Timer(phase, units="ns")
        await Clock(
            d.m_clk, float(os.environ.get("MICROSD_CDC_DST_NS", "12")), units="ns"
        ).start()

    cocotb.start_soon(other_clock())
    for name in (
        "s_cmd_valid",
        "s_wdata_valid",
        "m_rdata_valid",
        "m_cmd_ready",
        "m_wdata_ready",
        "s_rdata_ready",
        "s_cmd_address",
        "s_cmd_write",
        "s_wdata",
        "s_wmask",
        "m_rdata",
    ):
        getattr(d, name).value = 0

    async def reset():
        d.s_rst.value = 1
        d.m_rst.value = 1
        await Timer(180, units="ns")
        d.s_rst.value = 0
        d.m_rst.value = 0
        await Timer(180, units="ns")

    await reset()
    # Fill all channels while their consumers are stopped, then reset both
    # domains: none of this abandoned epoch may leak into fresh transactions.
    d.s_cmd_valid.value = d.s_wdata_valid.value = d.m_rdata_valid.value = 1
    await Timer(500, units="ns")
    assert not int(d.s_cmd_ready.value)
    assert not int(d.s_wdata_ready.value)
    assert not int(d.m_rdata_ready.value)
    d.s_cmd_valid.value = d.s_wdata_valid.value = d.m_rdata_valid.value = 0
    await reset()
    rng = random.Random(314)
    commands = [(rng.getrandbits(24), rng.getrandbits(1)) for _ in range(300)]
    writes = [(rng.getrandbits(128), rng.getrandbits(16)) for _ in range(300)]
    reads = [(rng.getrandbits(128),) for _ in range(300)]
    jobs = [
        transfer(
            d.s_clk,
            d.m_clk,
            d.s_cmd_valid,
            d.s_cmd_ready,
            (d.s_cmd_address, d.s_cmd_write),
            d.m_cmd_valid,
            d.m_cmd_ready,
            (d.m_cmd_address, d.m_cmd_write),
            commands,
            1,
        ),
        transfer(
            d.s_clk,
            d.m_clk,
            d.s_wdata_valid,
            d.s_wdata_ready,
            (d.s_wdata, d.s_wmask),
            d.m_wdata_valid,
            d.m_wdata_ready,
            (d.m_wdata, d.m_wmask),
            writes,
            2,
        ),
        transfer(
            d.m_clk,
            d.s_clk,
            d.m_rdata_valid,
            d.m_rdata_ready,
            (d.m_rdata,),
            d.s_rdata_valid,
            d.s_rdata_ready,
            (d.s_rdata,),
            reads,
            3,
        ),
    ]
    await with_timeout(Combine(*(cocotb.start_soon(job) for job in jobs)), 100, "us")
    for _ in range(20):
        await RisingEdge(d.s_clk)
    assert not int(d.s_rdata_valid.value)
    assert not int(d.m_cmd_valid.value)
    assert not int(d.m_wdata_valid.value)
