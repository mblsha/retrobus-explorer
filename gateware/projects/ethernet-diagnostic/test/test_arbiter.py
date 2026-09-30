import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


@cocotb.test()
async def grants_are_exclusive_and_release_handshake_is_preserved(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    for name in ("ethernet_request", "serial_request", "request_address", "reply_write", "reply_done"):
        getattr(d, name).value = 0
    d.ethernet_length.value, d.serial_length.value = 540, 28
    d.ethernet_data.value, d.serial_data.value = 17, 29
    d.rst.value = 1
    await Timer(30, units="ns")
    d.rst.value = 0
    d.ethernet_request.value = d.serial_request.value = 1
    await Timer(30, units="ns")
    assert int(d.request.value)
    assert int(d.request_data.value) == 29
    d.reply_write.value = 1
    d.request_address.value = 7
    await Timer(10, units="ns")
    assert int(d.serial_reply_write.value) and not int(d.ethernet_reply_write.value)
    assert int(d.serial_address.value) == int(d.ethernet_address.value) == 7
    await FallingEdge(d.clk)
    d.reply_done.value = 1
    await Timer(1, units="ns")
    assert int(d.serial_reply_done.value) and not int(d.ethernet_reply_done.value)
    await FallingEdge(d.clk)
    d.serial_request.value = d.reply_done.value = d.reply_write.value = 0
    for _ in range(2):
        assert not int(d.request.value)
        await FallingEdge(d.clk)
    await Timer(20, units="ns")
    assert int(d.request.value) and int(d.request_data.value) == 17
    d.reply_write.value = 1
    await Timer(10, units="ns")
    assert int(d.ethernet_reply_write.value) and not int(d.serial_reply_write.value)
    d.rst.value = 1
    await Timer(20, units="ns")
    assert not int(d.request.value)
    assert not int(d.ethernet_reply_write.value) and not int(d.serial_reply_write.value)


@cocotb.test()
async def simultaneous_requests_alternate_without_releasing_a_busy_owner(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
    for name in ("ethernet_request", "serial_request", "request_address", "reply_write", "reply_done"):
        getattr(d, name).value = 0
    d.ethernet_length.value, d.serial_length.value = 540, 28
    d.ethernet_data.value, d.serial_data.value = 17, 29
    d.rst.value = 1
    await Timer(30, units="ns")
    await FallingEdge(d.clk)
    d.rst.value = 0
    d.ethernet_request.value = d.serial_request.value = 1

    # Both adapters stay queued. Completion alternates the next grant;
    # waiting for a reply must retain the current source throughout.
    for source, data, length in (("serial", 29, 28), ("ethernet", 17, 540)) * 2:
        for _ in range(5):
            await FallingEdge(d.clk)
            if int(d.request.value):
                break
        else:
            assert False, "queued request was not granted"
        d.reply_write.value = 1
        for _ in range(5):
            await Timer(1, units="ns")
            assert int(d.request.value)
            assert int(d.request_data.value) == data
            assert int(d.request_length.value) == length
            assert int(d.serial_reply_write.value) == (source == "serial")
            assert int(d.ethernet_reply_write.value) == (source == "ethernet")
            await FallingEdge(d.clk)
        d.reply_done.value = 1
        await Timer(1, units="ns")
        assert int(d.serial_reply_done.value) == (source == "serial")
        assert int(d.ethernet_reply_done.value) == (source == "ethernet")
        await FallingEdge(d.clk)
        d.reply_done.value = d.reply_write.value = 0
        release_cycles = 0
        while not int(d.request.value):
            assert not int(d.serial_reply_write.value)
            assert not int(d.ethernet_reply_write.value)
            release_cycles += 1
            assert release_cycles <= 3, "release stalled a queued request"
            await FallingEdge(d.clk)
        assert release_cycles == 3
