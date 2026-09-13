import zlib
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


def frame(body):
    body = body.ljust(60, b"\0")
    return b"\x55" * 7 + b"\xd5" + body + zlib.crc32(body).to_bytes(4, "little")


async def exercise_mailbox(dut, phase_ns=0):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    receive = hasattr(dut, "rx_clk")
    phy_clock = dut.rx_clk if receive else dut.tx_clk
    async def start_phy():
        if phase_ns:
            await Timer(phase_ns, units="ns")
        await Clock(phy_clock, 40, units="ns").start()

    cocotb.start_soon(start_phy())
    dut.rst.value = 1
    dut.address.value = 0
    if receive:
        dut.consume.value = 0
        dut.dv.value = 0
        dut.er.value = 0
        dut.rxd.value = 0
    else:
        dut.write.value = 0
        dut.data.value = 0
        dut.submit.value = 0
        dut.length.value = 0
    await Timer(160, units="ns")
    dut.rst.value = 0
    if receive:

        async def send(data, corrupt=False):
            wire = bytearray(frame(data))
            if corrupt:
                wire[-1] ^= 1
            for byte in wire:
                for nibble in (byte & 15, byte >> 4):
                    await FallingEdge(phy_clock)
                    dut.dv.value = 1
                    dut.rxd.value = nibble
            await FallingEdge(phy_clock)
            dut.dv.value = 0
            await Timer(300, units="ns")

        first = bytes(range(64))
        await send(first, True)
        assert not int(dut.available.value)
        await send(first)
        assert int(dut.available.value)
        queued = [bytes([n]) * 60 for n in range(1, 8)]
        for body in queued:
            await send(body)
        await send(b"overflow must drop")
        for expected in [first] + queued:
            assert int(dut.available.value)
            assert int(dut.frame_length.value) == len(expected)
            for i, value in enumerate(expected):
                await FallingEdge(dut.clk)
                dut.address.value = i
                await Timer(20, units="ns")
                assert int(dut.data.value) == value
            dut.consume.value = 1
            await Timer(10, units="ns")
            dut.consume.value = 0
            await Timer(200, units="ns")
        assert not int(dut.available.value)
        for n in range(8):
            await send(bytes([n + 17]) * 60)
        for n in range(8):
            assert int(dut.available.value)
            for i in range(60):
                await FallingEdge(dut.clk)
                dut.address.value = i
                await Timer(20, units="ns")
                assert int(dut.data.value) == n + 17
            dut.consume.value = 1
            await Timer(10, units="ns")
            dut.consume.value = 0
            await Timer(200, units="ns")
        assert not int(dut.available.value)
        await send(b"next frame")
        assert int(dut.available.value)
        assert int(dut.frame_length.value) == 60
    else:
        bodies = [
            b"short",
            bytes((i * 17) & 255 for i in range(1094)),
            b"third",
            bytes((i * 7) & 255 for i in range(1514)),
            b"fifth",
        ]

        async def monitor():
            received = []
            nibbles = []
            gap = 100
            for _ in range(20000):
                await RisingEdge(phy_clock)
                if int(dut.tx_en.value):
                    if not nibbles:
                        assert gap >= 24
                        gap = 0
                    nibbles.append(int(dut.txd.value))
                else:
                    gap += 1
                    if nibbles:
                        received.append(
                            bytes(
                                nibbles[i] | nibbles[i + 1] << 4
                                for i in range(0, len(nibbles), 2)
                            )
                        )
                        nibbles = []
                        if len(received) == len(bodies):
                            return received
            assert False, "TX queue timeout"

        capture = cocotb.start_soon(monitor())
        for body in bodies:
            while not int(dut.ready.value):
                await FallingEdge(dut.clk)
            for i, byte in enumerate(body):
                await FallingEdge(dut.clk)
                dut.write.value = 1
                dut.address.value = i
                dut.data.value = byte
            await FallingEdge(dut.clk)
            dut.write.value = 0
            dut.length.value = len(body)
            dut.submit.value = 1
            await FallingEdge(dut.clk)
            dut.submit.value = 0
            await FallingEdge(dut.clk)
        assert await capture == [frame(body) for body in bodies]


@cocotb.test()
async def mailbox_frames(dut):
    await exercise_mailbox(dut)


@cocotb.test()
async def mailbox_frames_offset_clock(dut):
    await exercise_mailbox(dut, phase_ns=7)


@cocotb.test()
async def reset_release_follows_each_phy_clock_phase(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    receive = hasattr(dut, "rx_clk")
    phy_clock = dut.rx_clk if receive else dut.tx_clk
    local_reset = dut.rx_reset if receive else dut.tx_reset
    phy_clock.value = 0
    dut.rst.value = 1
    dut.address.value = 0
    if receive:
        dut.consume.value = dut.dv.value = dut.er.value = dut.rxd.value = 0
    else:
        dut.write.value = dut.data.value = dut.submit.value = dut.length.value = 0

    # Deliberately stop the PHY clock during assertion, then run it while reset
    # is held. This is the startup contract, including a late-starting PHY clock.
    await Timer(113, units="ns")
    assert int(local_reset.value)
    clock_task = cocotb.start_soon(Clock(phy_clock, 40, units="ns").start())
    edge = RisingEdge if receive else FallingEdge
    for phase in (1, 7, 19, 39):
        dut.rst.value = 1
        await Timer(160, units="ns")
        await edge(phy_clock)
        await Timer(phase, units="ns")
        dut.rst.value = 0
        await Timer(1, units="ps")
        assert int(local_reset.value)
        await edge(phy_clock)
        await Timer(1, units="ps")
        assert int(local_reset.value)
        await edge(phy_clock)
        await Timer(1, units="ps")
        assert not int(local_reset.value)
        await Timer(160, units="ns")
        assert not int(dut.available.value if receive else dut.tx_en.value)
    clock_task.kill()
