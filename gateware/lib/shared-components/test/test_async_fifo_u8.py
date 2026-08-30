# top = tb_async_fifo_u8

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event
from cocotb.triggers import FallingEdge
from cocotb.triggers import First
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


DEPTH = 8
SYNC_STAGES = 3
ADDR_MASK = DEPTH - 1


class AlchitryAsyncFifoModel:
    """Behavioral model of Alchitry async_fifo.luc for WIDTH=8, ENTRIES=8."""

    def __init__(self):
        self.mem = [0] * DEPTH
        self.waddr = 0
        self.gwsync = 0
        self.wsync = [0] * SYNC_STAGES

        self.raddr = 0
        self.grsync = 0
        self.rsync = [0] * SYNC_STAGES

        self.read_data = 0

        self.queue: list[int] = []
        self.accepted_writes = 0
        self.accepted_reads = 0

    @staticmethod
    def _gray(value: int) -> int:
        return (value ^ (value >> 1)) & ADDR_MASK

    def _wrdy(self) -> bool:
        wnext = (self.waddr + 1) & ADDR_MASK
        return self._gray(wnext) != self.wsync[-1]

    def _rrdy(self) -> bool:
        return self._gray(self.raddr) != self.rsync[-1]

    def outputs(self) -> tuple[int, int, int]:
        full = int(not self._wrdy())
        empty = int(not self._rrdy())
        return full, empty, self.read_data & 0xFF

    def step_wclk(self, *, wrst: int, wput: int, din: int) -> bool:
        if wrst:
            self.waddr = 0
            self.gwsync = 0
            self.wsync = [0] * SYNC_STAGES
            return False

        old_waddr = self.waddr
        old_wsync = list(self.wsync)
        old_grsync = self.grsync

        wnext = (old_waddr + 1) & ADDR_MASK
        wrdy = self._gray(wnext) != old_wsync[-1]
        do_write = bool((wput & 1) and wrdy)

        self.gwsync = self._gray(old_waddr)
        self.wsync[0] = old_grsync
        for idx in range(1, SYNC_STAGES):
            self.wsync[idx] = old_wsync[idx - 1]

        if do_write:
            self.mem[old_waddr] = din & 0xFF
            self.queue.append(din & 0xFF)
            self.accepted_writes += 1
            self.waddr = wnext

        if len(self.queue) > DEPTH - 1:
            raise AssertionError("queue overflow in async fifo model")
        return do_write

    def step_rclk(self, *, rrst: int, rget: int) -> bool:
        old_raddr = self.raddr
        old_rsync = list(self.rsync)
        old_gwsync = self.gwsync
        old_read_data = self.read_data

        raddr_gray = self._gray(old_raddr)
        rrdy = raddr_gray != old_rsync[-1]
        do_read = bool((rget & 1) and rrdy)

        if rrst:
            self.raddr = 0
            self.grsync = 0
            self.rsync = [0] * SYNC_STAGES
            return False

        if rrdy and self.queue:
            if (old_read_data & 0xFF) != (self.queue[0] & 0xFF):
                raise AssertionError(
                    f"FWFT mismatch: dout=0x{old_read_data:02x} queue_head=0x{self.queue[0]:02x}"
                )

        # RAM output register update (FWFT path): always samples selected address.
        ram_raddr = (old_raddr + 1) & ADDR_MASK if do_read else old_raddr
        self.read_data = self.mem[ram_raddr]

        if do_read:
            if not self.queue:
                raise AssertionError("read accepted while queue empty")
            self.queue.pop(0)
            self.accepted_reads += 1
            self.raddr = (old_raddr + 1) & ADDR_MASK

        self.grsync = raddr_gray
        self.rsync[0] = old_gwsync
        for idx in range(1, SYNC_STAGES):
            self.rsync[idx] = old_rsync[idx - 1]

        if len(self.queue) > DEPTH - 1:
            raise AssertionError("queue overflow in async fifo model")
        return do_read


