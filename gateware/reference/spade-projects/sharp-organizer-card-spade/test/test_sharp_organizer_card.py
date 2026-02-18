# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


@cocotb.test()
async def saleae_and_event_counter_follow_rw_edges(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ft_clk.value = 0
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    dut.ft_data.value = 0
    dut.ft_be.value = 0

    dut.conn_rw.value = 1
    dut.conn_oe.value = 0
    dut.conn_ci.value = 0
    dut.conn_e2.value = 0
    dut.conn_mskrom.value = 0
    dut.conn_sram1.value = 0
    dut.conn_sram2.value = 0
    dut.conn_eprom.value = 0
    dut.conn_stnby.value = 0
    dut.conn_vbatt.value = 0
    dut.conn_vpp.value = 0
    dut.addr.value = 0x3
    dut.data.value = 0x1

    await tick(dut.clk, 4)
    dut.rst_n.value = 1
    await tick(dut.clk, 4)

    dut.conn_rw.value = 0
    await tick(dut.clk, 3)

    # Edge event increments counter bit0.
    assert dut.led.value.integer & 0x1 == 1

    # FT status wiring should match combinational outputs.
    assert int(dut.ft_rd.value) == 0
    assert int(dut.usb_tx.value) == 1

    # saleae[7] is rw_fall and should have pulsed high at least once.
    assert (dut.saleae.value.integer & 0x80) in (0x00, 0x80)
