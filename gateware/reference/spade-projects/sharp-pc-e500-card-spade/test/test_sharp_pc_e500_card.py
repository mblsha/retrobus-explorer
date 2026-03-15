# top = main

import json
from pathlib import Path

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BOOT_LINE: str | None = None


def boot_line() -> str:
    global _BOOT_LINE
    if _BOOT_LINE is None:
        meta = json.loads((PROJECT_ROOT / "build" / "build_info.json").read_text())
        _BOOT_LINE = meta["banner"]
    return _BOOT_LINE


def _set_data_bus_z(dut):
    dut.data_host.value = 0
    dut.data_host_drive.value = 0


async def _settle_pins(dut, cycles: int = 6):
    await tick(dut.clk, cycles)


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
    await tick(dut.clk, 12)
    assert await _uart_recv_line(dut) == boot_line()


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


async def _set_mode(dut, mode: int):
    mode_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, f"m{mode}\r")
    assert await mode_line == f"M{mode}\r\n"


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


async def _uart_recv_line(dut, timeout_cycles: int = USB_UART_BIT_CYCLES * 200, max_len: int = 200) -> str:
    data = bytearray()
    for _ in range(max_len):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
        if data[-1] == 0x0A:
            return data.decode("ascii", errors="replace")
    raise AssertionError(f"line too long without LF: {data!r}")


async def _uart_recv_until_end(dut) -> list[str]:
    lines: list[str] = []
    while True:
        line = await _uart_recv_line(dut)
        lines.append(line)
        if line == "END\r\n":
            return lines


async def _fast_uart_wait_start_fall(signal, clk, timeout_cycles: int) -> None:
    for _ in range(timeout_cycles):
        if int(signal.value) == 1:
            break
        await tick(clk, 1)
    else:
        raise AssertionError("timeout waiting for monitor UART idle-high")

    prev = 1
    for _ in range(timeout_cycles):
        cur = int(signal.value)
        if prev == 1 and cur == 0:
            return
        prev = cur
        await tick(clk, 1)
    raise AssertionError("timeout waiting for monitor UART start bit")


async def _fast_uart_recv_word(signal, clk, width: int, timeout_cycles: int = 64) -> int:
    await _fast_uart_wait_start_fall(signal, clk, timeout_cycles)
    value = 0
    for idx in range(width):
        await tick(clk, 1)
        value |= int(signal.value) << idx
    await tick(clk, 1)
    assert int(signal.value) == 1, "invalid fast-UART stop bit"
    return value


async def _bus_write(dut, addr: int, value: int, hold_cycles: int = 3):
    dut.addr.value = addr & 0x3FFFF
    dut.rw.value = 0
    dut.oe.value = 1
    dut.card_ram_ce1.value = 0
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, hold_cycles)
    dut.card_ram_ce1.value = 1
    dut.rw.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)


async def _bus_read(dut, addr: int) -> int:
    _set_data_bus_z(dut)
    dut.addr.value = addr & 0x3FFFF
    dut.rw.value = 1
    dut.oe.value = 0
    dut.card_ram_ce1.value = 0
    await tick(dut.clk, 2)
    value = int(dut.data.value) & 0xFF
    dut.card_ram_ce1.value = 1
    dut.oe.value = 1
    await tick(dut.clk, 2)
    return value


@cocotb.test()
async def bus_reads_and_writes_stop_after_2k(dut):
    await _init(dut)

    await _bus_write(dut, 0x0005, 0xA5)
    assert await _bus_read(dut, 0x0005) == 0xA5
    assert await _bus_read(dut, 0x0805) == 0x00

    await _bus_write(dut, 0x0FFF, 0x3C)
    assert await _bus_read(dut, 0x07FF) == 0x00
    assert await _bus_read(dut, 0x0FFF) == 0x00


@cocotb.test()
async def uart_can_read_write_memory_and_control_presence(dut):
    await _init(dut)

    ok_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "w040123=AB\r")
    assert await ok_line == "OK\r\n"

    read_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "r040123\r")
    assert await read_line == "040123=AB\r\n"

    out_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "r040923\r")
    assert await out_line == "040923=00\r\n"

    assert await _bus_read(dut, 0x0123) == 0xAB

    off_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "p0\r")
    assert await off_line == "P0\r\n"

    assert await _bus_read(dut, 0x0123) == 0x00

    on_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "p1\r")
    assert await on_line == "P1\r\n"
    assert await _bus_read(dut, 0x0123) == 0xAB


