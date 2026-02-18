# top = led_counter

import cocotb
from spade import SpadeExt
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


@cocotb.test()
async def resets_and_counts_with_configurable_max(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, period=10, units="ns").start())

    s.i.max = "3"
    s.i.rst = "true"
    await tick(clk, 3)
    s.o.assert_eq("0")

    s.i.rst = "false"
    await tick(clk, 1)
    s.o.assert_eq("1")

    await tick(clk, 4)
    s.o.assert_eq("2")

    await tick(clk, 4)
    s.o.assert_eq("3")
