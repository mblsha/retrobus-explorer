# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
FFC_LOW_BYTE_OE = 0xFF


def _pack_banks(*banks: int) -> int:
    assert len(banks) == 6
    return sum((value & 0xFF) << (8 * index) for index, value in enumerate(banks))


async def _init(dut, *, ffc_word: int) -> None:
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ffc_data_host.value = ffc_word
    dut.ffc_host_drive.value = 1

    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 10)


async def _uart_send_byte(dut, value: int) -> None:
    dut.usb_rx.value = 1
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    dut.usb_rx.value = 0
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    for bit_index in range(8):
        dut.usb_rx.value = (value >> bit_index) & 1
        await tick(dut.clk, USB_UART_BIT_CYCLES)

    dut.usb_rx.value = 1
    await tick(dut.clk, USB_UART_BIT_CYCLES)


async def _uart_wait_start(dut, *, timeout_cycles: int = 3000) -> None:
    if int(dut.usb_tx.value) == 0:
        return

    previous = int(dut.usb_tx.value)
    for _ in range(timeout_cycles):
        current = int(dut.usb_tx.value)
        if previous == 1 and current == 0:
            return
        previous = current
        await tick(dut.clk, 1)
    raise AssertionError("timeout waiting for UART echo start bit")


async def _uart_recv_byte(dut) -> int:
    await _uart_wait_start(dut)
    await tick(dut.clk, USB_UART_BIT_CYCLES + USB_UART_BIT_CYCLES // 2)

    value = 0
    for bit_index in range(8):
        value |= int(dut.usb_tx.value) << bit_index
        await tick(dut.clk, USB_UART_BIT_CYCLES)

    assert int(dut.usb_tx.value) == 1, "invalid UART echo stop bit"
    await tick(dut.clk, USB_UART_BIT_CYCLES // 2)
    return value


async def _send_and_expect_echo(dut, value: int) -> None:
    echo_task = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, value)
    echoed = await echo_task
    assert echoed == value, f"expected echo 0x{value:02x}, got 0x{echoed:02x}"
    await tick(dut.clk, 4)


async def _assert_uart_stays_idle(dut, cycles: int) -> None:
    for _ in range(cycles):
        assert int(dut.usb_tx.value) == 1
        await tick(dut.clk, 1)


def _assert_receive_outputs(dut, expected_byte: int) -> None:
    assert int(dut.send_mode_debug.value) == 0
    assert dut.ffc_oe_debug.value.integer == 0
    assert dut.led.value.integer == expected_byte
    assert dut.saleae.value.integer == expected_byte


@cocotb.test()
async def reset_defaults_to_receive_bank_zero_and_releases_all_ffc_pins(dut):
    ffc_word = _pack_banks(0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC)
    await _init(dut, ffc_word=ffc_word)

    assert dut.bank_debug.value.integer == 0
    assert dut.counter_debug.value.integer == 0
    assert dut.ffc_data.value.integer == ffc_word
    _assert_receive_outputs(dut, 0x12)


@cocotb.test()
async def receive_mode_selects_banks_zero_through_five_and_echoes_digits(dut):
    banks = (0x11, 0x22, 0x33, 0x44, 0x55, 0x66)
    await _init(dut, ffc_word=_pack_banks(*banks))

    for bank, expected in enumerate(banks):
        await _send_and_expect_echo(dut, ord("0") + bank)
        assert dut.bank_debug.value.integer == bank
        _assert_receive_outputs(dut, expected)

    await _uart_send_byte(dut, ord("6"))
    await _assert_uart_stays_idle(dut, USB_UART_BIT_CYCLES * 3)
    assert dut.bank_debug.value.integer == 5
    _assert_receive_outputs(dut, banks[5])


@cocotb.test()
async def send_mode_drives_only_low_ffc_byte_and_uses_two_bit_counter_windows(dut):
    ffc_word = _pack_banks(0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0xF6)
    await _init(dut, ffc_word=ffc_word)

    await _send_and_expect_echo(dut, ord("S"))
    assert int(dut.send_mode_debug.value) == 1
    assert dut.bank_debug.value.integer == 0
    assert dut.ffc_oe_debug.value.integer == FFC_LOW_BYTE_OE

    counter = dut.counter_debug.value.integer
    expected = counter & 0xFF
    assert dut.led.value.integer == expected
    assert dut.saleae.value.integer == expected
    assert dut.ffc_drive_debug.value.integer == expected
    assert dut.ffc_data.value.integer == (ffc_word & ~0xFF) | expected

    await _send_and_expect_echo(dut, ord("3"))
    assert dut.bank_debug.value.integer == 3
    assert dut.ffc_oe_debug.value.integer == FFC_LOW_BYTE_OE

    counter = dut.counter_debug.value.integer
    expected = (counter >> (3 * 2)) & 0xFF
    assert dut.led.value.integer == expected
    assert dut.saleae.value.integer == expected
    assert dut.ffc_drive_debug.value.integer == expected
    assert dut.ffc_data.value.integer == (ffc_word & ~0xFF) | expected


@cocotb.test()
async def command_letters_are_case_insensitive_and_mode_switches_reset_bank(dut):
    ffc_word = _pack_banks(0x5A, 0x10, 0x20, 0x30, 0x40, 0x50)
    await _init(dut, ffc_word=ffc_word)

    await _send_and_expect_echo(dut, ord("s"))
    await _send_and_expect_echo(dut, ord("4"))
    assert int(dut.send_mode_debug.value) == 1
    assert dut.bank_debug.value.integer == 4

    await _send_and_expect_echo(dut, ord("R"))
    assert dut.bank_debug.value.integer == 0
    _assert_receive_outputs(dut, 0x5A)

    await _send_and_expect_echo(dut, ord("S"))
    await _send_and_expect_echo(dut, ord("2"))
    await _send_and_expect_echo(dut, ord("r"))
    assert dut.bank_debug.value.integer == 0
    _assert_receive_outputs(dut, 0x5A)


@cocotb.test()
async def reset_while_sending_clears_mode_bank_counter_and_output_enables(dut):
    await _init(dut, ffc_word=_pack_banks(0xC7, 1, 2, 3, 4, 5))

    await _send_and_expect_echo(dut, ord("s"))
    await _send_and_expect_echo(dut, ord("5"))
    assert int(dut.send_mode_debug.value) == 1
    assert dut.counter_debug.value.integer != 0

    dut.rst_n.value = 0
    await tick(dut.clk, 6)

    assert dut.bank_debug.value.integer == 0
    assert dut.counter_debug.value.integer == 0
    _assert_receive_outputs(dut, 0xC7)
