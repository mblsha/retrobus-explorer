# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


READ_READY = 3
READ_HOLD_DATA = 4
STREAM_READY = 0
STREAM_DONE = 5
ROM_BANK_SIZE = 0x4000


def _u(signal, mask: int) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & mask


def _set_ft_bus_z(dut) -> None:
    dut.ft_data_host.value = 0
    dut.ft_be_host.value = 0
    dut.ft_host_drive.value = 0


async def _tick(signal, cycles: int = 1) -> None:
    for _ in range(cycles):
        await RisingEdge(signal)
        await Timer(1, units="ps")


async def _init(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.ft_clk, 8, units="ns").start())

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    _set_ft_bus_z(dut)

    dut.z80_mreq.value = 1
    dut.z80_m1.value = 1
    dut.z80_ioreset.value = 0
    dut.z80_iorq.value = 1
    dut.z80_int1.value = 0
    dut.z80_wait.value = 1
    dut.z80_rd.value = 1
    dut.z80_wr.value = 1
    dut.addr.value = 0x8000
    dut.addr_bnk.value = 0
    dut.addr_ceram2.value = 1
    dut.addr_cerom2.value = 1

    await _tick(dut.clk, 8)
    dut.rst_n.value = 1
    await _tick(dut.clk, 16)


async def _expect_ft_request(dut, expected: int, timeout_cycles: int = 40000) -> None:
    dut.ft_txe.value = 0
    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_write = (
            _u(dut.ft_oe, 1) == 1
            and _u(dut.ft_wr, 1) == 0
            and _u(dut.ft_txe, 1) == 0
        )
        word = _u(dut.ft_data_drive, 0xFFFF)
        be = _u(dut.ft_be_drive, 0x3)
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_write:
            dut.ft_txe.value = 1
            assert (word, be) == (expected, 0b11)
            return
    raise AssertionError(f"timeout waiting for FT request {expected}")


async def _feed_ft_words(dut, words: list[int]) -> None:
    assert words
    dut.ft_txe.value = 1
    dut.ft_host_drive.value = 1
    dut.ft_rxf.value = 0
    dut.ft_data_host.value = words[0] & 0xFFFF
    dut.ft_be_host.value = 0b11

    index = 0
    timeout_cycles = max(4000, len(words) * 8)
    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_read = (
            _u(dut.ft_oe, 1) == 0
            and _u(dut.ft_rd, 1) == 0
            and _u(dut.ft_rxf, 1) == 0
        )
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_read:
            index += 1
            if index == len(words):
                dut.ft_rxf.value = 1
                _set_ft_bus_z(dut)
                return
            dut.ft_data_host.value = words[index] & 0xFFFF
    raise AssertionError(f"FT accepted only {index}/{len(words)} words")


async def _wait_debug_state(
    dut,
    *,
    read_state: int | None = None,
    stream_state: int | None = None,
    timeout_cycles: int = 50000,
) -> None:
    for _ in range(timeout_cycles):
        read_ok = read_state is None or _u(dut.read_state_debug, 0x7) == read_state
        stream_ok = stream_state is None or _u(dut.streaming_state_debug, 0x7) == stream_state
        if read_ok and stream_ok:
            return
        await _tick(dut.clk)
    raise AssertionError(
        "timeout waiting for states "
        f"read={read_state} stream={stream_state}; got "
        f"read={_u(dut.read_state_debug, 0x7)} "
        f"stream={_u(dut.streaming_state_debug, 0x7)}"
    )


async def _load_initial_banks(dut, bank0_words: list[int], bank1_words: list[int]) -> None:
    await _expect_ft_request(dut, 0)
    await _feed_ft_words(dut, [len(bank0_words) * 2, *bank0_words])
    await _expect_ft_request(dut, 1)
    await _feed_ft_words(dut, [len(bank1_words) * 2, *bank1_words])
    await _wait_debug_state(dut, read_state=READ_READY, stream_state=STREAM_READY)


async def _start_rom_read(dut, *, bank: int, offset: int) -> None:
    dut.addr.value = 0x8000 + offset
    dut.addr_bnk.value = bank
    dut.addr_cerom2.value = 0
    dut.z80_rd.value = 0
    dut.z80_mreq.value = 0
    await _wait_debug_state(dut, read_state=READ_HOLD_DATA, timeout_cycles=64)
    # The legacy RAM is synchronous. HOLD_DATA presents the latched address for
    # a full clock before its byte is available.
    await _tick(dut.clk, 2)
    assert _u(dut.data_oe_debug, 1) == 1


async def _finish_rom_read(dut) -> None:
    dut.z80_mreq.value = 1
    dut.z80_rd.value = 1
    dut.addr_cerom2.value = 1
    await _wait_debug_state(dut, read_state=READ_READY, timeout_cycles=64)
    assert _u(dut.data_oe_debug, 1) == 0


