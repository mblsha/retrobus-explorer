# top = tb_fifo

import random

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


DEPTH = 8


class AlchitrySyncFifoModel:
    """Cycle-accurate reference model of Alchitry's fifo.luc behavior."""

    def __init__(self, depth: int):
        self.depth = depth
        self.reset()

    def reset(self):
        self.waddr = 0
        self.waddr_delay = 0
        self.raddr = 0
        self.used = 0
        self.read_data = 0
        self.mem = [0] * self.depth
        self.queue: list[int] = []

    def _inc(self, value: int) -> int:
        # ENTRIES is expected to be a power of two, matching Alchitry fifo.luc.
        return (value + 1) % self.depth

    def _wrdy(self) -> bool:
        return self._inc(self.waddr) != self.raddr

    def _rrdy(self) -> bool:
        return self.raddr != self.waddr_delay

    def outputs(self) -> dict[str, int]:
        return {
            "full": int(not self._wrdy()),
            "empty": int(not self._rrdy()),
            "dout": self.read_data & 0xFF,
            "used": self.used,
        }

    def step(self, *, rst: int, wput: int, din: int, rget: int) -> dict[str, int]:
        if rst:
            self.reset()
            return self.outputs()

        old_waddr = self.waddr
        old_waddr_delay = self.waddr_delay
        old_raddr = self.raddr

        next_write = self._inc(old_waddr)
        wrdy = next_write != old_raddr
        rrdy = old_raddr != old_waddr_delay
        do_write = bool(wput and wrdy)
        do_read = bool(rget and rrdy)
        read_addr = self._inc(old_raddr) if do_read else old_raddr

        # Dual-port RAM behavior from simple_dual_port_ram.v:
        # read_data gets old mem content from selected raddr in this cycle.
        next_read_data = self.mem[read_addr]

        if do_write:
            self.mem[old_waddr] = din & 0xFF

        self.waddr = next_write if do_write else old_waddr
        self.waddr_delay = old_waddr
        self.raddr = self._inc(old_raddr) if do_read else old_raddr
        self.read_data = next_read_data
        self.used += int(do_write) - int(do_read)

        # Independent queue-level view for extra validation.
        if do_write:
            self.queue.append(din & 0xFF)
        if do_read:
            self.queue.pop(0)

        return self.outputs()


def _assert_matches(dut, expected: dict[str, int], model: AlchitrySyncFifoModel):
    full = int(dut.full.value)
    empty = int(dut.empty.value)
    dout = int(dut.dout.value)
    used = int(dut.used.value)

    assert full == expected["full"]
    assert empty == expected["empty"]
    assert dout == expected["dout"]
    assert used == expected["used"]

    # Extra invariants.
    assert used == len(model.queue)
    assert used <= DEPTH - 1  # Alchitry FIFO keeps one slot empty.
    if empty == 0:
        assert model.queue
        assert dout == model.queue[0]


async def _step(
    dut,
    model: AlchitrySyncFifoModel,
    *,
    rst: int,
    wput: int,
    din: int,
    rget: int,
):
    dut.rst.value = rst
    dut.wput.value = wput
    dut.din.value = din & 0xFF
    dut.rget.value = rget
    await tick(dut.clk, 1)
    expected = model.step(rst=rst, wput=wput, din=din, rget=rget)
    _assert_matches(dut, expected, model)
    return expected


@cocotb.test()
async def fifo_u8_matches_alchitry_semantics(dut):
    start_clock(dut.clk)
    model = AlchitrySyncFifoModel(DEPTH)

    await _step(dut, model, rst=1, wput=0, din=0x00, rget=0)
    await _step(dut, model, rst=1, wput=1, din=0xA5, rget=1)
    state = await _step(dut, model, rst=0, wput=0, din=0x00, rget=0)
    assert state["empty"] == 1

    # First write: queue occupancy increases immediately, but empty stays high one more cycle.
    state = await _step(dut, model, rst=0, wput=1, din=0x11, rget=0)
    assert state["used"] == 1
    assert state["empty"] == 1

    # One cycle later, entry appears at dout and empty deasserts.
    state = await _step(dut, model, rst=0, wput=0, din=0x00, rget=0)
    assert state["empty"] == 0
    assert state["dout"] == 0x11

    # Fill until full (usable entries are DEPTH-1).
    value = 0x20
    while True:
        state = await _step(dut, model, rst=0, wput=1, din=value, rget=0)
        value = (value + 1) & 0xFF
        if state["full"] == 1:
            break
    assert state["used"] == DEPTH - 1

    # Write while full is ignored.
    full_snapshot = dict(state)
    state = await _step(dut, model, rst=0, wput=1, din=0xEE, rget=0)
    assert state == full_snapshot

    # Read+write while full should perform only the read.
    state = await _step(dut, model, rst=0, wput=1, din=0xAB, rget=1)
    assert state["used"] == DEPTH - 2

    # Drain to empty.
    while model.queue:
        await _step(dut, model, rst=0, wput=0, din=0x00, rget=1)
    state = await _step(dut, model, rst=0, wput=0, din=0x00, rget=0)
    assert state["empty"] == 1

    # Random stress test with occasional resets.
    rng = random.Random(0xF1F0)
    for _ in range(1500):
        rst = 1 if rng.randrange(200) == 0 else 0
        wput = rng.randrange(2)
        rget = rng.randrange(2)
        din = rng.randrange(256)
        await _step(dut, model, rst=rst, wput=wput, din=din, rget=rget)
