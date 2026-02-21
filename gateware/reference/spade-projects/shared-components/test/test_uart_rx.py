# top = tb_uart_rx

import random

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


BIT_TIME = 10


def _odd_parity(byte: int) -> int:
    return bin(byte & 0xFF).count("1") & 1


class AlchitryUartRxModel:
    IDLE = 0
    WAIT_HALF = 1
    WAIT_FULL = 2
    WAIT_HIGH = 3

    def __init__(self, bit_time: int):
        self.bit_time = bit_time
        self.reset()

    def reset(self):
        self.state = self.IDLE
        self.ctr = 0
        self.bit_ctr = 0
        self.saved_data = 0
        self.new_data = 0
        # Mirrors `rxd[3]` shift chain and sampling on `rxd.q[-1]`.
        self.rxd0 = 1
        self.rxd1 = 1
        self.rxd2 = 1

    def step(self, *, rst: int, rx: int) -> tuple[int, int]:
        if rst:
            self.reset()
            return 0, self.saved_data

        old_rxd0 = self.rxd0
        old_rxd1 = self.rxd1
        old_rxd2 = self.rxd2
        sampled = old_rxd2

        next_state = self.state
        next_ctr = self.ctr
        next_bit_ctr = self.bit_ctr
        next_saved_data = self.saved_data
        next_new_data = 0

        if self.state == self.IDLE:
            next_bit_ctr = 0
            next_ctr = 0
            if sampled == 0:
                next_state = self.WAIT_HALF
        elif self.state == self.WAIT_HALF:
            next_ctr = self.ctr + 1
            if self.ctr == (self.bit_time >> 1):
                next_ctr = 0
                next_state = self.WAIT_FULL
        elif self.state == self.WAIT_FULL:
            next_ctr = self.ctr + 1
            if self.ctr == self.bit_time - 1:
                next_saved_data = ((sampled & 1) << 7) | ((self.saved_data >> 1) & 0x7F)
                next_bit_ctr = (self.bit_ctr + 1) & 0x7
                next_ctr = 0
                if self.bit_ctr == 7:
                    next_state = self.WAIT_HIGH
                    next_new_data = 1
        elif self.state == self.WAIT_HIGH:
            if sampled == 1:
                next_state = self.IDLE

        self.state = next_state
        self.ctr = next_ctr
        self.bit_ctr = next_bit_ctr
        self.saved_data = next_saved_data
        self.new_data = next_new_data
        self.rxd0 = rx & 1
        self.rxd1 = old_rxd0
        self.rxd2 = old_rxd1

        return self.new_data, self.saved_data


async def _init_test(dut, stop_bits: int, parity: int):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.rx_line.value = 1
    dut.bit_time.value = BIT_TIME
    dut.parity.value = parity
    dut.stop_bits.value = stop_bits

    await tick(dut.clk, 2)
    dut.rst.value = 0
    await tick(dut.clk, BIT_TIME)


async def _tick_and_capture(dut, cycles: int, events: list[tuple[int, int]]):
    for _ in range(cycles):
        await tick(dut.clk, 1)
        if int(dut.rx_valid.value) == 1:
            events.append((int(dut.rx_parity_error.value), int(dut.rx_byte.value)))


async def _drive_bit(dut, bit: int, events: list[tuple[int, int]]):
    dut.rx_line.value = bit
    await _tick_and_capture(dut, BIT_TIME, events)


async def _send_frame(
    dut,
    payload: int,
    events: list[tuple[int, int]],
    parity_enabled: bool,
    stop_bits: int,
    parity_bit: int | None = None,
):
    await _drive_bit(dut, 0, events)
    for bit_idx in range(8):
        await _drive_bit(dut, (payload >> bit_idx) & 1, events)

    if parity_enabled:
        bit = _odd_parity(payload) if parity_bit is None else parity_bit
        await _drive_bit(dut, bit, events)

    for _ in range(stop_bits):
        await _drive_bit(dut, 1, events)