async def _read_byte(dut, *, bank: int, offset: int) -> int:
    await _start_rom_read(dut, bank=bank, offset=offset)
    value = _u(dut.data_drive_debug, 0xFF)
    await _finish_rom_read(dut)
    return value


@cocotb.test()
async def initial_fill_requests_zero_then_one_and_uses_size_word(dut):
    await _init(dut)

    await _expect_ft_request(dut, 0)
    await _feed_ft_words(dut, [2, 0xBBAA])
    await _expect_ft_request(dut, 1)
    await _feed_ft_words(dut, [0])
    await _wait_debug_state(dut, read_state=READ_READY, stream_state=STREAM_READY)

    assert await _read_byte(dut, bank=0, offset=0) == 0xAA
    assert await _read_byte(dut, bank=0, offset=1) == 0xBB
    assert _u(dut.request_count_debug, 0xFFFF) == 2


@cocotb.test()
async def loader_writes_low_then_high_bytes_into_distinct_16k_banks(dut):
    await _init(dut)
    await _load_initial_banks(dut, [0x2211, 0x4433], [0x6655, 0x8877])

    assert [await _read_byte(dut, bank=0, offset=i) for i in range(4)] == [
        0x11,
        0x22,
        0x33,
        0x44,
    ]
    assert [await _read_byte(dut, bank=1, offset=i) for i in range(4)] == [
        0x55,
        0x66,
        0x77,
        0x88,
    ]


@cocotb.test()
async def active_bank_reads_refill_the_other_bank_and_alternate_request_ids(dut):
    await _init(dut)
    await _load_initial_banks(dut, [0x1001], [0x2002])

    # Bank 1 is the most recently filled bank. Reading it switches the loader
    # to bank 0 and emits request id 2 without disturbing the held old byte.
    await _start_rom_read(dut, bank=1, offset=0)
    assert _u(dut.data_drive_debug, 0xFF) == 0x02
    await _finish_rom_read(dut)
    await _expect_ft_request(dut, 2)
    assert _u(dut.streaming_bank_debug, 0x3) == 0
    await _feed_ft_words(dut, [2, 0xA1A0])
    await _wait_debug_state(dut, stream_state=STREAM_DONE)

    # Reading newly refilled bank 0 flips the refill target back to bank 1.
    await _start_rom_read(dut, bank=0, offset=0)
    assert _u(dut.data_drive_debug, 0xFF) == 0xA0
    await _finish_rom_read(dut)
    await _expect_ft_request(dut, 3)
    assert _u(dut.streaming_bank_debug, 0x3) == 1
    await _feed_ft_words(dut, [2, 0xB1B0])
    await _wait_debug_state(dut, stream_state=STREAM_DONE)

    assert await _read_byte(dut, bank=0, offset=1) == 0xA1
    assert await _read_byte(dut, bank=1, offset=0) == 0xB0


@cocotb.test()
async def hold_data_latches_bank_and_address_until_mreq_rises(dut):
    await _init(dut)
    await _load_initial_banks(dut, [0x2211], [0x4433])

    await _start_rom_read(dut, bank=0, offset=1)
    assert _u(dut.data_drive_debug, 0xFF) == 0x22

    dut.addr.value = 0x8000
    dut.addr_bnk.value = 1
    await _tick(dut.clk, 12)
    assert _u(dut.read_state_debug, 0x7) == READ_HOLD_DATA
    assert _u(dut.data_oe_debug, 1) == 1
    assert _u(dut.data_drive_debug, 0xFF) == 0x22

    await _finish_rom_read(dut)


@cocotb.test()
async def each_bank_preserves_the_first_and_last_bytes_of_its_16k_window(dut):
    await _init(dut)

    bank0 = [
        (((index * 7 + 1) & 0xFF) << 8) | ((index * 7) & 0xFF)
        for index in range(ROM_BANK_SIZE // 2)
    ]
    bank1 = [
        (((index * 11 + 0x81) & 0xFF) << 8) | ((index * 11 + 0x80) & 0xFF)
        for index in range(ROM_BANK_SIZE // 2)
    ]
    await _load_initial_banks(dut, bank0, bank1)

    assert await _read_byte(dut, bank=0, offset=0) == 0x00
    assert await _read_byte(dut, bank=0, offset=1) == 0x01
    assert await _read_byte(dut, bank=0, offset=ROM_BANK_SIZE - 2) == (bank0[-1] & 0xFF)
    assert await _read_byte(dut, bank=0, offset=ROM_BANK_SIZE - 1) == (bank0[-1] >> 8)

    assert await _read_byte(dut, bank=1, offset=0) == 0x80
    assert await _read_byte(dut, bank=1, offset=1) == 0x81
    assert await _read_byte(dut, bank=1, offset=ROM_BANK_SIZE - 2) == (bank1[-1] & 0xFF)
    assert await _read_byte(dut, bank=1, offset=ROM_BANK_SIZE - 1) == (bank1[-1] >> 8)
