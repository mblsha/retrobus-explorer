import sys
import os
import zlib
from pathlib import Path
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer, with_timeout
from test_blocks import packet
from test_network import udp

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "microsd-emulator/test"))
from test_ddr_integration import memory_model
from test_sd import Host
from test_sd_write import send_packet


@cocotb.test()
async def ethernet_sd_ethernet_roundtrip(d):
    for name, period in [("clk", 10), ("rx_clk", 40), ("tx_clk", 40)]:
        cocotb.start_soon(Clock(getattr(d, name), period, units="ns").start())
    d.rst.value = 1
    d.initialized.value = 1
    d.writable.value = 1
    d.dat_in.value = 15
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
                assert int(d.client_idle.value)
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
    ack = await exchange(request)
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
    model.kill()
