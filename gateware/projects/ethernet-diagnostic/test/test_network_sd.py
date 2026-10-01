import sys
import os
import zlib
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from packet_support import packet, udp


def framed(data):
    wire = bytearray([0x7e])
    for byte in data:
        wire.extend((0x7d, byte ^ 0x20) if byte in (0x7d, 0x7e) else (byte,))
    return bytes(wire + b"\x7e")


async def uart_send(d, data, bit_ns=80):
    for byte in data:
        for bit in [0] + [(byte >> n) & 1 for n in range(8)] + [1]:
            d.usb_rx.value = bit
            await Timer(bit_ns, units="ns")
    d.usb_rx.value = 1


async def uart_receive(d, bit_ns=80):
    frame = bytearray()
    collecting, escaped = False, False
    while True:
        await FallingEdge(d.usb_tx)
        await Timer(bit_ns * 1.5, units="ns")
        byte = 0
        for bit in range(8):
            byte |= int(d.usb_tx.value) << bit
            await Timer(bit_ns, units="ns")
        assert int(d.usb_tx.value), "UART stop bit"
        assert int(d.usb_active.value), "binary ownership must cover the final stop bit"
        # Sample again just before the stop bit ends, including the closing
        # delimiter of a rejected frame. Releasing at its midpoint truncates
        # the physical reply when board.v switches back to the BIOS UART.
        await Timer(bit_ns * 0.5 - 1, units="ns")
        assert int(d.usb_tx.value), "UART stop bit must remain high in full"
        assert int(d.usb_active.value), "TX ownership must last through the whole stop bit"
        await Timer(1, units="ns")
        if byte == 0x7e:
            if collecting and frame:
                assert not escaped
                return bytes(frame)
            collecting, escaped = True, False
        elif collecting:
            if escaped:
                assert byte in (0x5e, 0x5d)
                frame.append(byte ^ 0x20)
                escaped = False
            elif byte == 0x7d:
                escaped = True
            else:
                frame.append(byte)


async def usb_exchange(d, request, status=0, *, bit_ns=80):
    receiver = cocotb.start_soon(uart_receive(d, bit_ns))
    await uart_send(d, framed(request), bit_ns)
    response = await with_timeout(receiver, 20000, "us")
    assert response[:4] == b"RBA1"
    assert response[4] == request[4] and response[5] == status
    assert zlib.crc32(response[:-4]) == int.from_bytes(response[-4:], "little")
    await Timer(1000, units="ns")
    return response

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "microsd-emulator/test"))
from ddr_support import memory_model
from sd_support import Host
from sd_support import send_packet


