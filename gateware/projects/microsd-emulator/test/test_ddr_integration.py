import random
from collections import deque
import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer
from test_integration import exercise_image


async def memory_model(d, memory=None, read_addresses=None, clock=None, allow=None):
    clock = d.clk if clock is None else clock
    rng = random.Random(1903)
    commands = deque()
    writes = deque()
    if memory is None:
        memory = {}
    pending = None
    while True:
        await FallingEdge(clock)
        d.ddr_cmd_ready.value = int((allow is None or allow[0]) and rng.randrange(5) != 0)
        d.ddr_wdata_ready.value = int((allow is None or allow[0]) and rng.randrange(3) != 0)
        if pending is not None:
            delay, data = pending
            if delay:
                pending = (delay - 1, data)
            else:
                d.ddr_rdata.value = data
                d.ddr_rdata_valid.value = 1
        await Timer(1, units="ps")
        cmd = int(d.ddr_cmd_valid.value) and int(d.ddr_cmd_ready.value)
        write = int(d.ddr_wdata_valid.value) and int(d.ddr_wdata_ready.value)
        if cmd:
            commands.append((int(d.ddr_cmd_write.value), int(d.ddr_cmd_address.value)))
        if write:
            writes.append((int(d.ddr_wdata.value), int(d.ddr_wdata_mask.value)))
        read = int(d.ddr_rdata_valid.value) and int(d.ddr_rdata_ready.value)
        await RisingEdge(clock)
        await Timer(1, units="ps")
        if read:
            d.ddr_rdata_valid.value = 0
            pending = None
        if commands:
            we, address = commands[0]
            if we and writes:
                data, mask = writes.popleft()
                commands.popleft()
                value = memory.get(address, 0)
                for lane in range(16):
                    if mask & (1 << lane):
                        value = (value & ~(255 << (8 * lane))) | (
                            data & (255 << (8 * lane))
                        )
                memory[address] = value
            elif not we and pending is None:
                commands.popleft()
                if read_addresses is not None:
                    read_addresses.append(address)
                pending = (rng.randrange(2, 20), memory.get(address, 0))


@cocotb.test()
async def complete_image_loader_native_ddr_sd_path(d):
    d.writable.value = 0
    d.dat_in.value = 15
    d.diagnostic_status.value = 0
    d.initialized.value = 1
    d.ddr_cmd_ready.value = 0
    d.ddr_wdata_ready.value = 0
    d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    read_addresses = []
    task = cocotb.start_soon(memory_model(d, read_addresses=read_addresses))
    await exercise_image(d)
    for lba in (128, 16383):
        assert set(range(lba * 32, (lba + 1) * 32)) <= set(read_addresses)
    task.kill()
