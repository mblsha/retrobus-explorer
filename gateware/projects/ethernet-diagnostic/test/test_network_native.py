import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer


@cocotb.test()
async def native_backpressure_and_bounds(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    for name in (
        "request",
        "count",
        "write",
        "lba",
        "write_data",
        "cmd_ready",
        "rdata_valid",
        "rdata",
        "wdata_ready",
    ):
        getattr(dut, name).value = 0
    dut.enabled.value = 1
    await Timer(40, units="ns")
    dut.rst.value = 0
    memory = {}
    commands = []
    data = []
    pending = []
    returned = None
    cycle = 0

    async def operation(write, lba, payload=bytes(512), error=False, count=1):
        nonlocal returned, cycle
        dut.request.value = 1
        dut.write.value = write
        dut.lba.value = lba
        dut.count.value = count
        result = bytearray()
        previous_index = 0
        for _ in range(20000):
            await FallingEdge(dut.clk)
            cycle += 1
            dut.write_data.value = payload[previous_index]
            previous_index = int(dut.write_index.value)
            dut.cmd_ready.value = cycle % 5 in (0, 1)
            dut.wdata_ready.value = cycle % 7 in (2, 3)
            if returned is None and pending and pending[0][0] <= cycle:
                _, addr = pending.pop(0)
                returned = memory.get(addr, 0)
            dut.rdata_valid.value = returned is not None
            dut.rdata.value = returned or 0
            await Timer(1, units="ns")
            if int(dut.cmd_valid.value) and int(dut.cmd_ready.value):
                addr = int(dut.cmd_address.value)
                if int(dut.cmd_write.value):
                    commands.append(addr)
                else:
                    pending.append((cycle + 5, addr))
            if int(dut.wdata_valid.value) and int(dut.wdata_ready.value):
                assert int(dut.wdata_mask.value) == 65535
                data.append(int(dut.wdata.value))
            if commands and data:
                memory[commands.pop(0)] = data.pop(0)
            if returned is not None and int(dut.rdata_ready.value):
                returned = None
            if int(dut.read_valid.value):
                assert int(dut.read_index.value) == len(result)
                result.append(int(dut.read_data.value))
            if int(dut.done.value):
                assert bool(dut.error.value) == error
                dut.request.value = 0
                await Timer(30, units="ns")
                break
        else:
            assert False, "Native timeout"
        return bytes(result)

    for lba in (0, 524287):
        payload = bytes((i * 17 + lba) & 255 for i in range(512))
        await operation(True, lba, payload)
        assert await operation(False, lba) == payload
    for lba in (1, 524286):
        first = bytes([0xA5]) * 512
        second = bytes([0x3C]) * 512
        await operation(True, lba, first)
        await operation(True, lba + 1, second)
        assert await operation(False, lba, count=2) == first + second
    await operation(False, 524287, error=True, count=2)
    snapshot = dict(memory)
    await operation(True, 524288, error=True)
    assert memory == snapshot
    assert not commands and not data and not pending
