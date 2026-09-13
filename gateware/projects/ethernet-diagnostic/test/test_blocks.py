import struct
import zlib
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


def packet(op, seq, lba=0, count=0, data=b"", session=0x12345678):
    body = (
        b"RBS1"
        + bytes([op, 0, 0, 0])
        + struct.pack("<IIII", session, seq, lba, count)
        + data.ljust(512, b"\0")
    )
    assert len(body) == 536
    return body + struct.pack("<I", zlib.crc32(body))


@cocotb.test()
async def ordered_transfer_and_retries(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    for name in (
        "request",
        "request_length",
        "request_data",
        "memory_write_index",
        "memory_read_valid",
        "memory_read_index",
        "memory_read_data",
        "memory_done",
        "memory_error",
    ):
        getattr(dut, name).value = 0
    dut.rst.value = 1
    dut.initialized.value = 1
    dut.sd_quiescent.value = 1
    await Timer(40, units="ns")
    dut.rst.value = 0
    memory = {}
    writes = []
    reads = []

    async def exchange(wire, status=0):
        dut.request.value = 1
        dut.request_length.value = len(wire)
        reply = bytearray()
        progress = 0
        current = None
        for _ in range(10000):
            await FallingEdge(dut.clk)
            addr = int(dut.request_address.value)
            dut.request_data.value = wire[addr] if addr < len(wire) else 0
            if int(dut.memory_request.value):
                lba = int(dut.memory_lba.value)
                if current is None:
                    current = (
                        bytearray(512)
                        if int(dut.memory_write.value)
                        else b"".join(
                            memory.get(lba + n, bytes(512))
                            for n in range(int(dut.memory_count.value))
                        )
                    )
                if int(dut.memory_write.value):
                    index, phase = divmod(progress, 3)
                    if index < 512:
                        dut.memory_write_index.value = index
                        if phase == 2:
                            current[index] = int(dut.memory_write_data.value)
                        progress += 1
                    elif progress == 1536:
                        memory[lba] = bytes(current)
                        writes.append(lba)
                        dut.memory_done.value = 1
                        progress += 1
                elif progress < len(current):
                    dut.memory_read_valid.value = 1
                    dut.memory_read_index.value = progress
                    dut.memory_read_data.value = current[progress]
                    progress += 1
                elif progress == len(current):
                    dut.memory_read_valid.value = 0
                    dut.memory_done.value = 1
                    reads.append(lba)
                    progress += 1
            else:
                dut.memory_done.value = 0
                dut.memory_read_valid.value = 0
            if int(dut.reply_write.value):
                assert int(dut.reply_address.value) == len(reply)
                reply.append(int(dut.reply_data.value))
            if int(dut.reply_done.value):
                assert int(dut.reply_length.value) == len(reply)
                dut.request.value = 0
                await Timer(30, units="ns")
                break
        else:
            assert False, "Block service timeout"
        if len(wire) not in (28, 540):
            assert not reply
            return reply
        assert len(reply) == (
            1052
            if wire[4] == 7
            and int.from_bytes(wire[20:24], "little") == 2
            and status == 0
            else 540
        )
        assert reply[:4] == b"RBA1"
        assert zlib.crc32(reply[:-4]) == int.from_bytes(reply[-4:], "little")
        assert reply[5] == status, (reply[5], status)
        return bytes(reply)

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
