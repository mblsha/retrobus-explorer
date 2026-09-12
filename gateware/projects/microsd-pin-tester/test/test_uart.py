import cocotb
from cocotb.triggers import FallingEdge, Timer, with_timeout
from cocotb_helpers import start_clock, tick
from microsd_probe import request, decode


async def transmit(dut, packet):
    for byte in packet:
        for bit in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
            dut.usb_rx.value = bit
            await Timer(1000, units="ns")
    dut.usb_rx.value = 1


async def receive(dut):
    result = bytearray()
    for _ in range(64):
        await with_timeout(FallingEdge(dut.usb_tx), 100, "us")
        await Timer(1500, units="ns")
        byte = 0
        for i in range(8):
            byte |= int(dut.usb_tx.value) << i
            await Timer(1000, units="ns")
        assert int(dut.usb_tx.value) == 1, "UART stop bit"
        result.append(byte)
    return decode(bytes(result))


@cocotb.test()
async def serial_end_to_end_both_profiles(dut):
    start_clock(dut.clk)
    dut.usb_rx.value = 1
    dut.pmod.value = 0xA5
    dut.top_header.value = 0
    dut.rst_n.value = 0
    await tick(dut.clk, 10)
    dut.rst_n.value = 1
    await tick(dut.clk, 20)
    for profile in (0, 1, 2):
        dut.top_header.value = profile
        receiving = cocotb.start_soon(receive(dut))
        await transmit(dut, request(1, 42 + profile))
        result = await receiving
        assert result["sequence"] == 42 + profile
        assert result["raw_levels"] == 0xA5
        assert (
            result["profile"]
            == ("bottom-header", "top-header-r180", "bottom-header-row-swap")[profile]
        )
        await Timer(2000, units="ns")
