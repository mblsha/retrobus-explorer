"""Pin-level bus, UART protocol and physical FT245 interface integration."""

import struct
from functools import reduce
from operator import xor
import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from cocotb_helpers import start_clock, tick

BIT_NS = 250


async def send_byte(dut, value):
    dut.usb_rx.value = 0
    await Timer(BIT_NS, units="ns")
    for bit in range(8):
        dut.usb_rx.value = (value >> bit) & 1
        await Timer(BIT_NS, units="ns")
    dut.usb_rx.value = 1
    await Timer(BIT_NS, units="ns")


async def receive_byte(dut):
    await FallingEdge(dut.usb_tx)
    await Timer(BIT_NS * 1.5, units="ns")
    result = 0
    for bit in range(8):
        result |= int(dut.usb_tx.value) << bit
        await Timer(BIT_NS, units="ns")
    assert int(dut.usb_tx.value) == 1
    return result


async def command(dut, op, address=0, arg0=0, arg1=0, arg2=0, status=0, corrupt=False):
    request = bytes([0xA5, ord(op), address & 255, address >> 8, arg0, arg1, arg2])
    request += bytes([reduce(xor, request) ^ int(corrupt)])

    async def collect():
        return bytes([await receive_byte(dut) for _ in range(16)])

    task = cocotb.start_soon(collect())
    await Timer(1, units="ns")
    for value in request:
        await send_byte(dut, value)
    result = await with_timeout(task, 100, "us")
    assert result[:3] == bytes([0xD5, ord(op), status]), result.hex()
    assert reduce(xor, result) == 0, result.hex()
    return result[3:15]


async def initialize(dut):
    start_clock(dut.clk)
    start_clock(dut.ft_clk)
    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    dut.ft_host_drive.value = 0
    dut.ft_data_host.value = 0
    dut.ft_be_host.value = 3
    dut.addr.value = 0
    dut.data_host.value = 0
    dut.data_host_drive.value = 0
    for name in (
        "conn_rw",
        "conn_oe",
        "conn_ci",
        "conn_e2",
        "conn_mskrom",
        "conn_sram1",
        "conn_sram2",
        "conn_eprom",
    ):
        getattr(dut, name).value = 1
    for name in (
        "conn_stnby",
        "conn_vbatt",
        "conn_vpp",
        "conn_nc02",
        "conn_nc42",
        "conn_nc43",
        "conn_nc44",
    ):
        getattr(dut, name).value = 0
    await tick(dut.clk, 10)
    dut.rst_n.value = 1
    await tick(dut.clk, 10)


async def arm(dut):
    await command(dut, "V", 0x5241, 0x4D, 0x21)
    await command(dut, "A", 0x5241, 0x4D, 0x21)
    assert int(dut.armed_debug.value) == 1


async def release(dut):
    dut.conn_eprom.value = 1
    dut.conn_sram2.value = 1
    dut.conn_rw.value = 1
    dut.conn_oe.value = 1
    dut.data_host_drive.value = 0
    await tick(dut.clk, 5)
    assert int(dut.data_oe_debug.value) == 0


async def read_bus(dut, address, ram=False, duration=25):
    dut.addr.value = address
    dut.conn_rw.value = 1
    dut.conn_oe.value = 0
    dut.conn_sram2.value = int(not ram)
    dut.conn_eprom.value = int(ram)
    await tick(dut.clk, duration)
    assert int(dut.data_oe_debug.value) == 1
    value = int(dut.data.value)
    await release(dut)
    return value


async def write_bus(dut, address, data, ram=False, duration=25):
    dut.addr.value = address
    dut.conn_oe.value = 1
    dut.conn_rw.value = 0
    dut.data_host.value = data
    dut.data_host_drive.value = 1
    dut.conn_sram2.value = int(not ram)
    dut.conn_eprom.value = int(ram)
    await tick(dut.clk, duration)
    assert int(dut.data_oe_debug.value) == 0
    await release(dut)


async def ft_send(dut, words):
    index = 0
    dut.ft_host_drive.value = 1
    dut.ft_rxf.value = 0
    dut.ft_data_host.value, dut.ft_be_host.value = words[0]
    for _ in range(200000):
        await FallingEdge(dut.ft_clk)
        taking = int(dut.ft_rd.value) == 0 and int(dut.ft_oe.value) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ns")
        if taking:
            index += 1
            if index == len(words):
                dut.ft_rxf.value = 1
                dut.ft_host_drive.value = 0
                return
            dut.ft_data_host.value, dut.ft_be_host.value = words[index]
    raise AssertionError("FT input did not drain")


