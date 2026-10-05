import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from cocotb_helpers import start_clock


@cocotb.test()
async def dual_port_upload_bus_write_and_read_latency(dut):
    start_clock(dut.clk)
    dut.host_addr.value = 0
    dut.host_data.value = 0
    dut.host_write.value = 0
    dut.bus_addr.value = 15
    dut.bus_data.value = 0
    dut.bus_write.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.host_read.value) == int(dut.bus_read.value) == 0
    await FallingEdge(dut.clk)
    dut.host_write.value = 1
    dut.host_data.value = 0xA5
    dut.bus_write.value = 1
    dut.bus_data.value = 0x5A
    await RisingEdge(dut.clk)
    await FallingEdge(dut.clk)
    dut.host_write.value = dut.bus_write.value = 0
    dut.host_addr.value = 15
    dut.bus_addr.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.host_read.value) == 0x5A
    assert int(dut.bus_read.value) == 0xA5