def _dut_u8(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0xFF


def _dut_bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


def _assert_matches(dut, model: AlchitryAsyncFifoModel) -> None:
    exp_full, exp_empty, exp_dout = model.outputs()

    got_full = _dut_bit(dut.full)
    got_empty = _dut_bit(dut.empty)

    assert got_full == exp_full, f"full mismatch expected={exp_full} got={got_full}"
    assert got_empty == exp_empty, f"empty mismatch expected={exp_empty} got={got_empty}"

    if exp_empty == 0:
        assert model.queue, "empty=0 but queue is empty"
        got_dout = _dut_u8(dut.dout)
        assert got_dout == exp_dout, f"dout mismatch expected=0x{exp_dout:02x} got=0x{got_dout:02x}"
        assert got_dout == (model.queue[0] & 0xFF)


async def _start_rclk_with_offset(signal, *, period_ns: int, delay_ns: int) -> None:
    await Timer(delay_ns, units="ns")
    await Clock(signal, period_ns, units="ns").start()


async def _monitor_edges(dut, model: AlchitryAsyncFifoModel, stop: Event) -> None:
    while True:
        w_edge = RisingEdge(dut.wclk)
        r_edge = RisingEdge(dut.rclk)
        stop_wait = stop.wait()

        fired = await First(w_edge, r_edge, stop_wait)
        if fired is stop_wait:
            return

        await Timer(1, units="ps")
        if fired is w_edge:
            model.step_wclk(
                wrst=_dut_bit(dut.wrst),
                wput=_dut_bit(dut.wput),
                din=_dut_u8(dut.din),
            )
        elif fired is r_edge:
            model.step_rclk(
                rrst=_dut_bit(dut.rrst),
                rget=_dut_bit(dut.rget),
            )
        else:
            raise AssertionError("unexpected trigger fired")

        _assert_matches(dut, model)


async def _wait_rise(signal, cycles: int) -> None:
    for _ in range(cycles):
        await RisingEdge(signal)
        await Timer(1, units="ps")


async def _pulse_write(dut, value: int) -> None:
    await FallingEdge(dut.wclk)
    dut.din.value = value & 0xFF
    dut.wput.value = 1

    await RisingEdge(dut.wclk)
    await Timer(1, units="ps")

    await FallingEdge(dut.wclk)
    dut.wput.value = 0


async def _pulse_read(dut) -> int:
    await FallingEdge(dut.rclk)
    observed = _dut_u8(dut.dout)
    dut.rget.value = 1

    await RisingEdge(dut.rclk)
    await Timer(1, units="ps")

    await FallingEdge(dut.rclk)
    dut.rget.value = 0
    return observed


async def _wait_flag(signal, expected: int, *, clock, timeout_cycles: int = 120) -> None:
    for _ in range(timeout_cycles):
        await RisingEdge(clock)
        await Timer(1, units="ps")
        if _dut_bit(signal) == expected:
            return
    raise AssertionError(f"timed out waiting for {signal._name}={expected}")


@cocotb.test()
async def async_fifo_u8_directed(dut):
    cocotb.start_soon(Clock(dut.wclk, 10, units="ns").start())
    cocotb.start_soon(_start_rclk_with_offset(dut.rclk, period_ns=14, delay_ns=1))

    dut.wrst.value = 1
    dut.rrst.value = 1
    dut.wput.value = 0
    dut.rget.value = 0
    dut.din.value = 0

    # Keep reset asserted long enough to fully clear both domains.
    await _wait_rise(dut.wclk, 6)
    await _wait_rise(dut.rclk, 6)

    model = AlchitryAsyncFifoModel()
    stop = Event()
    monitor = cocotb.start_soon(_monitor_edges(dut, model, stop))

    dut.wrst.value = 0
    dut.rrst.value = 0

    await _wait_rise(dut.wclk, 4)
    await _wait_rise(dut.rclk, 4)

    payloads = [0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77]
    for value in payloads:
        await _pulse_write(dut, value)

    # After DEPTH-1 writes the FIFO should report full.
    await _wait_flag(dut.full, 1, clock=dut.wclk)

    writes_before = model.accepted_writes
    await _pulse_write(dut, 0xEE)
    await _wait_rise(dut.wclk, 2)
    assert model.accepted_writes == writes_before

    observed: list[int] = []
    for _ in payloads:
        await _wait_flag(dut.empty, 0, clock=dut.rclk)
        observed.append(await _pulse_read(dut))

    assert observed == payloads, f"read order mismatch expected={payloads} got={observed}"

    await _wait_flag(dut.empty, 1, clock=dut.rclk)

    stop.set()
    await monitor


@cocotb.test()
async def async_fifo_u8_randomized_model_compat(dut):
    cocotb.start_soon(Clock(dut.wclk, 10, units="ns").start())
    cocotb.start_soon(_start_rclk_with_offset(dut.rclk, period_ns=14, delay_ns=1))

    dut.wrst.value = 1
    dut.rrst.value = 1
    dut.wput.value = 0
    dut.rget.value = 0
    dut.din.value = 0

    await _wait_rise(dut.wclk, 8)
    await _wait_rise(dut.rclk, 8)

    model = AlchitryAsyncFifoModel()
    stop = Event()
    monitor = cocotb.start_soon(_monitor_edges(dut, model, stop))

    dut.wrst.value = 0
    dut.rrst.value = 0

    rng = random.Random(0xA5F02026)
    for _ in range(900):
        await FallingEdge(dut.wclk)
        dut.wput.value = 1 if rng.randrange(100) < 62 else 0
        dut.din.value = rng.randrange(256)

        await FallingEdge(dut.rclk)
        dut.rget.value = 1 if rng.randrange(100) < 58 else 0

    dut.wput.value = 0

    # Drain phase: force reads until FIFO has had ample time to empty.
    for _ in range(180):
        await FallingEdge(dut.rclk)
        dut.rget.value = 1

    dut.rget.value = 0
    await _wait_flag(dut.empty, 1, clock=dut.rclk)

    # Sanity: test did real work in both directions.
    assert model.accepted_writes > 100
    assert model.accepted_reads > 100
    assert not model.queue

    stop.set()
    await monitor
