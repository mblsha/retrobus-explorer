# top = main

import json
from pathlib import Path

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
CLASSIFY_CYCLES = 50
TAIL_CYCLES = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def saleae_bit(value, idx):
    return (value >> idx) & 1


def expected_boot_banner() -> str:
    info = json.loads((PROJECT_ROOT / "build" / "build_info.json").read_text())
    return info["banner"]


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


async def _fast_uart_wait_start_fall(signal, clk, timeout_cycles: int) -> None:
    if int(signal.value) == 0:
        return
    prev = int(signal.value)
    for _ in range(timeout_cycles):
        cur = int(signal.value)
        if prev == 1 and cur == 0:
            return
        prev = cur
        await tick(clk, 1)
    raise AssertionError("timeout waiting for fast UART start bit")


async def _fast_uart_recv_word(signal, clk, width: int, timeout_cycles: int = 128) -> int:
    await _fast_uart_wait_start_fall(signal, clk, timeout_cycles)
    value = 0
    for idx in range(width):
        await tick(clk, 1)
        value |= int(signal.value) << idx
    await tick(clk, 1)
    assert int(signal.value) == 1, "invalid fast-UART stop bit"
    return value


def _set_data_bus_z(dut):
    dut.data_host.value = 0
    dut.data_host_drive.value = 0


async def _init(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.ce1.value = 0
    dut.ce6.value = 0
    dut.vcc2.value = 0
    dut.nc.value = 0
    dut.addr.value = 0
    _set_data_bus_z(dut)

    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 12)
    assert await _uart_recv_line(dut) == expected_boot_banner()


async def _bus_write(dut, addr: int, value: int):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, CLASSIFY_CYCLES + 2)
    dut.rw.value = 1
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)


async def _bus_write_and_check_tail_release(dut, addr: int, value: int, tail_value: int):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, CLASSIFY_CYCLES + 2)
    dut.data_host.value = tail_value & 0xFF
    dut.rw.value = 1
    await tick(dut.clk, 1)
    observed = int(dut.data.value) & 0xFF
    await tick(dut.clk, TAIL_CYCLES - 1)
    dut.ce1.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return observed


async def _bus_read(dut, addr: int) -> int:
    _set_data_bus_z(dut)
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 1
    dut.oe.value = 0
    await tick(dut.clk, CLASSIFY_CYCLES + 2)
    value = int(dut.data.value) & 0xFF
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    dut.oe.value = 1
    await tick(dut.clk, 2)
    return value


async def _bus_read_and_check_late_drive(dut, addr: int, host_value: int):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 1
    dut.oe.value = 0
    dut.data_host.value = host_value & 0xFF
    dut.data_host_drive.value = 1

    await tick(dut.clk, CLASSIFY_CYCLES - 5)
    before = int(dut.data.value) & 0xFF

    _set_data_bus_z(dut)
    await tick(dut.clk, 7)
    after = int(dut.data.value) & 0xFF

    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    dut.oe.value = 1
    await tick(dut.clk, 2)
    return before, after


@cocotb.test()
async def boot_banner_and_usb_uart_idle_after_boot(dut):
    await _init(dut)

    await _assert_no_usb_tx_start_bit(dut, USB_UART_BIT_CYCLES * 12)
    assert int(dut.usb_tx.value) == 1


@cocotb.test()
async def ram_card_writes_reads_and_mirrors_2k(dut):
    await _init(dut)

    assert await _bus_read(dut, 0x0005) == 0x00

    observed = await _bus_write_and_check_tail_release(dut, 0x0005, 0xA5, 0x3C)
    assert observed == 0x3C
    assert await _bus_read(dut, 0x0005) == 0xA5
    assert await _bus_read(dut, 0x0805) == 0xA5

    await _bus_write(dut, 0x0805, 0x5A)
    assert await _bus_read(dut, 0x0005) == 0x5A
    assert await _bus_read(dut, 0x0805) == 0x5A

    before, after = await _bus_read_and_check_late_drive(dut, 0x0005, 0x3C)
    assert before == 0x3C
    assert after == 0x5A

    dut.data_host.value = 0xC3
    dut.data_host_drive.value = 1
    dut.ce1.value = 0
    dut.rw.value = 1
    await tick(dut.clk, 1)
    assert (int(dut.data.value) & 0xFF) == 0xC3
    _set_data_bus_z(dut)


@cocotb.test()
async def sniffer_uarts_and_ram_event_uart_report_bus_activity(dut):
    await _init(dut)

    dut.ce1.value = 1
    dut.ce6.value = 1
    dut.rw.value = 0
    await tick(dut.clk, 1)
    v = int(dut.saleae.value)
    assert saleae_bit(v, 0) == 1
    assert saleae_bit(v, 1) == 1
    assert saleae_bit(v, 2) == 0
    dut.ce1.value = 0
    dut.ce6.value = 0
    dut.rw.value = 1
    await tick(dut.clk, 1)

    event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    data_uart = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[5], dut.clk, 8))
    addr_uart = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 18))

    await _bus_write(dut, 0x0012, 0x5A)

    assert await event_write == 0x575A
    assert await data_uart == 0x5A
    assert await addr_uart == 0x0012

    v = int(dut.saleae.value)
    assert saleae_bit(v, 4) == 0
    assert saleae_bit(v, 6) == 0

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    assert await _bus_read(dut, 0x0012) == 0x5A
    assert await event_read == 0x525A