@cocotb.test()
async def test(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    events: list[tuple[int, int]] = []
    await _tick_and_capture(dut, BIT_TIME * 2, events)
    assert events == []

    payload = 0x0A
    await _send_frame(dut, payload, events, parity_enabled=False, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)
    assert events == [(0, payload)]


@cocotb.test()
async def quick_succession_works(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(dut, first, events, parity_enabled=False, stop_bits=1)
    await _send_frame(dut, second, events, parity_enabled=False, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, first), (0, second)]


@cocotb.test()
async def correct_parity(dut):
    await _init_test(dut, stop_bits=1, parity=1)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(dut, first, events, parity_enabled=True, stop_bits=1)
    await _send_frame(dut, second, events, parity_enabled=True, stop_bits=1)
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(0, first), (0, second)]


@cocotb.test()
async def incorrect_parity(dut):
    await _init_test(dut, stop_bits=1, parity=1)
    events: list[tuple[int, int]] = []

    first = 0x0A
    second = 0x2A
    await _send_frame(
        dut,
        first,
        events,
        parity_enabled=True,
        stop_bits=1,
        parity_bit=_odd_parity(first) ^ 1,
    )
    await _send_frame(
        dut,
        second,
        events,
        parity_enabled=True,
        stop_bits=1,
        parity_bit=_odd_parity(second) ^ 1,
    )
    await _tick_and_capture(dut, BIT_TIME, events)

    assert events == [(1, first), (1, second)]


@cocotb.test()
async def multiple_stop_bits_work(dut):
    await _init_test(dut, stop_bits=2, parity=0)
    events: list[tuple[int, int]] = []

    payload = 0x0A
    await _send_frame(dut, payload, events, parity_enabled=False, stop_bits=2)
    await _tick_and_capture(dut, BIT_TIME, events)
    assert events == [(0, payload)]

    await _tick_and_capture(dut, BIT_TIME * 4, events)
    assert events == [(0, payload)]


@cocotb.test()
async def alchitry_compat_no_parity_randomized(dut):
    bit_time = 10
    await _init_test(dut, stop_bits=1, parity=0)
    dut.bit_time.value = bit_time

    model = AlchitryUartRxModel(bit_time=bit_time)
    rng = random.Random(0x7788EE)

    # Mirror reset history used in _init_test.
    model.step(rst=1, rx=1)
    model.step(rst=1, rx=1)
    for _ in range(bit_time):
        model.step(rst=0, rx=1)

    line_levels: list[int] = []
    line_levels.extend([1] * (bit_time * 3))
    for _ in range(40):
        mode = rng.randrange(4)
        if mode == 0:
            # Valid 8N1 frame.
            payload = rng.randrange(256)
            line_levels.extend([0] * bit_time)
            for bit_idx in range(8):
                line_levels.extend([((payload >> bit_idx) & 1)] * bit_time)
            line_levels.extend([1] * bit_time)
        elif mode == 1:
            # Bad-stop frame: stop held low, then random low run.
            payload = rng.randrange(256)
            line_levels.extend([0] * bit_time)
            for bit_idx in range(8):
                line_levels.extend([((payload >> bit_idx) & 1)] * bit_time)
            line_levels.extend([0] * bit_time)
            line_levels.extend([0] * (rng.randrange(1, 3) * bit_time))
            line_levels.extend([1] * bit_time)
        elif mode == 2:
            line_levels.extend([1] * (rng.randrange(1, 3) * bit_time))
        else:
            line_levels.extend([rng.randrange(2) for _ in range(rng.randrange(1, bit_time))])

    for cycle, level in enumerate(line_levels):
        dut.rx_line.value = level
        await tick(dut.clk, 1)
        exp_valid, exp_data = model.step(rst=0, rx=level)
        dut_valid = int(dut.rx_valid.value)
        dut_byte = int(dut.rx_byte.value)
        dut_parity_error = int(dut.rx_parity_error.value)
        assert dut_valid == exp_valid, (
            f"valid mismatch at cycle={cycle} rx={level} "
            f"expected={exp_valid} got={dut_valid} "
            f"exp_data=0x{exp_data:02x} dut_data=0x{dut_byte:02x}"
        )
        if dut_valid:
            assert dut_parity_error == 0
            assert dut_byte == exp_data, (
                f"byte mismatch at cycle={cycle} rx={level} "
                f"expected=0x{exp_data:02x} got=0x{dut_byte:02x}"
            )
