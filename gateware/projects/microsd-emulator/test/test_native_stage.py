import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer, RisingEdge
from cocotb_helpers import tick


@cocotb.test()
async def write_commands_wait_for_their_data(d):
    cocotb.start_soon(Clock(d.clk, 12, units="ns").start())
    d.rst.value = 1
    d.s_cmd_valid.value = d.s_wdata_valid.value = d.m_rdata_valid.value = 0
    d.m_cmd_ready.value = 1
    d.m_wdata_ready.value = d.s_rdata_ready.value = 0
    await Timer(40, units="ns")
    d.rst.value = 0
    await Timer(24, units="ns")
    d.s_cmd_address.value = 127
    d.s_cmd_write.value = 1
    d.s_cmd_valid.value = 1
    d.s_wdata.value = 0x1111
    d.s_wmask.value = 0xFFFF
    d.s_wdata_valid.value = 1
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    d.s_cmd_address.value = 128
    d.s_wdata.value = 0x2222
    await RisingEdge(d.clk)
    await Timer(1, units="ns")
    # First command is accepted but its data has not yet been consumed.
    # A second command must not reach LiteDRAM with only the first data buffered.
    for _ in range(3):
        await RisingEdge(d.clk)
        await Timer(1, units="ns")
        assert not int(d.m_cmd_valid.value), "write command outran buffered data"
    d.s_cmd_valid.value = d.s_wdata_valid.value = 0
    d.rst.value = 1
    await tick(d.clk, 3)
    d.rst.value = 0
    await tick(d.clk, 3)
    assert not int(d.m_cmd_valid.value) and not int(d.m_wdata_valid.value)
    assert not int(d.s_rdata_valid.value)


@cocotb.test()
async def scheduled_native_data_with_stalls_masks_and_read_backpressure(d):
    cocotb.start_soon(Clock(d.clk, 12, units="ns").start())
    d.rst.value = 1
    for name in (
        "s_cmd_valid",
        "s_wdata_valid",
        "m_rdata_valid",
        "m_cmd_ready",
        "m_wdata_ready",
        "s_rdata_ready",
    ):
        getattr(d, name).value = 0
    await tick(d.clk, 4)
    d.rst.value = 0
    await tick(d.clk)
    rng = random.Random(814)
    addresses = [i * 129 for i in range(64)]
    commands = [(a, w) for w in (1, 0, 1, 0) for a in addresses]
    writes = [(rng.getrandbits(128), rng.randrange(1, 65536)) for _ in range(128)]
    ci = wi = physical_ci = physical_wi = reads = 0
    command_valid = data_valid = False
    inflight = pending_write = pending_read = None
    expected_read = None
    memory = {}
    for cycle in range(30000):
        if ci < len(commands) and not command_valid:
            command_valid = rng.randrange(4) != 0
        if wi < len(writes) and not data_valid:
            data_valid = rng.randrange(4) != 0
        d.s_cmd_valid.value = command_valid
        d.s_wdata_valid.value = data_valid
        if ci < len(commands):
            d.s_cmd_address.value, d.s_cmd_write.value = commands[ci]
        if wi < len(writes):
            d.s_wdata.value, d.s_wmask.value = writes[wi]
        ready = rng.randrange(4) != 0
        read_ready = rng.randrange(3) != 0
        d.m_cmd_ready.value = ready
        d.s_rdata_ready.value = read_ready
        d.m_wdata_ready.value = d.m_rdata_valid.value = 0
        # LiteDRAM can schedule data independently of valid/ready backpressure.
        if int(d.m_cmd_valid.value) and ready:
            assert inflight is None, "multiple outstanding native transactions"
            address, write = int(d.m_cmd_address.value), int(d.m_cmd_write.value)
            assert (address, write) == commands[physical_ci]
            physical_ci += 1
            inflight = (address, write)
            if write:
                pending_write = cycle + rng.randrange(1, 7)
            else:
                pending_read = cycle + rng.randrange(1, 7)
                expected_read = memory[address]
        if pending_write == cycle:
            # Intentionally do not wait for m_wdata_valid before consuming.
            assert int(d.m_wdata_valid.value), "native write-data underrun"
            data, mask = int(d.m_wdata.value), int(d.m_wmask.value)
            assert (data, mask) == writes[physical_wi]
            physical_wi += 1
            address = inflight[0]
            old = memory.get(address, 0)
            for lane in range(16):
                if mask >> lane & 1:
                    old = (old & ~(255 << (lane * 8))) | (data & (255 << (lane * 8)))
            memory[address] = old
            d.m_wdata_ready.value = 1
            pending_write = inflight = None
        if pending_read == cycle:
            assert int(d.m_rdata_ready.value), "native read-data overrun"
            d.m_rdata.value = expected_read
            d.m_rdata_valid.value = 1
            pending_read = None
        if int(d.s_rdata_valid.value) and read_ready:
            assert int(d.s_rdata.value) == expected_read
            reads += 1
            inflight = None
        if command_valid and int(d.s_cmd_ready.value):
            ci += 1
            command_valid = False
        if data_valid and int(d.s_wdata_ready.value):
            wi += 1
            data_valid = False
        await tick(d.clk)
        if reads == 128:
            assert ci == physical_ci == 256 and wi == physical_wi == 128
            break
    else:
        assert False, "native adapter did not complete"
    d.rst.value = 1
    await tick(d.clk, 3)
    assert not int(d.m_cmd_valid.value) and not int(d.m_wdata_valid.value)
    assert not int(d.s_rdata_valid.value)
