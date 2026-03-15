# top = main

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


def saleae_bit(value, idx):
    return (value >> idx) & 1


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
async def cooldown_delays_uart_and_busy_change_lines_pulse(dut):
    await _init(dut)

    idle = int(dut.saleae.value)
    assert idle == 0b1010_0000

    dut.addr.value = 0x00001
    dut.data.value = 0x01
    await tick(dut.clk, 1)

    v = int(dut.saleae.value)
    assert v == 0b1010_0000

    for _ in range(4):
        await tick(dut.clk, 1)
        v = int(dut.saleae.value)
        assert v == 0b1010_0000

    await tick(dut.clk, 1)
    v = int(dut.saleae.value)
    assert saleae_bit(v, 7) == 0
    assert saleae_bit(v, 5) == 0
    assert saleae_bit(v, 6) == 0
    assert saleae_bit(v, 4) == 0

    dut.addr.value = 0x00002
    dut.data.value = 0x02
    saw_busy_change = False
    for _ in range(3):
        await tick(dut.clk, 1)
        v = int(dut.saleae.value)
        if saleae_bit(v, 6) == 1 and saleae_bit(v, 4) == 1:
            saw_busy_change = True
            break
    assert saw_busy_change

    while True:
        await tick(dut.clk, 1)
        v = int(dut.saleae.value)
        if saleae_bit(v, 7) == 0 and saleae_bit(v, 5) == 0:
            break


@cocotb.test()
async def unchanged_inputs_keep_busy_change_lines_low_and_unrelated_outputs_tied_off(dut):
    await _init(dut)

    dut.usb_rx.value = 0
    dut.vcc2.value = 1
    dut.ce1.value = 1
    dut.ce6.value = 0
    dut.nc.value = 1
    dut.oe.value = 1
    dut.rw.value = 1
    await tick(dut.clk, 1)

    assert int(dut.usb_tx.value) == 1
    assert int(dut.led.value) == 0
    assert int(dut.saleae.value) == 0b1010_0000
