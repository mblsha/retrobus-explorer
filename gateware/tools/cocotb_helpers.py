from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def start_clock(signal, period_ns: int = 10):
    return cocotb.start_soon(Clock(signal, period_ns, units="ns").start())


async def tick(clk, cycles: int = 1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")
