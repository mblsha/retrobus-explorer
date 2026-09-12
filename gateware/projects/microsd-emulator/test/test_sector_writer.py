import random

import cocotb
from cocotb_helpers import start_clock, tick


@cocotb.test()
async def synchronous_staging_buffer_to_complete_masked_native_sector(d):
    start_clock(d.clk, 12)
    d.rst.value = 1
    d.start.value = d.cmd_ready.value = d.wdata_ready.value = 0
    d.lba.value = d.sector_byte.value = 0
    await tick(d.clk, 4)
    d.rst.value = 0
    rng = random.Random(6601)
    for lba in (0, 127, 128, 16383, 524287):
        data = bytes(rng.randrange(256) for _ in range(512))
        d.lba.value = lba
        d.start.value = 1
        await tick(d.clk)
        d.start.value = 0
        d.lba.value = 999  # The accepted address must remain latched.
        address = payload = None
        words = []
        previous_index = 0
        for cycle in range(10000):
            d.sector_byte.value = data[previous_index]
            previous_index = int(d.byte_index.value)
            command_ready = rng.randrange(5) == 0
            data_ready = rng.randrange(4) == 0
            d.cmd_ready.value = command_ready
            d.wdata_ready.value = data_ready
            if int(d.cmd_valid.value) and command_ready:
                assert address is None
                address = int(d.cmd_address.value)
            if int(d.wdata_valid.value) and data_ready:
                assert payload is None
                assert int(d.wdata_mask.value) == 0xFFFF
                payload = int(d.wdata.value)
            if address is not None and payload is not None:
                assert address == lba * 32 + len(words)
                words.append(payload.to_bytes(16, "little"))
                address = payload = None
            await tick(d.clk)
            if int(d.complete.value):
                break
        else:
            assert False, "sector commit timed out"
        assert not int(d.failed.value) and not int(d.busy.value)
        assert len(words) == 32 and b"".join(words) == data
        await tick(d.clk, 2)
    for lba in (524288, 0xFFFFFFFF):
        d.lba.value = lba
        d.start.value = 1
        await tick(d.clk)
        d.start.value = 0
        assert int(d.complete.value) and int(d.failed.value)
        assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
        await tick(d.clk, 2)


@cocotb.test()
async def independent_acknowledgments_stay_consumed_until_next_word(d):
    """A stalled channel must not reissue the other channel's accepted beat."""
    start_clock(d.clk, 10)
    d.rst.value = 1
    d.start.value = d.cmd_ready.value = d.wdata_ready.value = 0
    d.lba.value = 17
    d.sector_byte.value = 0xA6
    await tick(d.clk, 4)
    d.rst.value = 0
    d.start.value = 1
    await tick(d.clk)
    d.start.value = 0
    for word in range(32):
        for _ in range(40):
            if int(d.cmd_valid.value) and int(d.wdata_valid.value):
                break
            await tick(d.clk)
        else:
            assert False, f"word {word} not offered"
        assert int(d.cmd_address.value) == 17 * 32 + word
        assert int(d.wdata.value) == int.from_bytes(bytes([0xA6]) * 16, "little")
        first, second = ("cmd", "wdata") if word % 2 else ("wdata", "cmd")
        getattr(d, first + "_ready").value = 1
        await tick(d.clk)
        for _ in range(19):
            assert not int(getattr(d, first + "_valid").value)
            assert int(getattr(d, second + "_valid").value)
            assert int(d.busy.value) and not int(d.complete.value)
            assert int(d.cmd_address.value) == 17 * 32 + word
            await tick(d.clk)
        getattr(d, second + "_ready").value = 1
        await tick(d.clk)
        assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
        d.cmd_ready.value = d.wdata_ready.value = 0
        if word < 31:
            assert int(d.busy.value) and not int(d.complete.value)
    assert int(d.complete.value) and not int(d.busy.value)
    assert not int(d.failed.value)
    await tick(d.clk)
    assert not int(d.complete.value)
