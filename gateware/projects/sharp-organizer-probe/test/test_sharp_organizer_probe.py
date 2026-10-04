"""UART integration and fail-released pin behavior of the Au1 card probe."""

import cocotb
from cocotb.triggers import FallingEdge, Timer

from cocotb_helpers import start_clock, tick


BIT_NS = 1000


async def send_byte(dut, byte):
    dut.usb_rx.value = 0
    await Timer(BIT_NS, units="ns")
    for bit in range(8):
        dut.usb_rx.value = (byte >> bit) & 1
        await Timer(BIT_NS, units="ns")
    dut.usb_rx.value = 1
    await Timer(BIT_NS, units="ns")


async def receive_byte(dut):
    await FallingEdge(dut.usb_tx)
    await Timer(BIT_NS + BIT_NS // 2, units="ns")
    value = 0
    for bit in range(8):
        value |= int(dut.usb_tx.value) << bit
        await Timer(BIT_NS, units="ns")
    assert int(dut.usb_tx.value) == 1
    return value


async def command(dut, payload, response_len):
    async def collect():
        return bytes([await receive_byte(dut) for _ in range(response_len)])

    response = cocotb.start_soon(collect())
    await Timer(1, units="ns")
    for byte in payload:
        await send_byte(dut, byte)
    return await response


async def initialize(dut):
    start_clock(dut.clk)
    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.addr_host.value = 0x12345
    dut.data_host.value = 0xA6
    dut.control_host.value = 0x82
    dut.protected_host.value = 0x35
    dut.data.value = 0
    dut.conn_stnby.value = 0
    dut.conn_vbatt.value = 0
    dut.conn_vpp.value = 0
    dut.conn_nc02.value = 0
    dut.conn_nc42.value = 0
    dut.conn_nc43.value = 0
    dut.conn_nc44.value = 0
    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 10)


def released(dut):
    assert int(dut.addr_oe_debug.value) == 0
    assert int(dut.data_oe_debug.value) == 0
    assert int(dut.control_oe_debug.value) == 0
    assert int(dut.armed_debug.value) == 0


@cocotb.test()
async def uart_probe_and_watchdog(dut):
    await initialize(dut)
    released(dut)
    assert await command(dut, b"I", 5) == b"OBP3\n"
    snap = await command(dut, b"?", 16)
    assert snap == bytes.fromhex("53 01 23 45 a6 82 35 00 00 00 00 00 00 00 00 00")
    assert await command(dut, b"A\x01\x23\x45\x0f\xff\xff", 1) == b"!"
    released(dut)
    assert await command(dut, b"UREAX", 1) == b"!"
    released(dut)

    assert await command(dut, b"UREAD", 1) == b"U"
    assert int(dut.armed_debug.value) == 1
    assert await command(dut, b"A\x01\x23\x45\x0f\xff\xff", 1) == b"A"
    assert int(dut.addr_drive_debug.value) == 0x12345
    assert int(dut.addr_oe_debug.value) == 0xFFFFF
    assert await command(dut, b"C\x82\x82", 1) == b"C"
    assert int(dut.control_drive_debug.value) == 0x82
    assert int(dut.control_oe_debug.value) == 0x82
    snap = await command(dut, b"?", 16)
    assert snap[0] == ord("S") and snap[1:7] == bytes.fromhex("01 23 45 a6 82 35")
    assert snap[7:16] == bytes.fromhex("01 23 45 0f ff ff 82 82 01")
    assert await command(dut, b"Z", 1) == b"Z"
    released(dut)

    assert await command(dut, b"UREAD", 1) == b"U"
    assert await command(dut, b"A\x00\x01\x23\x0f\xff\xff", 1) == b"A"
    assert int(dut.addr_oe_debug.value) == 0xFFFFF
    await Timer(510000, units="ns")
    released(dut)


@cocotb.test()
async def burst_reads_sequential_addresses_and_releases(dut):
    await initialize(dut)

    async def card_rom():
        while True:
            dut.data_host.value = (int(dut.addr_drive_debug.value) ^ 0x5A) & 0xFF
            await Timer(100, units="ns")

    model = cocotb.start_soon(card_rom())
    assert await command(dut, b"R\x00\x01\x20\x00\x08\xff\x7d\xff", 1) == b"!"
    released(dut)
    assert await command(dut, b"UREAD", 1) == b"U"
    response = await command(dut, b"R\x00\x01\x20\x00\x08\xff\x7d\xff", 9)
    assert response == b"R" + bytes(((0x120 + i) ^ 0x5A) & 0xFF for i in range(8))
    await tick(dut.clk, 4)
    released(dut)
    model.kill()


@cocotb.test()
async def bounded_sram_write_never_selects_rom_or_enables_oe(dut):
    await initialize(dut)
    assert await command(dut, b"W\x00\x7f\xff\x5a\x02", 1) == b"!"
    released(dut)
    assert await command(dut, b"UREAD", 1) == b"U"
    assert await command(dut, b"W\x00\x7f\xff\x5a\x03", 1) == b"!"
    released(dut)

    assert await command(dut, b"UREAD", 1) == b"U"
    samples = []

    async def watch_write():
        while True:
            samples.append((
                int(dut.addr_drive_debug.value),
                int(dut.data_drive_debug.value),
                int(dut.data_oe_debug.value),
                int(dut.control_drive_debug.value),
                int(dut.control_oe_debug.value),
            ))
            await Timer(100, units="ns")

    monitor = cocotb.start_soon(watch_write())
    assert await command(dut, b"W\x00\x7f\xff\x5a\x02", 1) == b"W"
    monitor.kill()
    await tick(dut.clk, 4)
    released(dut)
    driven = [sample for sample in samples if sample[2]]
    assert driven
    assert all(addr == 0x7fff and data == 0x5a and mask == 0xff
               for addr, data, _, _, mask in driven)
    assert all(control & 0x9e == 0x9e for _, _, _, control, _ in driven)
    assert any(control == 0xbe for _, _, _, control, _ in driven)
    assert all(control in (0xff, 0xbf, 0xbe) for _, _, _, control, _ in driven)
