# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def counter_drives_led_saleae_and_ffc(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 2)

    assert dut.led.value.integer == 0
    assert dut.saleae.value.integer == 0
    assert dut.ffc_data.value.integer == 0
    assert int(dut.usb_tx.value) == 1

    dut.rst_n.value = 1
    for cycle in range(1, 33):
        await tick(dut.clk, 1)
        assert dut.led.value.integer == (cycle & 0xFF)
        assert dut.saleae.value.integer == (cycle & 0xFF)
        assert dut.ffc_data.value.integer == (cycle & ((1 << 48) - 1))
