# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def read_pins(dut):
    return [
        int(dut.pin0.value),
        int(dut.pin1.value),
        int(dut.pin2.value),
        int(dut.pin3.value),
        int(dut.pin4.value),
        int(dut.pin5.value),
        int(dut.pin6.value),
        int(dut.pin7.value),
    ]


def expected_bits(counter_value):
    return [(counter_value >> i) & 1 for i in range(8)]


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


@cocotb.test()
async def output_pins_follow_counter_bits(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    # Hold reset active for two cycles to get deterministic startup state.
    dut.rst_n.value = 0
    await tick(dut.clk, 2)
    assert read_pins(dut) == [0] * 8

    # Release reset. Counter starts at 0 and increments on each clock edge.
    dut.rst_n.value = 1

    for expected_counter in range(1, 33):
        await tick(dut.clk, 1)
        observed = read_pins(dut)
        expected = expected_bits(expected_counter & 0xFF)
        assert observed == expected, (
            f"counter={expected_counter} expected pins {expected} got {observed}"
        )
