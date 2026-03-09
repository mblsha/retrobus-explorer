# top = main

import cocotb
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100


def _set_ft_bus_z(dut):
    dut.ft_data_host.value = 0
    dut.ft_be_host.value = 0
    dut.ft_host_drive.value = 0


async def _init(dut):
    start_clock(dut.clk)
    start_clock(dut.ft_clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    _set_ft_bus_z(dut)

    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 12)


async def _uart_send_byte(dut, value: int):
    dut.usb_rx.value = 1
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    dut.usb_rx.value = 0
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    for idx in range(8):
        dut.usb_rx.value = (value >> idx) & 1
        await tick(dut.clk, USB_UART_BIT_CYCLES)

    dut.usb_rx.value = 1
    await tick(dut.clk, USB_UART_BIT_CYCLES)


async def _uart_send_text(dut, text: str):
    for ch in text.encode("ascii"):
        await _uart_send_byte(dut, ch)


async def _uart_wait_start_fall(dut, timeout_cycles: int) -> None:
    if int(dut.usb_tx.value) == 0:
        return
    prev = int(dut.usb_tx.value)
    for _ in range(timeout_cycles):
        cur = int(dut.usb_tx.value)
        if prev == 1 and cur == 0:
            return
        prev = cur
        await tick(dut.clk, 1)
    raise AssertionError("timeout waiting for USB UART start bit")


async def _uart_recv_byte(dut, timeout_cycles: int = 12000) -> int:
    await _uart_wait_start_fall(dut, timeout_cycles)
    await tick(dut.clk, USB_UART_BIT_CYCLES + (USB_UART_BIT_CYCLES // 2))

    value = 0
    for idx in range(8):
        value |= int(dut.usb_tx.value) << idx
        await tick(dut.clk, USB_UART_BIT_CYCLES)

    stop = int(dut.usb_tx.value)
    assert stop == 1, f"invalid stop bit: {stop}"
    return value


async def _uart_recv_line(dut, timeout_cycles: int = USB_UART_BIT_CYCLES * 150, max_len: int = 160) -> str:
    data = bytearray()
    for _ in range(max_len):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
        if data[-1] == 0x0A:
            return data.decode("ascii", errors="replace")
    raise AssertionError(f"line too long without LF: {data!r}")


async def _ft_host_send_word_be(dut, word: int, be: int, timeout_cycles: int = 2000):
    dut.ft_data_host.value = word & 0xFFFF
    dut.ft_be_host.value = be & 0x3
    dut.ft_host_drive.value = 1
    dut.ft_rxf.value = 0

    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_read = int(dut.ft_oe.value) == 0 and int(dut.ft_rd.value) == 0 and int(dut.ft_rxf.value) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_read:
            dut.ft_rxf.value = 1
            _set_ft_bus_z(dut)
            await tick(dut.clk, 8)
            return
    raise AssertionError("timeout waiting for FT read handshake")


async def _collect_ft_writes(dut, count: int, timeout_cycles: int = 30000) -> list[tuple[int, int]]:
    observed: list[tuple[int, int]] = []
    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_write = int(dut.ft_oe.value) == 1 and int(dut.ft_wr.value) == 0 and int(dut.ft_txe.value) == 0
        sampled = (int(dut.ft_data_drive.value) & 0xFFFF, int(dut.ft_be_drive.value) & 0x3)
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_write:
            observed.append(sampled)
            if len(observed) == count:
                return observed
    raise AssertionError(f"timeout waiting for {count} FT writes")


@cocotb.test()
async def ft_words_are_printed_as_hex_with_byte_enables(dut):
    await _init(dut)

    recv0 = cocotb.start_soon(_uart_recv_line(dut))
    await _ft_host_send_word_be(dut, 0x1234, 0x3)
    assert await recv0 == "1234/3\r\n"

    recv1 = cocotb.start_soon(_uart_recv_line(dut))
    await _ft_host_send_word_be(dut, 0x0034, 0x1)
    assert await recv1 == "0034/1\r\n"

    recv2 = cocotb.start_soon(_uart_recv_line(dut))
    await _ft_host_send_word_be(dut, 0x1200, 0x2)
    assert await recv2 == "1200/2\r\n"


@cocotb.test()
async def uart_hex_lines_are_written_to_ft_with_default_and_explicit_be(dut):
    await _init(dut)

    dut.ft_txe.value = 0
    writes = cocotb.start_soon(_collect_ft_writes(dut, 3))
    await _uart_send_text(dut, "1234\r0034/1\r1200/2\r")
    assert await writes == [
        (0x1234, 0x3),
        (0x0034, 0x1),
        (0x1200, 0x2),
    ]


@cocotb.test()
async def help_status_and_parse_error_reporting_work(dut):
    await _init(dut)

    help_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "h\r")
    assert await help_line == "hhhh[/b] ? h\r\n"

    err_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "12XZ\r")
    assert await err_line == "ERR\r\n"

    status_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "?\r")
    assert await status_line == "R0000 T0000 E0001 S0000\r\n"


@cocotb.test()
async def multi_digit_be_suffix_is_rejected_as_parse_error(dut):
    await _init(dut)

    err_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "1234/01\r")
    assert await err_line == "ERR\r\n"


@cocotb.test()
async def counters_track_ft_rx_and_uart_tx_activity(dut):
    await _init(dut)

    recv = cocotb.start_soon(_uart_recv_line(dut))
    await _ft_host_send_word_be(dut, 0xABCD, 0x3)
    assert await recv == "ABCD/3\r\n"

    dut.ft_txe.value = 0
    writes = cocotb.start_soon(_collect_ft_writes(dut, 1))
    await _uart_send_text(dut, "55AA\r")
    assert await writes == [(0x55AA, 0x3)]

    status_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "?\r")
    assert await status_line == "R0001 T0001 E0000 S0000\r\n"
