# top = tb_bus_debug

import itertools
import random

import cocotb
from cocotb.triggers import Timer


async def _settle():
    await Timer(1, units="ns")


def _bit(value: int, index: int) -> int:
    return (value >> index) & 1


def _packed_bits(bits: list[int]) -> int:
    return sum(bit << index for index, bit in enumerate(bits))


def _set_defaults(dut) -> None:
    dut.addr.value = 0
    dut.data.value = 0
    dut.event_code.value = 0
    dut.overflow_count.value = 0
    dut.saleae_mode.value = 0
    dut.saleae_inputs.value = 0
    dut.saleae_counter.value = 0
    dut.overflow_ft_enabled.value = 0
    dut.overflow_fifo_full.value = 0
    dut.overflow_rd_rise.value = 0
    dut.overflow_wr_rise.value = 0


@cocotb.test()
async def event_and_overflow_words_preserve_every_field(dut):
    _set_defaults(dut)
    rng = random.Random(0xB05D_EB06)
    vectors = [
        (0x0000, 0x00, 0x00, 0x000000),
        (0x1234, 0xA5, ord("R"), 0x0ABCDE),
        (0xFFFF, 0xFF, 0xFF, 0xFFFFFF),
    ]
    vectors.extend(
        (
            rng.randrange(1 << 16),
            rng.randrange(1 << 8),
            rng.randrange(1 << 8),
            rng.randrange(1 << 24),
        )
        for _ in range(128)
    )

    for addr, data, event_code, overflow_count in vectors:
        dut.addr.value = addr
        dut.data.value = data
        dut.event_code.value = event_code
        dut.overflow_count.value = overflow_count
        await _settle()

        assert int(dut.event_word.value) == (addr << 16) | (data << 8) | event_code
        assert int(dut.overflow_word.value) == (overflow_count << 8) | event_code


@cocotb.test()
async def saleae_mux_maps_every_mode_and_signal(dut):
    _set_defaults(dut)
    rng = random.Random(0x5A1E_AE00)
    patterns = [0x0000, 0xFFFF, 0xA5C3, 0x5A3C]
    patterns.extend(rng.randrange(1 << 16) for _ in range(64))

    for signals in patterns:
        dut.saleae_inputs.value = signals
        counter = rng.randrange(1 << 8)
        dut.saleae_counter.value = counter
        expected_by_mode = (
            [
                _bit(signals, 0),
                _bit(signals, 1),
                _bit(signals, 2),
                _bit(signals, 3),
                _bit(signals, 4),
                _bit(signals, 13),
                _bit(signals, 14),
                _bit(signals, 15),
            ],
            [
                _bit(signals, 5),
                _bit(signals, 6),
                _bit(signals, 8),
                _bit(signals, 4),
                _bit(signals, 0),
                _bit(signals, 1),
                _bit(signals, 2),
                _bit(signals, 3),
            ],
            [
                _bit(signals, 5),
                _bit(signals, 6),
                _bit(signals, 7),
                _bit(signals, 8),
                _bit(signals, 0),
                _bit(signals, 1),
                _bit(signals, 2),
                _bit(signals, 3),
            ],
            [
                _bit(signals, 9),
                _bit(signals, 10),
                _bit(signals, 11),
                _bit(signals, 12),
                _bit(signals, 0),
                _bit(signals, 1),
                _bit(signals, 2),
                _bit(signals, 3),
            ],
            [_bit(counter, index) for index in range(8)],
        )

        for mode, expected_bits in enumerate(expected_by_mode):
            dut.saleae_mode.value = mode
            await _settle()
            assert int(dut.saleae_out.value) == _packed_bits(expected_bits)


@cocotb.test()
async def overflow_emission_matches_the_full_guard_truth_table(dut):
    _set_defaults(dut)

    for count in (0, 1, 0xFFFFFF):
        dut.overflow_count.value = count
        for ft_enabled, fifo_full, rd_rise, wr_rise in itertools.product((0, 1), repeat=4):
            dut.overflow_ft_enabled.value = ft_enabled
            dut.overflow_fifo_full.value = fifo_full
            dut.overflow_rd_rise.value = rd_rise
            dut.overflow_wr_rise.value = wr_rise
            await _settle()

            expected = (
                not rd_rise
                and not wr_rise
                and ft_enabled
                and not fifo_full
                and count > 0
            )
            assert int(dut.should_emit_overflow.value) == int(expected)
