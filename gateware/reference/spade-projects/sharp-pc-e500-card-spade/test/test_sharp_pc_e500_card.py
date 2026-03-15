# top = main

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100


def _set_data_bus_z(dut):
    dut.data_host.value = 0
    dut.data_host_drive.value = 0


async def _init(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.card_ram_ce1.value = 1
    dut.card_rom_ce6.value = 1
    dut.vcc2.value = 0
    dut.nc.value = 0
    dut.addr.value = 0
    _set_data_bus_z(dut)

    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 20)

    assert int(dut.usb_tx.value) == 1
    assert int(dut.saleae.value) == 0


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


async def _uart_recv_text(dut, length: int) -> str:
    data = bytearray()
    for _ in range(length):
        data.append(await _uart_recv_byte(dut))
    return data.decode("ascii", errors="replace")


@cocotb.test()
async def routes_address_pin_with_echo_and_ack(dut):
    await _init(dut)

    expected = "3-16\r\nS3<=FFC16:A10\r\n"
    recv = cocotb.start_soon(_uart_recv_text(dut, len(expected)))
    await _uart_send_text(dut, "316\r")
    assert await recv == expected

    dut.addr.value = 0
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == 0

    dut.addr.value = 1 << 10
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == (1 << 3)

    dut.addr.value = 0
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == 0


@cocotb.test()
async def invalid_route_prints_err_and_does_not_change_outputs(dut):
    await _init(dut)

    dut.addr.value = 1 << 10
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0

    expected = "3-48\r\nERR\r\n"
    recv = cocotb.start_soon(_uart_recv_text(dut, len(expected)))
    await _uart_send_text(dut, "348\r")
    assert await recv == expected

    await tick(dut.clk, 1)
    assert int(dut.saleae.value) == 0


@cocotb.test()
async def route_overwrite_switches_saleae_source(dut):
    await _init(dut)

    recv0 = cocotb.start_soon(_uart_recv_text(dut, len("3-16\r\nS3<=FFC16:A10\r\n")))
    await _uart_send_text(dut, "316\r")
    assert await recv0 == "3-16\r\nS3<=FFC16:A10\r\n"

    dut.addr.value = 1 << 10
    _set_data_bus_z(dut)
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == (1 << 3)

    recv1 = cocotb.start_soon(_uart_recv_text(dut, len("3-28\r\nS3<=FFC28:D0\r\n")))
    await _uart_send_text(dut, "328\r")
    assert await recv1 == "3-28\r\nS3<=FFC28:D0\r\n"

    dut.addr.value = 0
    dut.data_host.value = 0x00
    dut.data_host_drive.value = 1
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == 0

    dut.data_host.value = 0x01
    await tick(dut.clk, 1)
    assert int(dut.saleae.value) & (1 << 3) == (1 << 3)

    _set_data_bus_z(dut)


@cocotb.test()
async def non_digits_are_ignored(dut):
    await _init(dut)

    expected = "3-28\r\nS3<=FFC28:D0\r\n"
    recv = cocotb.start_soon(_uart_recv_text(dut, len(expected)))
    await _uart_send_text(dut, "x3y2z8\r")
    assert await recv == expected
