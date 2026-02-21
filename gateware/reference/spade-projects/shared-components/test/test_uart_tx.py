# top = tb_uart_tx

import random

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


BIT_TIME = 6


def _odd_parity(byte: int) -> int:
    return bin(byte & 0xFF).count("1") & 1


class AlchitryUartTxModel:
    IDLE = 0
    START = 1
    DATA = 2
    STOP = 3

    def __init__(self, bit_time: int):
        self.bit_time = bit_time
        self.reset()

    def reset(self):
        self.state = self.IDLE
        self.ctr = 0
        self.bit_ctr = 0
        self.saved_data = 0
        self.tx_reg = 1

    def step(self, *, rst: int, new_data: int, data: int) -> tuple[int, int]:
        if rst:
            self.reset()
        else:
            next_state = self.state
            next_ctr = self.ctr
            next_bit_ctr = self.bit_ctr
            next_saved_data = self.saved_data
            next_tx_reg = self.tx_reg

            if self.state == self.IDLE:
                next_tx_reg = 1
                next_bit_ctr = 0
                next_ctr = 0
                if new_data:
                    next_saved_data = data & 0xFF
                    next_state = self.START
            elif self.state == self.START:
                next_ctr = self.ctr + 1
                next_tx_reg = 0
                if self.ctr == self.bit_time - 1:
                    next_ctr = 0
                    next_state = self.DATA
            elif self.state == self.DATA:
                next_tx_reg = (self.saved_data >> self.bit_ctr) & 1
                next_ctr = self.ctr + 1
                if self.ctr == self.bit_time - 1:
                    next_ctr = 0
                    next_bit_ctr = (self.bit_ctr + 1) & 0x7
                    if self.bit_ctr == 7:
                        next_state = self.STOP
            elif self.state == self.STOP:
                next_tx_reg = 1
                next_ctr = self.ctr + 1
                if self.ctr == self.bit_time - 1:
                    next_state = self.IDLE

            self.state = next_state
            self.ctr = next_ctr
            self.bit_ctr = next_bit_ctr
            self.saved_data = next_saved_data
            self.tx_reg = next_tx_reg

        busy = 0 if self.state == self.IDLE else 1
        return self.tx_reg, (0 if busy else 1)


async def _init_test(dut, stop_bits: int, parity: int):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.send.value = 0
    dut.data_byte.value = 0
    dut.bit_time.value = BIT_TIME
    dut.parity.value = parity
    dut.stop_bits.value = stop_bits

    await tick(dut.clk, 2)
    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_ready.value) == 1

    dut.rst.value = 0
    await tick(dut.clk, 1)


async def _check_next_bit(dut, expected: int):
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_line.value) == expected


async def _check_transmission(dut, payload: int):
    dut.data_byte.value = payload
    dut.send.value = 1
    await tick(dut.clk, 1)
    dut.send.value = 0

    # Alchitry semantics: tx is registered, so start bit appears one cycle
    # after the send pulse is accepted.
    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_ready.value) == 0

    await _check_next_bit(dut, 0)
    for bit_idx in range(8):
        await _check_next_bit(dut, (payload >> bit_idx) & 1)
        assert int(dut.tx_ready.value) == 0


@cocotb.test()
async def simple_tx_test(dut):
    await _init_test(dut, stop_bits=1, parity=0)
    await _check_transmission(dut, 0x35)
    await _check_next_bit(dut, 1)
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_ready.value) == 1


@cocotb.test()
async def simple_tx_test_with_2_stop_bits(dut):
    await _init_test(dut, stop_bits=2, parity=0)
    await _check_transmission(dut, 0x35)
    await _check_next_bit(dut, 1)
    await _check_next_bit(dut, 1)
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_ready.value) == 1


@cocotb.test()
async def even_parity_bit_works(dut):
    payload = 0x35  # 4 set bits => odd parity bit is 0
    await _init_test(dut, stop_bits=1, parity=1)
    await _check_transmission(dut, payload)
    await _check_next_bit(dut, _odd_parity(payload))
    await _check_next_bit(dut, 1)
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_ready.value) == 1


@cocotb.test()
async def odd_parity_bit_works(dut):
    payload = 0x75  # 5 set bits => odd parity bit is 1
    await _init_test(dut, stop_bits=1, parity=1)
    await _check_transmission(dut, payload)
    await _check_next_bit(dut, _odd_parity(payload))
    await _check_next_bit(dut, 1)
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_ready.value) == 1


@cocotb.test()
async def even_parity_bit_with_multiple_stop_bit_works(dut):
    payload = 0x35
    await _init_test(dut, stop_bits=2, parity=1)
    await _check_transmission(dut, payload)
    await _check_next_bit(dut, _odd_parity(payload))
    await _check_next_bit(dut, 1)
    await _check_next_bit(dut, 1)
    await tick(dut.clk, BIT_TIME)
    assert int(dut.tx_ready.value) == 1


@cocotb.test()
async def alchitry_compat_no_parity_randomized(dut):
    bit_time = 7
    await _init_test(dut, stop_bits=1, parity=0)
    dut.bit_time.value = bit_time

    model = AlchitryUartTxModel(bit_time=bit_time)
    rng = random.Random(0x55AACC)

    # Mirror reset history used above so model and DUT start aligned.
    model.step(rst=1, new_data=0, data=0)
    model.step(rst=1, new_data=0, data=0)
    model.step(rst=0, new_data=0, data=0)

    for cycle in range(600):
        send = rng.randrange(2)
        data = rng.randrange(256)
        dut.send.value = send
        dut.data_byte.value = data
        await tick(dut.clk, 1)

        exp_tx, exp_ready = model.step(rst=0, new_data=send, data=data)
        got_tx = int(dut.tx_line.value)
        got_ready = int(dut.tx_ready.value)
        assert got_tx == exp_tx, (
            f"tx mismatch at cycle={cycle} send={send} data=0x{data:02x} "
            f"expected={exp_tx} got={got_tx}"
        )
        assert got_ready == exp_ready, (
            f"ready mismatch at cycle={cycle} send={send} data=0x{data:02x} "
            f"expected={exp_ready} got={got_ready}"
        )