@cocotb.test()
async def ethernet_sd_ethernet_roundtrip(d):
    for name, period in [("clk", 10), ("rx_clk", 40), ("tx_clk", 40)]:
        cocotb.start_soon(Clock(getattr(d, name), period, units="ns").start())
    d.rst.value = 1
    d.initialized.value = 1
    d.writable.value = 1
    d.fast_mode.value = int(os.environ.get("MICROSD_FAST_MODE", "1"))
    d.h700_mode.value = 0
    d.mmc_only.value = 0
    # The writable card's CSD now comes from the build, so the
    # testbench has to supply the qualified default.
    d.sd_csd.value = 0x0026001A115903FFC002800002400023
    d.dat_in.value = 15
    d.uart_bit_time.value = 8
    d.usb_rx.value = 1
    d.diagnostic_status.value = 0
    d.sd_clk.value = 0
    d.cmd_in.value = 1
    d.eth_rxd.value = 0
    d.eth_rx_dv.value = 0
    d.eth_rxerr.value = 0
    d.ddr_cmd_ready.value = 0
    d.ddr_wdata_ready.value = 0
    d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    await Timer(200, units="ns")
    d.rst.value = 0
    await FallingEdge(d.clk)
    d.network_frontend_0.startup.value = 19_999_990
    await Timer(1000, units="ns")

    async def check_ownership():
        previous_owner = False
        while True:
            await FallingEdge(d.clk)
            owner = bool(d.network_owner.value)
            if owner and not previous_owner:
                assert int(d.native_stage_empty.value)
            previous_owner = owner
            if owner:
                assert not int(d.frontend_armed.value)
                assert not int(d.write_busy.value)
                assert not int(d.read_pending.value)

    cocotb.start_soon(check_ownership())
    memory = {}
    allow = [True]

    class ReadyGate:
        def __init__(self, handle):
            self.handle = handle

        @property
        def value(self):
            return self.handle.value

        @value.setter
        def value(self, value):
            self.handle.value = value if allow[0] else 0

    class MemoryPort:
        ddr_cmd_ready = ReadyGate(d.ddr_cmd_ready)
        ddr_wdata_ready = ReadyGate(d.ddr_wdata_ready)

        def __getattr__(self, name):
            return getattr(d, name)

    model = cocotb.start_soon(memory_model(MemoryPort(), memory))

    async def receive():
        nibbles = []
        while True:
            await RisingEdge(d.tx_clk)
            if int(d.eth_tx_en.value):
                nibbles.append(int(d.eth_txd.value))
            elif nibbles:
                break
        wire = bytes(
            nibbles[i] | nibbles[i + 1] << 4 for i in range(0, len(nibbles), 2)
        )
        assert wire[:8] == b"\x55" * 7 + b"\xd5"
        body = wire[8:-4]
        assert zlib.crc32(body) == int.from_bytes(wire[-4:], "little")
        assert body[12:14] == b"\x08\0" and body[23] == 17
        reply = body[42:]
        assert reply[:4] == b"RBA1"
        assert zlib.crc32(reply[:-4]) == int.from_bytes(reply[-4:], "little")
        return reply

    async def send(request):
        body = udp(request)
        wire = b"\x55" * 7 + b"\xd5" + body + zlib.crc32(body).to_bytes(4, "little")
        for byte in wire:
            for nibble in (byte & 15, byte >> 4):
                await FallingEdge(d.rx_clk)
                d.eth_rx_dv.value = 1
                d.eth_rxd.value = nibble
        await FallingEdge(d.rx_clk)
        d.eth_rx_dv.value = 0

    async def exchange(request, status=0):
        receiver = cocotb.start_soon(receive())
        await send(request)
        reply = await with_timeout(receiver, 1000, "us")
        assert reply[5] == status, (reply[5], status)
        await Timer(1000, units="ns")
        return reply

    first = bytes((i * 31 + 7) & 255 for i in range(512))
    await exchange(packet(1, 0, count=2))
    request = packet(2, 1, count=1, data=first)
    ack = await usb_exchange(d, request)
    # The Ethernet retry uses the shared cache and must not write twice.
    assert await exchange(request) == ack
    await exchange(packet(2, 2, lba=1, count=1, data=first[::-1]))
    await exchange(packet(4, 3))
    assert int(d.armed_status.value)
    os.environ["MICROSD_FAST_MODE"] = "1"
    host = Host(d)
    host.half_ns = 39
    await host.init(writable=True)
    await host.command(55, 0x10000)
    await host.command(6, 2)
    await host.command(17, 0)
    assert await host.data(wide=True) == first
    await host.command(24, 0)
    changed = await send_packet(host, True, 93)
    await host.command(17, 0)
    assert await host.data(wide=True) == changed
    snapshot = dict(memory)
    await exchange(packet(2, 4, lba=2, count=1, data=first), 4)
    assert memory == snapshot
    await exchange(packet(5, 5))
    assert not int(d.armed_status.value)
    reply = await exchange(packet(3, 6, count=1))
    assert reply[24:536] == changed
    reply = await exchange(packet(3, 7, lba=1, count=1))
    assert reply[24:536] == first[::-1]
    assert memory == snapshot
    # Disarm after accepting an SD packet while DDR is deliberately stalled.
    # Network reads must be refused until that accepted write drains.
    await exchange(packet(4, 8))
    await host.init(writable=True)
    await host.command(55, 0x10000)
    await host.command(6, 2)
    allow[0] = False
    await host.command(24, 512)
    pending = await send_packet(host, True, 117, wait_complete=False)
    assert int(d.write_busy.value)
    await exchange(packet(5, 9))
    await exchange(packet(3, 10, lba=1, count=1), 4)
    assert memory == snapshot
    allow[0] = True
    await Timer(100000, units="ns")
    reply = await exchange(packet(3, 11, lba=1, count=1))
    assert reply[24:536] == pending
    assert all(memory.get(i) == snapshot.get(i) for i in range(32))
    compact = packet(7, 900, count=2)[:24]
    compact += zlib.crc32(compact).to_bytes(4, "little")
    bulk = await exchange(compact)
    assert bulk[24:-4] == changed + pending
    again = await exchange(packet(7, 2, count=2))
    assert again[24:-4] == changed + pending
    await exchange(packet(7, 1000, lba=524287, count=2), 5)
    assert all(memory.get(i) == snapshot.get(i) for i in range(32))

    async def collect():
        return [await receive() for _ in range(8)]

    collector = cocotb.start_soon(collect())
    for n in range(8):
        request = packet(7, 501 + n, lba=n % 2, count=2 if n % 2 == 0 else 1)
        if n % 3 != 0:
            request = request[:24]
            request += zlib.crc32(request).to_bytes(4, "little")
        await send(request)
        await Timer(1000, units="ns")
    burst = await with_timeout(collector, 4000, "us")
    assert [int.from_bytes(x[12:16], "little") for x in burst] == list(range(501, 509))
    for n, response in enumerate(burst):
        assert response[24:-4] == (changed + pending if n % 2 == 0 else pending)
    # An SD read already admitted to the DDR stage must also drain after DISARM.
    await exchange(packet(4, 12))
    await host.init(writable=True)
    allow[0] = False
    before_read = dict(memory)
    await host.command(17, 0)
    await Timer(1000, units="ns")
    assert int(d.read_pending.value)
    await exchange(packet(5, 13))
    await exchange(packet(3, 14, count=1), 4)
    assert not int(d.network_owner.value)
    allow[0] = True
    await Timer(100000, units="ns")
    reply = await exchange(packet(3, 15, count=1))
    assert reply[24:536] == changed
    assert memory == before_read
    model.kill()


