# top = tb_uart_tx

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


BIT_TIME = 6


def _odd_parity(byte: int) -> int:
    return bin(byte & 0xFF).count("1") & 1


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

    assert int(dut.tx_line.value) == 0
    assert int(dut.tx_ready.value) == 0

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
