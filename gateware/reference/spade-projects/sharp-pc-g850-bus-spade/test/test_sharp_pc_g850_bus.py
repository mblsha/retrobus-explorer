# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


@cocotb.test()
async def wait_output_pulses_after_bus_fall(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 0
    dut.ft_clk.value = 0
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    dut.ft_data.value = 0
    dut.ft_be.value = 0

    dut.z80_mreq.value = 1
    dut.z80_m1.value = 1
    dut.z80_ioreset.value = 0
    dut.z80_iorq.value = 1
    dut.z80_int1.value = 0
    dut.z80_rd.value = 1
    dut.z80_wr.value = 1

    dut.data.value = 0xA5
    dut.addr.value = 0x1234
    dut.addr_bnk.value = 0x2
    dut.addr_ceram2.value = 0
    dut.addr_cerom2.value = 1

    await tick(dut.clk, 3)
    dut.rst_n.value = 1
    await tick(dut.clk, 3)

    assert int(dut.z80_wait.value) == 1

    dut.z80_mreq.value = 0
    await tick(dut.clk, 2)
    dut.z80_mreq.value = 1

    await tick(dut.clk, 1)
    assert int(dut.z80_wait.value) == 0

    await tick(dut.clk, 4)
    assert int(dut.z80_wait.value) == 1
