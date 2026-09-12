import cocotb
from cocotb.triggers import FallingEdge, Timer, with_timeout
from cocotb_helpers import start_clock, tick
from microsd_image import packet, decode_ack


async def receive(d):
    data = bytearray()
    for _ in range(16):
        await with_timeout(FallingEdge(d.usb_tx), 6000, "us")
        await Timer(1500, units="ns")
        value = 0
        for bit in range(8):
            value |= int(d.usb_tx.value) << bit
            await Timer(1000, units="ns")
        assert int(d.usb_tx.value)
        data.append(value)
    return decode_ack(bytes(data))


@cocotb.test()
async def uart_image_packet_reaches_validated_loader(d):
    start_clock(d.clk)
    d.rst_n.value = 0
    d.usb_rx.value = 1
    d.sd_clk.value = 1
    d.cmd_in.value = 1
    await tick(d.clk, 10)
    d.rst_n.value = 1
    await tick(d.clk, 10)
    task = cocotb.start_soon(receive(d))
    raw = packet(1, 0, 312, bytes((i * 7) & 255 for i in range(512)))
    for byte in raw:
        for bit in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
            d.usb_rx.value = bit
            await Timer(1000, units="ns")
    assert await task == (1, 0, 312)
    assert (
        not int(d.armed_status.value)
        and not int(d.cmd_oe.value)
        and not int(d.dat_oe.value)
    )