@cocotb.test()
async def usb_info_with_absent_phy_clocks_and_uninitialized_ddr(d):
    # A 64 MHz period is 15625 ps; its half-period needs alternating
    # integer delays at Verilator's 1 ps precision.
    async def fabric_clock():
        while True:
            d.clk.value = 0
            await Timer(7812, units="ps")
            d.clk.value = 1
            await Timer(7813, units="ps")
    cocotb.start_soon(fabric_clock())
    for name in ("rx_clk", "tx_clk", "initialized", "diagnostic_status",
                 "fast_mode", "h700_mode", "h700_falling_phase", "h700_early_command",
                 "sd_csd", "capture_lba", "mmc_only", "writable", "sd_clk",
                 "eth_rxd", "eth_rx_dv", "eth_rxerr", "ddr_cmd_ready",
                 "ddr_wdata_ready", "ddr_rdata_valid", "ddr_rdata"):
        getattr(d, name).value = 0
    d.uart_bit_time.value = 64
    d.usb_rx.value, d.cmd_in.value, d.dat_in.value = 1, 1, 15
    d.rst.value = 1
    await Timer(100, units="ns")
    d.rst.value = 0
    head = packet(9, 0, session=0)[:24]
    query = head + zlib.crc32(head).to_bytes(4, "little")
    corrupt = query[:-1] + bytes([query[-1] ^ 1])
    await usb_exchange(d, corrupt, status=1, bit_ns=1000)
    assert not int(d.usb_active.value), "bad CRC must release the BIOS console"
    result = await usb_exchange(d, query, bit_ns=1000)
    assert result[24:28] == b"RBI1"
    assert int.from_bytes(result[48:52], "little") & 3 == 0
    assert int(d.usb_active.value)
    # Once a recognized reply claims binary mode, later rejected frames
    # must leave it active. Test rejection both before and after INFO.
    await usb_exchange(d, corrupt, status=1, bit_ns=1000)
    assert int(d.usb_active.value), "bad CRC must retain an established binary session"
    assert not int(d.armed_status.value)
    assert not int(d.ddr_cmd_valid.value)
