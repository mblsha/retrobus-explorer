import struct
import zlib
import cocotb
from cocotb.triggers import Timer
from packet_support import packet
from block_support import block_fixture


@cocotb.test()
async def ordered_transfer_and_retries(dut):
    memory, writes, reads, requests, exchange = await block_fixture(dut)

    await exchange(packet(1, 0, count=2))
    assert not int(dut.armed.value)
    await exchange(packet(3, 1, count=1))
    first = bytes((i * 31 + 7) & 255 for i in range(512))
    request = packet(2, 2, count=1, data=first)
    ack = await exchange(request)
    assert writes == [0] and memory[0] == first
    assert await exchange(request) == ack
    assert writes == [0]
    await exchange(packet(2, 2, count=1, data=first[::-1]), 9)
    assert writes == [0]
    await exchange(packet(2, 4, lba=1, count=1), 3)
    await exchange(packet(2, 3, lba=1, count=1, data=first[::-1]))
    await exchange(packet(4, 4))
    assert int(dut.armed.value)
    await exchange(packet(7, 333, count=2), 4)
    await exchange(packet(2, 5, lba=2, count=1), 4)
    await exchange(packet(3, 6, count=1), 4)
    await exchange(packet(1, 0, count=1, session=99), 4)
    await exchange(packet(5, 7))
    assert not int(dut.armed.value)
    reply = await exchange(packet(3, 8, count=1))
    assert reply[24:536] == first
    memory[0] = bytes(512)
    assert await exchange(packet(3, 8, count=1)) == reply
    assert reads == [0, 0]
    compact = packet(7, 875, lba=0, count=2)[:24]
    compact += struct.pack("<I", zlib.crc32(compact))
    assert (await exchange(compact))[24:-4] == bytes(512) + first[::-1]
    bulk = await exchange(packet(7, 876, lba=0, count=2))
    assert bulk[24:-4] == bytes(512) + first[::-1]
    memory[0] = first
    assert (await exchange(packet(7, 876, lba=0, count=2)))[24:-4] == first + first[
        ::-1
    ]
    await exchange(packet(7, 1, lba=524287, count=2), 5)
    await exchange(packet(7, 1, count=0), 5)
    await exchange(packet(7, 1, count=2, session=99), 2)
    short_write = packet(2, 9, count=1)[:24]
    short_write += struct.pack("<I", zlib.crc32(short_write))
    await exchange(short_write, 1)
    assert writes == [0, 1]
    corrupt = bytearray(packet(3, 9, count=1))
    corrupt[25] ^= 1
    await exchange(corrupt, 1)
    await exchange(packet(3, 9, lba=524288, count=1), 5)
    await exchange(packet(6, 10, session=99), 2)
    await exchange(packet(6, 10))
    await exchange(b"truncated")
    dut.rst.value = 1
    await Timer(30, units="ns")
    dut.rst.value = 0
    await exchange(packet(2, 11, count=1), 2)
    assert writes == [0, 1]


@cocotb.test()
async def sequence_wrap_and_cached_error(dut):
    _, _, _, requests, exchange = await block_fixture(dut)
    await exchange(packet(1, 0, count=1))
    # Reach the wrap boundary without executing four billion transactions.
    dut.next_sequence.value = 0xFFFFFFFF
    rejected = packet(3, 0xFFFFFFFF, lba=524288, count=1)
    first = await exchange(rejected, 5)
    assert int(dut.next_sequence.value) == 0
    assert await exchange(rejected, 5) == first
    assert int(dut.next_sequence.value) == 0
    await exchange(packet(6, 0))
    assert int(dut.next_sequence.value) == 1
    assert not requests


@cocotb.test()
async def memory_error_is_cached_without_advancing_upload(dut):
    _, writes, _, requests, exchange = await block_fixture(dut)
    await exchange(packet(1, 0, count=1))
    failed = packet(2, 1, count=1, data=b"x" * 512)
    first = await exchange(failed, 7, memory_failure=True)
    assert int(dut.written_sectors.value) == 0
    assert int(dut.next_sequence.value) == 2
    assert await exchange(failed, 7) == first
    assert len(requests) == 1 and not writes
    await exchange(packet(4, 2), 8)
    assert not int(dut.armed.value)
    assert len(requests) == 1