async def ft_collect(dut, records):
    words = []
    for _ in range(100000):
        await FallingEdge(dut.ft_clk)
        taking = int(dut.ft_wr.value) == 0 and int(dut.ft_oe.value) == 1
        word = int(dut.ft_data.value)
        be = int(dut.ft_be.value)
        await RisingEdge(dut.ft_clk)
        if taking:
            assert be == 3
            words.append(word)
            if len(words) == records * 8:
                return list(
                    struct.iter_unpack(
                        "<IIII", struct.pack("<" + "H" * len(words), *words)
                    )
                )
    raise AssertionError(f"Only {len(words)} FT words received")


@cocotb.test()
async def uart_memory_boundaries_and_release(dut):
    await initialize(dut)
    assert int(dut.data_oe_debug.value) == 0
    assert (await command(dut, "I"))[:4] == b"OEM1"
    await command(dut, "A", 0x5241, 0x4D, 0x21, status=4)
    for address, byte in [(0, 0xA5), (0x3FFF, 0x7E), (0x8000, 0x12), (0x87FF, 0x34)]:
        await command(dut, "W", address, byte)
        assert (await command(dut, "R", address))[0] == byte
    await command(dut, "W", 0x4000, 0xFF, status=2)
    await command(dut, "R", 0x8800, status=2)
    await command(dut, "W", 0, 0xFF, corrupt=True, status=1)
    assert (await command(dut, "R", 0))[0] == 0xA5
    await command(dut, "?", status=5)
    await arm(dut)
    assert await read_bus(dut, 0x40000) == 0xA5
    assert await read_bus(dut, 0x5FFFF) == 0x7E
    assert await read_bus(dut, 0x807FF, ram=True) == 0x34
    await command(dut, "Z")
    assert int(dut.armed_debug.value) == 0
    dut.conn_eprom.value = 0
    dut.conn_oe.value = 0
    await tick(dut.clk, 20)
    assert int(dut.data_oe_debug.value) == 0


@cocotb.test()
async def asynchronous_turnaround_and_held_select_address(dut):
    await initialize(dut)
    await command(dut, "W", 0x100, 0x81)
    await command(dut, "W", 0x101, 0x42)
    await arm(dut)
    for phase in range(10):
        await FallingEdge(dut.clk)
        await Timer(phase + 1, units="ns")
        dut.addr.value = 0x40100
        dut.conn_eprom.value = 0
        dut.conn_oe.value = 0
        await tick(dut.clk, 15)
        assert int(dut.data.value) == 0x81
        dut.addr.value = 0x40101
        await Timer(1, units="ns")
        assert int(dut.data_oe_debug.value) == 0
        await tick(dut.clk, 15)
        assert int(dut.data.value) == 0x42
        dut.conn_rw.value = 0
        await Timer(1, units="ns")
        assert int(dut.data_oe_debug.value) == 0
        await release(dut)
    dut.conn_mskrom.value = 0
    dut.conn_oe.value = 0
    await tick(dut.clk, 20)
    assert int(dut.data_oe_debug.value) == 0
    dut.conn_mskrom.value = 1
    await release(dut)
    dut.conn_eprom.value = 0
    dut.conn_oe.value = 0
    await tick(dut.clk, 20)
    dut.rst_n.value = 0
    await Timer(1, units="ns")
    assert int(dut.data_oe_debug.value) == 0


@cocotb.test()
async def sram_writes_idle_guard_and_live_timing(dut):
    await initialize(dut)
    await command(dut, "F", arg0=6, arg1=0x80)
    await arm(dut)
    await write_bus(dut, 0x80004, 0x11, ram=True)
    assert await read_bus(dut, 0x80004, ram=True) == 0x11
    await write_bus(dut, 0x80004, 0x99, ram=True, duration=3)
    assert await read_bus(dut, 0x80004, ram=True) == 0x11
    await command(dut, "W", 0x0400, 0x55, status=3)
    await write_bus(dut, 0x43FF5, 0)
    await command(dut, "W", 0x0400, 0x55)
    await command(dut, "W", 0x0100, 0x55, status=3)
    await command(dut, "W", 0x3FDF, 1)
    # Upload guard closes on commit, even before the CPU emits STATE=busy.
    await command(dut, "W", 0x0400, 0x66, status=3)
    await write_bus(dut, 0x43FF5, 1)
    await command(dut, "W", 0x0400, 0x66, status=3)
    await command(dut, "T", arg0=255, arg1=255)
    dut.addr.value = 0x80006
    dut.conn_sram2.value = 0
    dut.conn_rw.value = 0
    dut.data_host_drive.value = 1
    dut.data_host.value = 0xA6
    await tick(dut.clk, 5)
    await release(dut)
    change = cocotb.start_soon(command(dut, "T", arg0=0, arg1=0))
    # Start the bus during the last UART byte. The new timing arrives while
    # the long old write window is active, then we end it before 255 clocks.
    await Timer(19000, units="ns")
    dut.addr.value = 0x80006
    dut.conn_sram2.value = 0
    dut.conn_rw.value = 0
    dut.data_host_drive.value = 1
    dut.data_host.value = 0xA6
    await Timer(1800, units="ns")
    await release(dut)
    await change
    assert (await command(dut, "R", 0x8006))[0] == 0
    await write_bus(dut, 0x80006, 0x44, ram=True, duration=8)
    assert await read_bus(dut, 0x80006, ram=True) == 0x44


