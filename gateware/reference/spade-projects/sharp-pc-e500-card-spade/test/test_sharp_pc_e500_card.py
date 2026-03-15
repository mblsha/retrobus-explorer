# top = main

import json
from pathlib import Path

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100


def saleae_bit(value, idx):
    return (value >> idx) & 1


def expected_boot_banner() -> str:
    project_dir = Path(__file__).resolve().parents[1]
    info = json.loads((project_dir / "build" / "build_info.json").read_text())
    return info["banner"]


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


async def _uart_recv_line(dut, timeout_cycles: int = USB_UART_BIT_CYCLES * 200, max_len: int = 160) -> str:
    data = bytearray()
    for _ in range(max_len):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
        if data[-1] == 0x0A:
            return data.decode("ascii", errors="replace")
    raise AssertionError(f"line too long without LF: {data!r}")


async def _assert_no_usb_tx_start_bit(dut, cycles: int):
    prev = int(dut.usb_tx.value)
    for _ in range(cycles):
        cur = int(dut.usb_tx.value)
        assert not (prev == 1 and cur == 0), "unexpected USB UART transmission"
        prev = cur
        await tick(dut.clk, 1)


async def _init(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 0
    dut.addr.value = 0
    dut.vcc2.value = 0
    dut.data.value = 0
    dut.ce1.value = 0
    dut.ce6.value = 1
    dut.nc.value = 0
    dut.oe.value = 0

    await tick(dut.clk, 2)
    dut.rst_n.value = 1
    banner = await _uart_recv_line(dut)
    assert banner == expected_boot_banner()
    await tick(dut.clk, 1)


@cocotb.test()
async def boot_banner_and_fixed_50ns_cooldown_delay_both_uarts(dut):
    await _init(dut)

    dut.addr.value = 0x00001
    dut.data.value = 0x01

    addr_start = None
    data_start = None
    for cycle in range(20):
        v = int(dut.saleae.value)
        if addr_start is None and saleae_bit(v, 7) == 0:
            addr_start = cycle
        if data_start is None and saleae_bit(v, 5) == 0:
            data_start = cycle
        if addr_start is not None and data_start is not None:
            break
        await tick(dut.clk, 1)

    assert addr_start is not None
    assert data_start is not None
    assert abs(data_start - addr_start) <= 1


@cocotb.test()
async def usb_uart_is_idle_after_boot_banner(dut):
    await _init(dut)

    await _assert_no_usb_tx_start_bit(dut, USB_UART_BIT_CYCLES * 12)
    assert int(dut.usb_tx.value) == 1


@cocotb.test()
async def raw_control_pins_still_drive_saleae_outputs(dut):
    await _init(dut)

    dut.ce1.value = 1
    dut.ce6.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    await tick(dut.clk, 1)

    v = int(dut.saleae.value)
    assert saleae_bit(v, 0) == 1
    assert saleae_bit(v, 1) == 0
    assert saleae_bit(v, 2) == 1
    assert saleae_bit(v, 3) == 1
