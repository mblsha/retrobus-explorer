import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


def framed(data):
    wire = bytearray([0x7e])
    for byte in data:
        wire.extend((0x7d, byte ^ 0x20) if byte in (0x7d, 0x7e) else (byte,))
    return bytes(wire + b"\x7e")


@cocotb.test()
async def framing_recovery_and_buffered_reply(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    for name in ("rx_valid", "rx_byte", "tx_ready", "request_address",
                 "reply_write", "reply_address", "reply_data", "reply_done", "reply_length"):
        getattr(d, name).value = 0
    d.rst.value = 1
    await Timer(40, units="ns")
    d.rst.value = 0

    async def send(wire):
        for byte in wire:
            await FallingEdge(d.clk)
            d.rx_valid.value, d.rx_byte.value = 1, byte
            await FallingEdge(d.clk)
            d.rx_valid.value = 0
        await Timer(30, units="ns")

    # Noise, an unfinished escape, a malformed escape, and overflow all
    # recover at the next delimiter without exposing a partial request.
    await send(b"BIOS boot output")
    await send(b"\x7eabc\x7d\x7e")
    assert not int(d.request.value)
    await send(b"\x7eabc\x7d\x11\x7e")
    assert not int(d.request.value)
    await send(framed(bytes(541)))
    assert not int(d.request.value)
    await send(framed(bytes(540) + b"\x7e"))
    assert not int(d.request.value)
    body = bytes(range(256)) * 2 + bytes(range(28))
    await send(framed(body))
    assert int(d.request.value) and int(d.request_length.value) == 540
    assert int(d.active.value)
    # A second frame cannot overwrite the request held for the service.
    await send(framed(bytes(540)))
    actual = bytearray()
    for index in range(len(body)):
        d.request_address.value = index
        await Timer(30, units="ns")
        actual.append(int(d.request_data.value))
    assert bytes(actual) == body

    reply = bytes(range(256)) * 4 + bytes(range(28))
    for index, byte in enumerate(reply):
        await FallingEdge(d.clk)
        d.reply_write.value, d.reply_address.value, d.reply_data.value = 1, index, byte
    await FallingEdge(d.clk)
    d.reply_write.value = 0
    d.reply_length.value, d.reply_done.value = len(reply), 1
    await FallingEdge(d.clk)
    d.reply_done.value = 0
    output = bytearray()
    # Backpressure must hold a stable byte until accepted.
    for cycle in range(9000):
        await FallingEdge(d.clk)
        ready = cycle % 3 == 0
        d.tx_ready.value = int(ready)
        if ready and int(d.tx_valid.value):
            output.append(int(d.tx_byte.value))
        if bytes(output) == framed(reply):
            break
    else:
        assert False, "serial reply timeout"
    await Timer(50, units="ns")
    assert int(d.active.value), "recognized reply must retain binary ownership"
    assert not int(d.request.value)
    await send(framed(b"new packet"))
    assert int(d.request.value)
    d.rst.value = 1
    await Timer(30, units="ns")
    assert not int(d.request.value) and not int(d.active.value)


@cocotb.test()
async def rejected_frame_releases_console_after_error_reply(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    for name in ("rx_valid", "rx_byte", "tx_ready", "request_address",
                 "reply_write", "reply_address", "reply_data", "reply_done", "reply_length"):
        getattr(d, name).value = 0
    d.rst.value = 1
    await Timer(40, units="ns")
    d.rst.value = 0
    assert not int(d.active.value)
    for byte in framed(b"stray terminal frame"):
        await FallingEdge(d.clk)
        d.rx_valid.value, d.rx_byte.value = 1, byte
        await FallingEdge(d.clk)
        d.rx_valid.value = 0
    await Timer(30, units="ns")
    assert int(d.request.value) and int(d.active.value)
    reply = b"RBA1\x09\x01" + bytes(534)
    for index, byte in enumerate(reply):
        await FallingEdge(d.clk)
        d.reply_write.value, d.reply_address.value, d.reply_data.value = 1, index, byte
    await FallingEdge(d.clk)
    d.reply_write.value = 0
    d.reply_length.value, d.reply_done.value = len(reply), 1
    await FallingEdge(d.clk)
    d.reply_done.value = 0
    output = bytearray()
    for cycle in range(9000):
        await FallingEdge(d.clk)
        ready = cycle % 3 == 0
        d.tx_ready.value = int(ready)
        assert int(d.active.value), "temporary TX ownership must cover the entire error frame"
        if ready and int(d.tx_valid.value):
            output.append(int(d.tx_byte.value))
        if bytes(output) == framed(reply):
            break
    else:
        assert False, "error reply did not drain"
    await Timer(50, units="ns")
    assert not int(d.request.value) and not int(d.active.value)