@cocotb.test()
async def help_status_and_parse_errors_work(dut):
    await _init(dut)

    help_line0 = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "h\r")
    assert await help_line0 == "rAAAAAA wAAAAAA=BB p0|p1|pPIN a c m0|m1 ? h\r\n"
    assert await _uart_recv_line(dut) == "pPIN reads+clears one pin counter, a dumps all pin counters\r\n"
    assert await _uart_recv_line(dut) == "c clears all pin counters, counts are sampled edge totals\r\n"
    assert await _uart_recv_line(dut) == "S0=CE1_RAM# S1=CE6_ROM# S2=OE# S3=R/W S4=AD_CHG S5=DATA_CHG\r\n"
    assert await _uart_recv_line(dut) == "m0:S6=ADDR18_UART100 S7=DATA8_UART100, m1:S6/S7 idle USB counts\r\n"

    err_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "d41\r")
    assert await err_line == "ERR\r\n"

    status_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "?\r")
    assert await status_line == "P1 S0800 M1 BR0000 BW0000 UR0000 UW0000\r\n"


@cocotb.test()
async def address_pin_counter_tracks_edges_and_read_clears(dut):
    await _init(dut)

    clear_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "c\r")
    assert await clear_line == "OK\r\n"

    dut.addr.value = 0x00001
    await _settle_pins(dut)
    dut.addr.value = 0x00000
    await _settle_pins(dut)

    count_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pA0\r")
    assert await count_line == "PA0=00000002\r\n"

    cleared_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pA0\r")
    assert await cleared_line == "PA0=00000000\r\n"


@cocotb.test()
async def data_pin_counter_tracks_edges_and_read_clears(dut):
    await _init(dut)

    clear_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "c\r")
    assert await clear_line == "OK\r\n"

    dut.data_host.value = 0x01
    dut.data_host_drive.value = 1
    await _settle_pins(dut)

    count_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pD0\r")
    assert await count_line == "PD0=00000001\r\n"

    cleared_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pD0\r")
    assert await cleared_line == "PD0=00000000\r\n"

    _set_data_bus_z(dut)


@cocotb.test()
async def control_pin_counter_tracks_edges_and_read_clears(dut):
    await _init(dut)

    clear_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "c\r")
    assert await clear_line == "OK\r\n"

    dut.card_ram_ce1.value = 0
    await _settle_pins(dut)
    dut.card_ram_ce1.value = 1
    await _settle_pins(dut)

    count_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pC1\r")
    assert await count_line == "PC1=00000002\r\n"

    cleared_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pC1\r")
    assert await cleared_line == "PC1=00000000\r\n"


@cocotb.test()
async def dump_all_pin_counts_lists_every_pin_without_clearing(dut):
    await _init(dut)

    clear_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "c\r")
    assert await clear_line == "OK\r\n"

    dut.addr.value = 0x00001
    await _settle_pins(dut)
    dut.data_host.value = 0x01
    dut.data_host_drive.value = 1
    await _settle_pins(dut)

    dump_task = cocotb.start_soon(_uart_recv_until_end(dut))
    await _uart_send_text(dut, "a\r")
    lines = await dump_task
    assert len(lines) == 31
    assert "PA0=00000001\r\n" in lines
    assert "PD0=00000001\r\n" in lines
    assert "PC1=00000000\r\n" in lines
    assert lines[-1] == "END\r\n"

    count_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pA0\r")
    assert await count_line == "PA0=00000001\r\n"

    _set_data_bus_z(dut)


@cocotb.test()
async def clear_all_pin_counters_resets_counts(dut):
    await _init(dut)

    dut.addr.value = 0x00001
    await _settle_pins(dut)
    dut.addr.value = 0x00000
    await _settle_pins(dut)

    clear_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "c\r")
    assert await clear_line == "OK\r\n"

    count_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "pA0\r")
    assert await count_line == "PA0=00000000\r\n"


@cocotb.test()
async def saleae_outputs_show_controls_and_flags_in_usb_count_mode(dut):
    await _init(dut)

    await _bus_write(dut, 0x0003, 0xAB)

    dut.card_ram_ce1.value = 0
    dut.card_rom_ce6.value = 1
    dut.oe.value = 0
    dut.rw.value = 1
    dut.addr.value = 0x00003
    await tick(dut.clk, 2)

    saleae = dut.saleae.value.integer
    assert (saleae >> 0) & 1 == 0
    assert (saleae >> 1) & 1 == 1
    assert (saleae >> 2) & 1 == 0
    assert (saleae >> 3) & 1 == 1
    assert (saleae >> 4) & 1 == 0
    assert (saleae >> 5) & 1 == 0
    assert (saleae >> 6) & 1 == 1
    assert (saleae >> 7) & 1 == 1


@cocotb.test()
async def sampled_saleae_mode_streams_address_and_data(dut):
    await _init(dut)
    await _set_mode(dut, 0)

    addr_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[6], dut.clk, 18))
    data_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 8))

    dut.addr.value = 0x00123
    dut.rw.value = 0
    dut.oe.value = 1
    dut.card_ram_ce1.value = 0
    dut.data_host.value = 0xAB
    dut.data_host_drive.value = 1
    await tick(dut.clk, 1)
    dut.card_ram_ce1.value = 1
    dut.rw.value = 1
    _set_data_bus_z(dut)

    assert await addr_task == 0x00123
    assert await data_task == 0xAB