@cocotb.test()
async def ft_input_byte_enables_and_held_read_consumption(dut):
    await initialize(dut)
    await command(dut, "F", arg0=6, arg1=0x80)
    await arm(dut)
    await ft_send(dut, [(0x2211, 3), (0x9933, 1), (0x4499, 2), (0xBEEF, 0)])
    await tick(dut.clk, 30)
    assert await read_bus(dut, 0x43FF7) == 1
    assert await read_bus(dut, 0x43FF8, duration=100) == 0x11
    assert await read_bus(dut, 0x43FF8) == 0x22
    assert await read_bus(dut, 0x43FF8) == 0x33
    assert await read_bus(dut, 0x43FF8) == 0x44
    assert await read_bus(dut, 0x43FF7) == 0
    assert await read_bus(dut, 0x43FF8) == 0
    assert struct.unpack("<III", await command(dut, "S", 1))[2] == 1


@cocotb.test()
async def ft_trace_coherent_records_backpressure_and_drops(dut):
    await initialize(dut)
    await command(dut, "W", 0x234, 0x69)
    await command(dut, "F", arg0=7, arg1=0x80)
    await arm(dut)
    dut.conn_nc42.value = 1
    assert await read_bus(dut, 0x40234) == 0x69
    await write_bus(dut, 0x43FF1, 0x41)
    await tick(dut.clk, 30)
    dut.ft_txe.value = 0
    rows = await ft_collect(dut, 2)
    assert [row[0] for row in rows] == [0xE7010000, 0xE7010001]
    assert rows[1][1] > rows[0][1]
    assert rows[0][2] & 0xFFFFF == 0x40234
    assert rows[0][2] >> 28 == 1
    assert rows[0][3] & 255 == 0x69
    assert rows[0][3] & 0x1000
    assert rows[1][2] >> 28 == 3 and rows[1][3] & 255 == 0x41
    dut.ft_txe.value = 1
    await tick(dut.clk, 20)
    for index in range(1500):
        await write_bus(dut, 0x80100 + index, index & 255, ram=True, duration=18)
    sequence, drops, _ = struct.unpack("<III", await command(dut, "S", 1))
    assert sequence == 1502 and drops > 0
    await write_bus(dut, 0x43FF4, 0)
    assert (await command(dut, "S"))[3] == 6
    await write_bus(dut, 0x80002, 0x42, ram=True)
    assert struct.unpack("<III", await command(dut, "S", 1))[0] == 1503
    await command(dut, "Z")
    assert int(dut.armed_debug.value) == 0


@cocotb.test()
async def ft_receive_backpressure_and_bidirectional_service(dut):
    await initialize(dut)
    await command(dut, "F", arg0=6, arg1=0x80)
    await arm(dut)
    await write_bus(dut, 0x43FF1, 0x77)
    # More input than both RX queues can hold. FIFO fullness must stop FT RD,
    # and the waiting outbound record must still get serviced.
    words = [(index ^ 0x5A00, 3) for index in range(800)]
    feed = cocotb.start_soon(ft_send(dut, words))
    dut.ft_txe.value = 0
    collect = cocotb.start_soon(ft_collect(dut, 1))
    await tick(dut.clk, 4000)
    assert not feed.done()
    assert int(dut.ft_rd.value) == 1
    rows = await collect
    assert rows[0][3] & 255 == 0x77
    for word, _ in words:
        assert await read_bus(dut, 0x43FF8) == word & 255
        assert await read_bus(dut, 0x43FF8) == word >> 8
    await feed
    assert await read_bus(dut, 0x43FF7) == 0


@cocotb.test()
async def partial_uart_timeout_keeps_emulation_active(dut):
    await initialize(dut)
    await command(dut, "W", 0x0000, 0x5A)
    await arm(dut)
    for byte in (0xA5, ord("W"), 0x00):
        await send_byte(dut, byte)
    await Timer(10_100_000, units="ns")
    assert int(dut.armed_debug.value) == 1
    assert (await command(dut, "R", 0))[0] == 0x5A
    assert await read_bus(dut, 0x40000) == 0x5A
