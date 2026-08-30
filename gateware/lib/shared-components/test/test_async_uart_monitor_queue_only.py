# top = tb_async_uart_monitor_queue_only

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Event
from cocotb.triggers import FallingEdge
from cocotb.triggers import First
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def _bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


def _u8(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0xFF


def _assert_equivalent(dut) -> None:
    for suffix in ("line", "busy", "full", "empty"):
        monitor_value = _bit(getattr(dut, f"monitor_{suffix}"))
        bridge_value = _bit(getattr(dut, f"bridge_{suffix}"))
        assert bridge_value == monitor_value, (
            f"{suffix} mismatch: monitor={monitor_value} bridge={bridge_value}"
        )

    if _bit(dut.monitor_empty) == 0:
        monitor_dout = _u8(dut.monitor_dout)
        bridge_dout = _u8(dut.bridge_dout)
        assert bridge_dout == monitor_dout, (
            f"dout mismatch: monitor=0x{monitor_dout:02x} bridge=0x{bridge_dout:02x}"
        )

    assert _bit(dut.bridge_dropped) == 0
    assert _u8(dut.bridge_dropped_count) == 0


async def _start_rclk_with_offset(signal) -> None:
    await Timer(1, units="ns")
    await Clock(signal, 14, units="ns").start()


async def _monitor_equivalence(dut, stop: Event, observations: dict[str, bool]) -> None:
    while True:
        w_edge = RisingEdge(dut.wclk)
        r_edge = RisingEdge(dut.rclk)
        stop_wait = stop.wait()
        fired = await First(w_edge, r_edge, stop_wait)
        if fired is stop_wait:
            return

        await Timer(1, units="ps")
        _assert_equivalent(dut)
        observations["busy"] |= bool(_bit(dut.bridge_busy))
        observations["start_bit"] |= _bit(dut.bridge_line) == 0
        observations["full"] |= bool(_bit(dut.bridge_full))


async def _wait_rising(signal, count: int) -> None:
    for _ in range(count):
        await RisingEdge(signal)
        await Timer(1, units="ps")


@cocotb.test()
async def queue_only_bridge_matches_async_uart_monitor_cycle_for_cycle(dut):
    cocotb.start_soon(Clock(dut.wclk, 10, units="ns").start())
    cocotb.start_soon(_start_rclk_with_offset(dut.rclk))

    dut.wrst.value = 1
    dut.rrst.value = 1
    dut.din.value = 0
    dut.wput.value = 0
    await _wait_rising(dut.wclk, 8)
    await _wait_rising(dut.rclk, 8)

    dut.wrst.value = 0
    dut.rrst.value = 0
    await _wait_rising(dut.wclk, 6)
    await _wait_rising(dut.rclk, 6)
    _assert_equivalent(dut)

    observations = {"busy": False, "start_bit": False, "full": False}
    stop = Event()
    monitor = cocotb.start_soon(_monitor_equivalence(dut, stop, observations))

    # Exercise accepted writes, full handling, and changing data while full. The
    # two implementations own separate FIFOs, so equality here characterizes the
    # complete FIFO-to-UART composition rather than only the UART waveform.
    rng = random.Random(0xA51C_2026)
    for _ in range(180):
        await FallingEdge(dut.wclk)
        dut.wput.value = 1 if rng.randrange(100) < 72 else 0
        dut.din.value = rng.randrange(256)

    await FallingEdge(dut.wclk)
    dut.wput.value = 0

    # Four-entry Alchitry-style FIFOs have three usable slots. Allow enough read
    # clock cycles for all accepted bytes and their UART frames to drain.
    await _wait_rising(dut.rclk, 360)
    assert _bit(dut.bridge_empty) == 1
    assert _bit(dut.bridge_busy) == 0

    stop.set()
    await monitor

    assert observations["busy"], "expected at least one byte to enter the UART"
    assert observations["start_bit"], "expected at least one UART start bit"
    assert observations["full"], "expected the write-side FIFO to reach full"
