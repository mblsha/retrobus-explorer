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
async def changed_flags_pulse_and_uarts_emit_on_change(dut):
    await _init(dut)

    idle = int(dut.saleae.value)
    assert idle == 0b1010_0000

    dut.addr.value = 0x00001
    dut.data.value = 0x01
    await tick(dut.clk, 1)

    v = int(dut.saleae.value)
    assert v == 0b1111_0000

    await tick(dut.clk, 1)
    v = int(dut.saleae.value)
    assert v == 0b1010_0000

    await tick(dut.clk, 1)
    v = int(dut.saleae.value)
    assert ((v >> 7) & 1) == 0
    assert ((v >> 5) & 1) == 0

    await tick(dut.clk, 1)
    v = int(dut.saleae.value)
    assert ((v >> 7) & 1) == 1
    assert ((v >> 5) & 1) == 1

    for _ in range(8):
        await tick(dut.clk, 1)

    v = int(dut.saleae.value)
    assert ((v >> 7) & 1) == 0
    assert ((v >> 5) & 1) == 1

    for _ in range(10):
        await tick(dut.clk, 1)

    v = int(dut.saleae.value)
    assert ((v >> 7) & 1) == 1
    assert ((v >> 5) & 1) == 1


@cocotb.test()
async def unchanged_inputs_keep_flags_low_and_unrelated_outputs_tied_off(dut):
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
    assert int(dut.saleae.value) == 0b1111_0000

    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0b1010_0000
