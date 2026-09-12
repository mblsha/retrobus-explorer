import random

import cocotb
from cocotb_helpers import start_clock, tick


MASK = (1 << 128) - 1


def pattern(address, inverted):
    value = sum(address << shift for shift in (0, 32, 64, 96))
    value ^= 0x0123456789ABCDEF55AA33CCF00F9696
    return value ^ (MASK if inverted else 0)


async def reset(d, count=33, timeout=100):
    for name in ("start", "cmd_ready", "wdata_ready", "rdata_valid", "rdata"):
        getattr(d, name).value = 0
    d.word_count.value = count
    d.timeout_cycles.value = timeout
    d.rst.value = 1
    await tick(d.clk, 3)
    assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
    d.rst.value = 0
    await tick(d.clk)
    d.start.value = 1
    await tick(d.clk)
    d.start.value = 0


async def run_memory(d, count=33, corrupt=None, address_mask=None):
    await reset(d, count)
    rng = random.Random(421)
    memory = {}
    pending_command = pending_data = pending_read = None
    writes = reads = 0
    for cycle in range(10000):
        if int(d.failed.value) or int(d.passed.value):
            return writes, reads, memory
        command_ready = rng.randrange(3) != 0
        data_ready = rng.randrange(3) != 0
        d.cmd_ready.value = command_ready
        d.wdata_ready.value = data_ready
        d.rdata_valid.value = 0
        if pending_read is not None and cycle >= pending_read[0]:
            _, address, value = pending_read
            assert int(d.rdata_ready.value)
            d.rdata_valid.value = 1
            d.rdata.value = value
            pending_read = None
        if int(d.cmd_valid.value) and command_ready:
            address = int(d.cmd_address.value)
            assert 0 <= address < count
            if int(d.cmd_write.value):
                assert pending_command is None
                pending_command = address
            else:
                assert pending_read is None
                assert address == reads % count
                key = address if address_mask is None else address & address_mask
                value = memory[key]
                if corrupt is not None and (address, reads // count) == corrupt[:2]:
                    value ^= 1 << corrupt[2]
                pending_read = (cycle + rng.randrange(2, 8), address, value)
                reads += 1
        if int(d.wdata_valid.value) and data_ready:
            assert pending_data is None
            assert int(d.wdata_mask.value) == 0xFFFF
            pending_data = int(d.wdata.value)
        if pending_command is not None and pending_data is not None:
            assert pending_command == writes % count
            assert pending_data == (
                0 if writes >= count * 2 else pattern(pending_command, writes >= count)
            )
            key = (
                pending_command
                if address_mask is None
                else pending_command & address_mask
            )
            memory[key] = pending_data
            pending_command = pending_data = None
            writes += 1
        await tick(d.clk)
    assert False, "native BIST did not terminate"


@cocotb.test()
async def pattern_and_zero_passes_independent_channels_and_delayed_reads(d):
    start_clock(d.clk, 12)
    writes, reads, memory = await run_memory(d)
    assert int(d.passed.value) and not int(d.failed.value)
    assert writes == reads == 99
    assert memory == {i: 0 for i in range(33)}
    await tick(d.clk, 5)
    assert int(d.passed.value) and not int(d.busy.value)
    assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)


@cocotb.test()
async def corruption_is_sticky_and_records_address(d):
    start_clock(d.clk, 12)
    await run_memory(d, corrupt=(17, 0, 0))
    assert int(d.failed.value) and not int(d.passed.value)
    assert int(d.progress.value) == 17
    assert int(d.diagnostic.value) == 11
    assert int(d.expected_word.value) == pattern(17, False)
    assert int(d.actual_word.value) == pattern(17, False) ^ 1
    d.start.value = 1
    await tick(d.clk, 10)
    assert int(d.failed.value) and int(d.progress.value) == 17
    assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)


@cocotb.test()
async def timeout_and_invalid_region(d):
    start_clock(d.clk, 12)
    await reset(d, timeout=8)
    await tick(d.clk, 12)
    assert int(d.failed.value) and not int(d.passed.value)
    assert int(d.diagnostic.value) >> 3 == 2
    for count in (0, 16777217):
        await reset(d, count=count)
        assert int(d.failed.value) and not int(d.cmd_valid.value)
        assert int(d.diagnostic.value) == 24
    writes, reads, _ = await run_memory(d, count=1)
    assert int(d.passed.value) and writes == reads == 3


@cocotb.test()
async def detects_all_byte_lanes_in_all_passes_and_address_aliasing(d):
    start_clock(d.clk, 12)
    for phase in (0, 1, 2):
        for lane in range(16):
            await run_memory(d, count=3, corrupt=(1, phase, lane * 8 + 7))
            assert int(d.failed.value) and not int(d.passed.value)
            assert int(d.progress.value) == 1
    await run_memory(d, count=33, address_mask=15)
    assert int(d.failed.value) and int(d.progress.value) == 0


@cocotb.test()
async def timeout_after_partial_write_or_outstanding_read(d):
    start_clock(d.clk, 12)
    for command_ready, data_ready in ((1, 0), (0, 1)):
        await reset(d, count=1, timeout=8)
        d.cmd_ready.value = command_ready
        d.wdata_ready.value = data_ready
        await tick(d.clk, 2)
        assert int(d.cmd_valid.value) == (not command_ready)
        assert int(d.wdata_valid.value) == (not data_ready)
        await tick(d.clk, 12)
        assert int(d.failed.value) and not int(d.passed.value)
        assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
    await reset(d, count=1, timeout=8)
    d.cmd_ready.value = 1
    d.wdata_ready.value = 1
    await tick(d.clk, 3)
    assert int(d.rdata_ready.value)
    await tick(d.clk, 12)
    assert int(d.failed.value) and not int(d.rdata_ready.value)


@cocotb.test()
async def accepts_full_physical_capacity_without_count_wrap(d):
    start_clock(d.clk, 12)
    for count in (524289, 16777215, 16777216):
        await reset(d, count=count)
        assert int(d.busy.value) and not int(d.failed.value)
        assert int(d.cmd_valid.value) and int(d.cmd_address.value) == 0
        d.cmd_ready.value = 1
        d.wdata_ready.value = 1
        await tick(d.clk, 2)
        assert int(d.cmd_address.value) > 0
        assert not int(d.passed.value)
