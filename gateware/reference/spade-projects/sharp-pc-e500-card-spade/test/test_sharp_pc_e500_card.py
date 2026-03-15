# top = main

import json
from pathlib import Path

import cocotb

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def boot_line() -> str:
    meta = json.loads((PROJECT_ROOT / "build" / "build_info.json").read_text())
    return meta["banner"]


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


async def _uart_recv_line(dut, timeout_cycles: int = USB_UART_BIT_CYCLES * 160, max_len: int = 160) -> str:
    data = bytearray()
    for _ in range(max_len):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
        if data[-1] == 0x0A:
            return data.decode("ascii", errors="replace")
    raise AssertionError(f"line too long without LF: {data!r}")


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
    assert await help_line0 == "rAAAAAA wAAAAAA=BB p0|p1 m0|m1|m2 ? h\r\n"
    assert await _uart_recv_line(dut) == "S0=CE1_RAM# S1=CE6_ROM# S2=OE#\r\n"
    assert await _uart_recv_line(dut) == "m0/m1:S3=R/W S4=AD_CHG S5=DATA_CHG\r\n"
    assert await _uart_recv_line(dut) == "m0:S6=ADDR18_UART100 S7=DATA8_UART100\r\n"
    assert await _uart_recv_line(dut) == "m1:S6=PINCHR0 S7=PINCHR1 C1 C6 OE RW A0-A9 AA-AH D0-D7\r\n"
    assert await _uart_recv_line(dut) == "m2:S3=CTRL S4=DATACHR0 S5=DATACHR1 S6=ADDRCHR0 S7=ADDRCHR1\r\n"
    assert await _uart_recv_line(dut) == "CTRL:1 6 O R DATA:D0-D7 ADDR:A0-A9 AA-AH\r\n"

    err_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "w030000=12\r")
    assert await err_line == "ERR\r\n"

    status_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "?\r")
    assert await status_line == "P1 S0800 M1 BR0000 BW0000 UR0000 UW0000\r\n"


@cocotb.test()
async def boot_probe_style_present_and_absent_behavior_matches_spec(dut):
    await _init(dut)

    await _bus_write(dut, 0x0005, 0x01)
    assert (await _bus_read(dut, 0x0005)) & 0x01 == 0x01

    off_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "p0\r")
    assert await off_line == "P0\r\n"

    await _bus_write(dut, 0x0005, 0x01)
    assert await _bus_read(dut, 0x0005) == 0x00

    on_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "p1\r")
    assert await on_line == "P1\r\n"


@cocotb.test()
async def status_counts_track_bus_and_uart_accesses(dut):
    await _init(dut)

    await _bus_write(dut, 0x0001, 0x11)
    assert await _bus_read(dut, 0x0001) == 0x11

    ok_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "w040002=22\r")
    assert await ok_line == "OK\r\n"

    read_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "r040002\r")
    assert await read_line == "040002=22\r\n"

    status_line = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "?\r")
    assert await status_line == "P1 S0800 M1 BR0001 BW0001 UR0001 UW0001\r\n"


@cocotb.test()
async def pin_debug_mode_is_default_and_reports_pin_names(dut):
    await _init(dut)

    char0_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[6], dut.clk, 8))
    char1_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 8))

    dut.card_ram_ce1.value = 0
    await tick(dut.clk, 2)

    assert await char0_task == ord("C")
    assert await char1_task == ord("1")


@cocotb.test()
async def saleae_outputs_show_controls_and_monitor_uart_lines(dut):
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


@cocotb.test()
async def bus_write_streams_address_and_data_over_fast_uart_saleae_lines(dut):
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


@cocotb.test()
async def split_pin_debug_mode_reports_control_tokens_on_saleae3(dut):
    await _init(dut)
    await _set_mode(dut, 2)

    ctrl_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 8))

    dut.card_ram_ce1.value = 0
    await tick(dut.clk, 2)

    assert await ctrl_task == ord("1")


@cocotb.test()
async def split_pin_debug_mode_reports_data_tags_on_saleae45(dut):
    await _init(dut)
    await _set_mode(dut, 2)

    data0_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[4], dut.clk, 8))
    data1_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[5], dut.clk, 8))

    dut.addr.value = 0
    dut.rw.value = 0
    dut.oe.value = 1
    dut.card_ram_ce1.value = 0
    dut.data_host.value = 0x01
    dut.data_host_drive.value = 1
    await tick(dut.clk, 2)

    assert await data0_task == ord("D")
    assert await data1_task == ord("0")


@cocotb.test()
async def split_pin_debug_mode_reports_address_tags_on_saleae67(dut):
    await _init(dut)
    await _set_mode(dut, 2)

    addr0_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[6], dut.clk, 8))
    addr1_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 8))

    dut.addr.value = 0x00001
    await tick(dut.clk, 2)

    assert await addr0_task == ord("A")
    assert await addr1_task == ord("0")


@cocotb.test()
async def split_pin_debug_mode_drains_ctrl_addr_and_data_in_parallel(dut):
    await _init(dut)
    await _set_mode(dut, 2)

    ctrl_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 8))
    data0_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[4], dut.clk, 8))
    data1_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[5], dut.clk, 8))
    addr0_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[6], dut.clk, 8))
    addr1_task = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 8))

    dut.addr.value = 0x00001
    dut.rw.value = 0
    dut.oe.value = 1
    dut.card_ram_ce1.value = 0
    dut.data_host.value = 0x01
    dut.data_host_drive.value = 1
    await tick(dut.clk, 2)

    assert await ctrl_task == ord("1")
    assert await data0_task == ord("D")
    assert await data1_task == ord("0")
    assert await addr0_task == ord("A")
    assert await addr1_task == ord("0")
