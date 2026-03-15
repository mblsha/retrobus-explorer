# top = main

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


async def _init(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 0
    dut.addr.value = 0
    dut.vcc2.value = 0
    dut.data.value = 0
    dut.ce1.value = 0
    dut.ce6.value = 1
    dut.nc.value = 0
    dut.oe.value = 0

    await tick(dut.clk, 2)
    dut.rst_n.value = 1
    await tick(dut.clk, 1)


@cocotb.test()
async def named_pc_e500_pins_map_directly_to_saleae(dut):
    await _init(dut)

    dut.rw.value = 0
    dut.addr.value = 0x00
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0x00

    dut.rw.value = 1
    dut.addr.value = 0x01
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0x0C

    dut.addr.value = 0x0F
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0xDC

    dut.addr.value = 0x0A
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0x94


@cocotb.test()
async def unrelated_outputs_are_tied_off(dut):
    await _init(dut)

    dut.usb_rx.value = 0
    dut.vcc2.value = 1
    dut.data.value = 0xFF
    dut.ce1.value = 1
    dut.ce6.value = 0
    dut.nc.value = 1
    dut.oe.value = 1
    dut.rw.value = 1
    dut.addr.value = (1 << 18) - 1
    await tick(dut.clk, 1)

    assert int(dut.usb_tx.value) == 1
    assert int(dut.led.value) == 0
