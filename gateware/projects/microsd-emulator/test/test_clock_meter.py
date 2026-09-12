import cocotb
from cocotb_helpers import start_clock, tick


@cocotb.test()
async def counts_active_clock_and_retains_peak_through_gating(d):
    start_clock(d.clk, 10)
    d.rst.value = 1
    d.sd_clk.value = 0
    d.window_cycles.value = 64
    await tick(d.clk, 4)
    d.rst.value = 0
    total = 0
    for period, expected in ((16, 4), (8, 8), (4, 16)):
        for _ in range(256 // period):
            d.sd_clk.value = 0
            await tick(d.clk, period // 2)
            d.sd_clk.value = 1
            await tick(d.clk, period // 2)
        d.sd_clk.value = 0
        await tick(d.clk, 10)
        total += 256 // period
        assert int(d.total_edges.value) == total
        assert int(d.peak_edges.value) == expected
        assert int(d.minimum_period.value) == period
        assert int(d.latest_period.value) == period
    await tick(d.clk, 128)
    assert int(d.peak_edges.value) == 16 and int(d.minimum_period.value) == 4
    d.rst.value = 1
    await tick(d.clk, 4)
    assert int(d.peak_edges.value) == int(d.minimum_period.value) == 0
