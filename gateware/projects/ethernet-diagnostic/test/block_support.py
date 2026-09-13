"""Clocked block-service peer with explicit memory completion/error injection."""

import zlib
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


async def block_fixture(dut):
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
    requests = []

    async def exchange(wire, status=0, *, memory_failure=False):
        dut.request.value = 1
        dut.request_length.value = len(wire)
        reply = bytearray()
        progress = 0
        current = None
        memory_requests_before = len(requests)
        for _ in range(10000):
            await FallingEdge(dut.clk)
            addr = int(dut.request_address.value)
            dut.request_data.value = wire[addr] if addr < len(wire) else 0
            if int(dut.memory_request.value):
                lba = int(dut.memory_lba.value)
                if current is None:
                    requests.append((int(dut.memory_write.value), lba))
                    current = (
                        bytearray(512)
                        if int(dut.memory_write.value)
                        else b"".join(
                            memory.get(lba + n, bytes(512))
                            for n in range(int(dut.memory_count.value))
                        )
                    )
                if memory_failure:
                    dut.memory_error.value = 1
                    dut.memory_done.value = 1
                elif int(dut.memory_write.value):
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
                dut.memory_error.value = 0
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
        if status and status != 7:
            assert len(requests) == memory_requests_before, (
                "Rejected command reached memory"
            )
        return bytes(reply)

    return memory, writes, reads, requests, exchange
