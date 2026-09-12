import random
import cocotb
from cocotb_helpers import start_clock, tick
from microsd_image import packet, decode_ack


async def send(d, raw):
    for b in raw:
        d.rx_valid.value = 1
        d.rx_byte.value = b
        assert not int(d.load_valid.value), "image mutation before CRC validation"
        await tick(d.clk)
    d.rx_valid.value = 0


async def finish(d):
    writes = []
    ack = bytearray()
    rng = random.Random(334)
    for _ in range(1500):
        lr = int(rng.randrange(4) != 0)
        tr = int(rng.randrange(3) != 0)
        d.load_ready.value = lr
        d.tx_ready.value = tr
        valid = int(d.load_valid.value)
        address = int(d.load_address.value)
        byte = int(d.load_byte.value)
        if valid and lr:
            writes.append((address, byte))
        if int(d.tx_valid.value) and tr:
            ack.append(int(d.tx_byte.value))
        await tick(d.clk)
        if valid and not lr:
            assert (
                int(d.load_valid.value)
                and int(d.load_address.value) == address
                and int(d.load_byte.value) == byte
            )
        if len(ack) == 16:
            break
    d.load_ready.value = 0
    d.tx_ready.value = 0
    return writes, decode_ack(bytes(ack))


@cocotb.test()
async def atomic_crc_checked_upload_bounds_full_image_and_arm(d):
    start_clock(d.clk)
    d.rst.value = 1
    d.rx_valid.value = 0
    d.rx_byte.value = 0
    d.tx_ready.value = 0
    d.load_ready.value = 0
    await tick(d.clk, 5)
    d.rst.value = 0
    await tick(d.clk)
    await send(d, packet(2, 0, 1))
    writes, ack = await finish(d)
    assert not writes and ack == (2, 4, 1) and not int(d.armed.value)
    raw = bytearray(packet(1, 0, 2, bytes([0xFF]) * 512))
    raw[77] ^= 1
    await send(d, raw)
    writes, ack = await finish(d)
    assert not writes and ack == (1, 1, 2)
    for sector in range(128):
        data = bytes((i + sector) & 255 for i in range(512))
        await send(d, packet(1, sector, sector + 10, data))
        writes, ack = await finish(d)
        assert writes == [(sector * 512 + i, b) for i, b in enumerate(data)]
        assert ack == (1, 0, sector + 10)
    await send(d, packet(2, 0, 200))
    writes, ack = await finish(d)
    assert not writes and ack == (2, 0, 200) and int(d.armed.value)
    await send(d, packet(1, 0, 201))
    writes, ack = await finish(d)
    assert not writes and ack == (1, 3, 201)
    await send(d, packet(3, 0, 202))
    writes, ack = await finish(d)
    assert not writes and ack == (3, 0, 202) and not int(d.armed.value)
    await send(d, packet(2, 0, 203))
    writes, ack = await finish(d)
    assert ack == (2, 4, 203)


@cocotb.test()
async def malformed_bounds_timeout_resync_and_reset(d):
    import struct
    import zlib
    from cocotb.triggers import Timer

    start_clock(d.clk)
    d.rst.value = 1
    d.rx_valid.value = 0
    d.rx_byte.value = 0
    d.tx_ready.value = 0
    d.load_ready.value = 0
    await tick(d.clk, 5)
    d.rst.value = 0
    await tick(d.clk)
    for sector in (128, 65536, 0xFFFFFFFF):
        raw = bytearray(packet(1, 0, 44))
        struct.pack_into("<I", raw, 8, sector)
        struct.pack_into("<I", raw, 528, zlib.crc32(raw[:528]))
        await send(d, raw)
        writes, ack = await finish(d)
        assert not writes and ack == (1, 2, 44)
    # A truncated header expires; an overlapping magic prefix resynchronizes.
    await send(d, packet(1, 0, 45)[:30])
    await Timer(10_000_100, units="ns")
    assert not int(d.tx_valid.value) and not int(d.load_valid.value)
    await send(d, b"MMS")
    await send(d, packet(1, 0, 46))
    writes, ack = await finish(d)
    assert len(writes) == 512 and ack == (1, 0, 46)
    await send(d, packet(1, 1, 47))
    d.load_ready.value = 1
    await tick(d.clk, 10)
    d.rst.value = 1
    await tick(d.clk, 3)
    assert not int(d.armed.value) and not int(d.load_valid.value)
    d.rst.value = 0
    d.load_ready.value = 0
    await tick(d.clk)
    await send(d, packet(2, 0, 48))
    writes, ack = await finish(d)
    assert not writes and ack == (2, 4, 48)


@cocotb.test()
async def status_query_is_read_only_and_crc_checked(d):
    start_clock(d.clk)
    d.rst.value = 1
    d.status_word.value = 0x12345678
    d.rx_valid.value = 0
    d.rx_byte.value = 0
    d.tx_ready.value = 0
    d.load_ready.value = 0
    await tick(d.clk, 5)
    d.rst.value = 0
    await send(d, packet(4, 0, 77))
    writes, ack = await finish(d)
    assert not writes and ack == (4, 0, 0x12345678)
    assert not int(d.armed.value)
    bad = bytearray(packet(4, 0, 78))
    bad[-1] ^= 1
    await send(d, bad)
    writes, ack = await finish(d)
    assert not writes and ack == (4, 1, 78)


@cocotb.test()
async def indexed_status_queries_do_not_mutate_memory(d):
    start_clock(d.clk)
    d.rst.value = 1
    d.rx_valid.value = 0
    d.rx_byte.value = 0
    d.tx_ready.value = 0
    d.load_ready.value = 0
    d.status_word.value = 0
    await tick(d.clk, 3)
    d.rst.value = 0
    await tick(d.clk)
    for selector in (0, 1, 7, 11, 127):
        await send(d, packet(4, selector, 99))
        assert int(d.status_selector.value) == selector
        # Selector is established by the header before the status snapshot.
        d.status_word.value = 0xdead0000 | selector
        writes, ack = await finish(d)
        assert not writes and not int(d.armed.value)
        assert ack == (4, 0, 0xdead0000 | selector)
