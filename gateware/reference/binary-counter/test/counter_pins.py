# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


BIT_CYCLES = 100


def read_u8(signal):
    return int(signal.value) & 0xFF


class AlchitryUartRxModel:
    IDLE = 0
    WAIT_HALF = 1
    WAIT_FULL = 2
    WAIT_HIGH = 3

    def __init__(self, bit_time: int):
        self.bit_time = bit_time
        self.rxd0 = 1
        self.rxd1 = 1
        self.rxd2 = 1
        self.state = self.IDLE
        self.ctr = 0
        self.bit_ctr = 0
        self.saved_data = 0

    def step(self, rx: int) -> tuple[int, int]:
        sampled = self.rxd2
        new_data = 0

        if self.state == self.IDLE:
            self.bit_ctr = 0
            self.ctr = 0
            if sampled == 0:
                self.state = self.WAIT_HALF
        elif self.state == self.WAIT_HALF:
            self.ctr += 1
            if self.ctr == (self.bit_time >> 1):
                self.ctr = 0
                self.state = self.WAIT_FULL
        elif self.state == self.WAIT_FULL:
            self.ctr += 1
            if self.ctr == self.bit_time - 1:
                self.saved_data = ((sampled & 1) << 7) | ((self.saved_data >> 1) & 0x7F)
                self.bit_ctr = (self.bit_ctr + 1) & 0x7
                self.ctr = 0
                if self.bit_ctr == 0:
                    self.state = self.WAIT_HIGH
                    new_data = 1
        elif self.state == self.WAIT_HIGH:
            if sampled == 1:
                self.state = self.IDLE

        self.rxd2 = self.rxd1
        self.rxd1 = self.rxd0
        self.rxd0 = rx & 1
        return new_data, self.saved_data


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


async def send_uart_byte(dut, value):
    dut.usb_rx.value = 1
    await tick(dut.clk, BIT_CYCLES)

    dut.usb_rx.value = 0
    await tick(dut.clk, BIT_CYCLES)

    for bit_idx in range(8):
        dut.usb_rx.value = (value >> bit_idx) & 1
        await tick(dut.clk, BIT_CYCLES)

    dut.usb_rx.value = 1
    await tick(dut.clk, BIT_CYCLES)


async def recv_uart_byte(dut, timeout_cycles=BIT_CYCLES * 50):
    model = AlchitryUartRxModel(bit_time=BIT_CYCLES)
    for _ in range(timeout_cycles):
        await tick(dut.clk, 1)
        valid, value = model.step(int(dut.usb_tx.value))
        if valid:
            return value

    assert False, "timed out waiting for uart echo"


async def assert_no_uart_echo(dut, cycles):
    model = AlchitryUartRxModel(bit_time=BIT_CYCLES)
    for _ in range(cycles):
        await tick(dut.clk, 1)
        valid, _ = model.step(int(dut.usb_tx.value))
        assert valid == 0, "unexpected uart tx byte"


async def wait_for_tx_idle_high(dut, cycles=16, max_cycles=500):
    seen = 0
    for _ in range(max_cycles):
        await tick(dut.clk, 1)
        if int(dut.usb_tx.value) == 1:
            seen += 1
            if seen >= cycles:
                return
        else:
            seen = 0
    assert False, "timed out waiting for idle-high usb_tx"


async def measure_led_change_intervals(dut, count, max_cycles, skip_first=True):
    intervals = []
    last_led = read_u8(dut.led)
    since_last = 0

    for _ in range(max_cycles):
        await tick(dut.clk, 1)
        since_last += 1

        led = read_u8(dut.led)
        saleae = read_u8(dut.saleae)
        assert led == saleae, f"saleae must mirror led (led=0x{led:02x}, saleae=0x{saleae:02x})"

        if led != last_led:
            if skip_first:
                skip_first = False
            else:
                intervals.append(since_last)
            since_last = 0
            last_led = led
            if len(intervals) == count:
                break

    assert len(intervals) == count, f"only saw {len(intervals)} led transitions, expected {count}"
    return intervals


@cocotb.test()
async def uart_digit_controls_led_saleae_slow_factor(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 8)

    assert read_u8(dut.led) == 0
    assert read_u8(dut.saleae) == 0

    dut.rst_n.value = 1
    await wait_for_tx_idle_high(dut)

    fast_intervals = await measure_led_change_intervals(dut, count=8, max_cycles=40)
    assert fast_intervals == [1] * 8, f"default slowdown should be 0, got intervals {fast_intervals}"

    echo_task = cocotb.start_soon(recv_uart_byte(dut))
    await send_uart_byte(dut, ord("3"))
    echoed = await echo_task
    assert echoed == ord("3"), f"expected echo '3', got 0x{echoed:02x}"

    slow_intervals = await measure_led_change_intervals(dut, count=6, max_cycles=120)
    assert slow_intervals == [8] * 6, f"slow factor 3 should update every 8 cycles, got {slow_intervals}"

    await wait_for_tx_idle_high(dut, cycles=BIT_CYCLES)
    echo_task = cocotb.start_soon(recv_uart_byte(dut))
    await send_uart_byte(dut, ord("0"))
    echoed = await echo_task
    assert echoed == ord("0"), f"expected echo '0', got 0x{echoed:02x}"

    fast_again = await measure_led_change_intervals(dut, count=8, max_cycles=40)
    assert fast_again == [1] * 8, f"slow factor 0 should update every cycle, got {fast_again}"


@cocotb.test()
async def non_digit_is_ignored_and_not_echoed(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await wait_for_tx_idle_high(dut)

    baseline = await measure_led_change_intervals(dut, count=6, max_cycles=30)
    assert baseline == [1] * 6

    await send_uart_byte(dut, ord("x"))
    await assert_no_uart_echo(dut, BIT_CYCLES * 14)

    after = await measure_led_change_intervals(dut, count=6, max_cycles=30)
    assert after == [1] * 6
