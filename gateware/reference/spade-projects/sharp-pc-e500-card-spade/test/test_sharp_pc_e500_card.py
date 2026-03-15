# top = main

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


async def _init(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ffc_data.value = 0

    await tick(dut.clk, 2)
    dut.rst_n.value = 1
    await tick(dut.clk, 1)


@cocotb.test()
async def low_ffc_data_pins_map_directly_to_saleae(dut):
    await _init(dut)

    dut.ffc_data.value = 0x00
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0x00

    dut.ffc_data.value = 0x01
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0x01

    dut.ffc_data.value = 0xA5
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0xA5

    dut.ffc_data.value = 0x1FF
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0xFF


@cocotb.test()
async def unrelated_outputs_are_tied_off(dut):
    await _init(dut)

    dut.ffc_data.value = (1 << 48) - 1
    dut.usb_rx.value = 0
    await tick(dut.clk, 1)

    assert int(dut.usb_tx.value) == 1
    assert int(dut.led.value) == 0
