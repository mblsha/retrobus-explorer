# top = main

import json
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
DEFAULT_CLASSIFY_CYCLES = 45
DEFAULT_CTRL_WRITE_DELAY_CYCLES = 3
TAIL_CYCLES = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FT_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
FT_CE6_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_ce6.ft16"
FT_OVERFLOW_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_overflow_record.ft16"

FT_KIND_BUS_CHANGE = 0x00
FT_KIND_CE1_READ = 0x01
FT_KIND_CE1_WRITE = 0x02
FT_KIND_CE6_READ = 0x03
FT_KIND_CE6_WRITE_ATTEMPT = 0x04
FT_KIND_SYNC = 0xF0
FT_KIND_OVERFLOW = 0xF1
FT_KIND_CONFIG = 0xF2
FT_RECORD_WORDS = 5
FT_RECORD_FIFO_RECORDS = 8192
FT_TAP_TX_FIFO_WORDS = 8192
FT_TAP_TX_FIFO_RECORDS = FT_TAP_TX_FIFO_WORDS // FT_RECORD_WORDS
FT_OVERFLOW_TRIGGER_READS = 12000


def saleae_bit(value, idx):
    return (value >> idx) & 1


def expected_boot_banner() -> str:
    info = json.loads((PROJECT_ROOT / "build" / "build_info.json").read_text())
    return info["banner"]


def _bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


def _u16(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0xFFFF


def _u2(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0x3


def _ft_kind(record: int) -> int:
    return (record >> 72) & 0xFF


def _ft_delta(record: int) -> int:
    return (record >> 40) & 0xFFFFFFFF


def _ft_addr(record: int) -> int:
    return (record >> 22) & 0x3FFFF


def _ft_data(record: int) -> int:
    return (record >> 14) & 0xFF


def _ft_aux(record: int) -> int:
    return record & 0x3FFF


def _ft_overflow_count(record: int) -> int:
    return _ft_addr(record) | (_ft_data(record) << 18)


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
    await tick(dut.clk, USB_UART_BIT_CYCLES // 2)
    return value


async def _uart_recv_line(dut, timeout_cycles: int = USB_UART_BIT_CYCLES * 200, max_len: int = 160) -> str:
    data = bytearray()
    for _ in range(max_len):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
        if data[-1] == 0x0A:
            return data.decode("ascii", errors="replace")
    raise AssertionError(f"line too long without LF: {data!r}")


async def _uart_recv_exact(dut, nbytes: int, timeout_cycles: int = USB_UART_BIT_CYCLES * 200) -> bytes:
    data = bytearray()
    for _ in range(nbytes):
        data.append(await _uart_recv_byte(dut, timeout_cycles))
    return bytes(data)


async def _uart_send_byte(dut, value: int):
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


async def _assert_no_fast_uart_start_fall(signal, clk, cycles: int) -> None:
    prev = int(signal.value)
    for _ in range(cycles):
        cur = int(signal.value)
        assert not (prev == 1 and cur == 0), "unexpected fast UART transmission"
        prev = cur
        await tick(clk, 1)


async def _fast_uart_recv_word(signal, clk, width: int, timeout_cycles: int = 128) -> int:
    await _fast_uart_wait_start_fall(signal, clk, timeout_cycles)
    value = 0
    for idx in range(width):
        await tick(clk, 1)
        value |= int(signal.value) << idx
    await tick(clk, 1)
    assert int(signal.value) == 1, "invalid fast-UART stop bit"
    return value


async def _fast_uart_recv_bytes(signal, clk, count: int, timeout_cycles: int = 128) -> list[int]:
    data = []
    for _ in range(count):
        data.append(await _fast_uart_recv_word(signal, clk, 8, timeout_cycles))
    return data


async def _fast_uart_recv_words(signal, clk, width: int, count: int, timeout_cycles: int = 128) -> list[int]:
    data = []
    for _ in range(count):
        data.append(await _fast_uart_recv_word(signal, clk, width, timeout_cycles))
    return data


async def _collect_ft_writes(dut, count: int, timeout_cycles: int = 4000) -> list[tuple[int, int]]:
    observed: list[tuple[int, int]] = []
    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_write = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        sampled_word = (_u16(dut.ft_data), _u2(dut.ft_be))
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_write:
            observed.append(sampled_word)
            if len(observed) == count:
                return observed
    raise AssertionError(f"timed out waiting for {count} FT writes")


async def _assert_no_ft_write(dut, cycles: int = 800):
    for _ in range(cycles):
        await FallingEdge(dut.ft_clk)
        will_write = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        assert not will_write, "unexpected FT write while streaming should be idle"


async def _ft_recv_record(dut, timeout_cycles: int = 12000) -> int:
    words = await _collect_ft_writes(dut, 5, timeout_cycles)
    record = 0
    for idx, (word, be) in enumerate(words):
        assert be == 0x3, f"expected FT byte-enable 0x3, got {be:#x}"
        record |= word << (16 * idx)
    return record


async def _ft_recv_records(dut, count: int, timeout_cycles: int = 12000) -> list[int]:
    out: list[int] = []
    for _ in range(count):
        out.append(await _ft_recv_record(dut, timeout_cycles))
    return out


def _ft_records_to_bytes(records: list[int]) -> bytes:
    out = bytearray()
    for record in records:
        out.extend(int(record).to_bytes(10, "little"))
    return bytes(out)


def _set_data_bus_z(dut):
    dut.data_host.value = 0
    dut.data_host_drive.value = 0


def _set_ft_bus_z(dut):
    dut.ft_data_host.value = 0
    dut.ft_be_host.value = 0
    dut.ft_host_drive.value = 0


async def _init(dut):
    start_clock(dut.clk)
    start_clock(dut.ft_clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.ce1.value = 0
    dut.ce6.value = 1
    dut.vcc2.value = 0
    dut.nc.value = 0
    dut.addr.value = 0
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 0
    _set_data_bus_z(dut)
    _set_ft_bus_z(dut)

    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 12)
    assert await _uart_recv_line(dut) == expected_boot_banner()


async def _enable_ft(dut, drain_debug_cycles: int = 32):
    ft_records = cocotb.start_soon(_ft_recv_records(dut, 2))
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"f1\r\nF=1\r\n")))
    await _uart_send_text(dut, "f1\r")
    assert await rx == b"f1\r\nF=1\r\n"
    sync, config = await ft_records
    if drain_debug_cycles > 0:
        await tick(dut.clk, drain_debug_cycles)
    return sync, config


def _parse_ft_stats_line(line: str) -> dict[str, int]:
    parts = line.strip().split()
    stats: dict[str, int] = {}
    for part in parts:
        key, value = part.split("=", 1)
        if key == "F":
            stats[key] = int(value, 10)
        else:
            stats[key] = int(value, 16)
    return stats


def _parse_key_value_csv(line: str) -> tuple[str, dict[str, int]]:
    parts = line.strip().split(",")
    prefix = parts[0]
    values: dict[str, int] = {}
    for part in parts[1:]:
        key, value = part.split("=", 1)
        if key == "ARM":
            values[key] = int(value, 10)
        else:
            values[key] = int(value, 16)
    return prefix, values


async def _disable_ft(dut):
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"f0\r\n")))
    await _uart_send_text(dut, "f0\r")
    assert await rx == b"f0\r\n"
    line = await _uart_recv_line(dut, max_len=160)
    stats = _parse_ft_stats_line(line)
    assert stats["F"] == 0
    return stats


async def _find_uart_write_collision_phase(
    dut,
    cmd: str,
    *,
    search_start: int = 7800,
    search_span: int = 500,
    classify_cycles: int = DEFAULT_CLASSIFY_CYCLES,
) -> int:
    echo = cmd.replace("\r", "\r\n").encode()
    for phase in range(search_start, search_start + search_span):
        dut.rst_n.value = 0
        dut.usb_rx.value = 1
        dut.rw.value = 1
        dut.oe.value = 1
        dut.ce1.value = 0
        dut.ce6.value = 1
        dut.addr.value = 0
        _set_data_bus_z(dut)
        await tick(dut.clk, 8)
        dut.rst_n.value = 1
        await tick(dut.clk, 12)
        assert await _uart_recv_line(dut) == expected_boot_banner()

        echo_rx = cocotb.start_soon(_uart_recv_exact(dut, len(echo)))
        tx = cocotb.start_soon(_uart_send_text(dut, cmd))
        await tick(dut.clk, phase)
        await _bus_write(dut, 0x0012, 0x5A, classify_cycles=classify_cycles)
        await tx
        if await echo_rx != echo:
            continue
        if await _uart_recv_line(dut, timeout_cycles=USB_UART_BIT_CYCLES * 40) == "BUSY\r\n":
            return phase
    raise AssertionError("failed to find a same-cycle UART write collision phase")


async def _find_uart_read_collision_phase(
    dut,
    cmd: str,
    *,
    search_start: int = 4800,
    search_span: int = 400,
    classify_cycles: int = DEFAULT_CLASSIFY_CYCLES,
    bus_addr: int = 0x0005,
    bus_value: int = 0xA5,
) -> int:
    echo = cmd.replace("\r", "\r\n").encode()
    for phase in range(search_start, search_start + search_span):
        await _init(dut)

        echo_rx = cocotb.start_soon(_uart_recv_exact(dut, len(echo)))
        tx = cocotb.start_soon(_uart_send_text(dut, cmd))
        await tick(dut.clk, phase)
        await _bus_write(dut, bus_addr, bus_value, classify_cycles=classify_cycles)
        await tx
        if await echo_rx != echo:
            continue
        if await _uart_recv_line(dut, timeout_cycles=USB_UART_BIT_CYCLES * 40) == "BUSY\r\n":
            return phase
    raise AssertionError("failed to find a same-cycle UART read collision phase")


async def _bus_write(dut, addr: int, value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    dut.rw.value = 1
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)


async def _bus_write_and_check_tail_release(dut, addr: int, value: int, tail_value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    dut.data_host.value = tail_value & 0xFF
    dut.rw.value = 1
    await tick(dut.clk, 1)
    observed = int(dut.data.value) & 0xFF
    await tick(dut.clk, TAIL_CYCLES - 1)
    dut.ce1.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return observed


async def _bus_read(dut, addr: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES) -> int:
    _set_data_bus_z(dut)
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 1
    dut.oe.value = 0
    await tick(dut.clk, classify_cycles + 2)
    value = int(dut.data.value) & 0xFF
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    dut.oe.value = 1
    await tick(dut.clk, 2)
    return value


async def _bus_read_and_check_late_drive(dut, addr: int, host_value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce1.value = 1
    dut.rw.value = 1
    dut.oe.value = 0
    dut.data_host.value = host_value & 0xFF
    dut.data_host_drive.value = 1

    await tick(dut.clk, classify_cycles - 5)
    before = int(dut.data.value) & 0xFF

    _set_data_bus_z(dut)
    await tick(dut.clk, 7)
    after = int(dut.data.value) & 0xFF

    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    dut.oe.value = 1
    await tick(dut.clk, 2)
    return before, after


async def _ce6_read(dut, addr: int, value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce6.value = 0
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 0
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    observed = int(dut.data.value) & 0xFF
    drive = int(dut.data_oe.value)
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce6.value = 1
    dut.oe.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return observed, drive


async def _ce6_write(dut, addr: int, value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce6.value = 0
    dut.ce1.value = 0
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce6.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return drive


async def _ce6_ctrl_short_write(dut, addr: int, value: int, pre_low_cycles: int = 1, low_cycles: int = 1):
    dut.addr.value = addr & 0x3FFFF
    dut.ce6.value = 0
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, pre_low_cycles)
    dut.rw.value = 0
    await tick(dut.clk, low_cycles)
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    dut.ce6.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return drive


async def _ce6_ctrl_async_write_phase(
    dut,
    addr: int,
    value: int,
    *,
    ce6_phase_ns: int,
    rw_phase_ns: int,
    hold_low_ns: int = 120,
):
    assert 0 <= ce6_phase_ns < 10
    assert 0 <= rw_phase_ns < 10

    dut.addr.value = addr & 0x3FFFF
    dut.ce6.value = 1
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, units="ps")

    current_ns = 0
    if ce6_phase_ns > 0:
        await Timer(ce6_phase_ns, units="ns")
    dut.ce6.value = 0
    current_ns = ce6_phase_ns
    if rw_phase_ns > current_ns:
        await Timer(rw_phase_ns - current_ns, units="ns")
    dut.rw.value = 0
    await Timer(hold_low_ns, units="ns")
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    dut.ce6.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return drive


@cocotb.test()
async def boot_banner_and_uart_ft_idle_after_boot(dut):
    await _init(dut)

    await _assert_no_usb_tx_start_bit(dut, USB_UART_BIT_CYCLES * 12)
    await _assert_no_ft_write(dut, 400)
    assert int(dut.usb_tx.value) == 1


@cocotb.test()
async def usb_uart_echo_reads_writes_ft_toggle_and_reports_errors(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"w005=A5\r\nOK\r\n")))
    await _uart_send_text(dut, "w005=A5\r")
    assert await rx == b"w005=A5\r\nOK\r\n"

    assert await _bus_read(dut, 0x0005) == 0xA5
    assert await _bus_read(dut, 0x0805) == 0xA5

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"r005\r\n005=A5\r\n")))
    await _uart_send_text(dut, "r005\r")
    assert await rx == b"r005\r\n005=A5\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"W021=A7\r\nOK\r\n")))
    await _uart_send_text(dut, "W021=A7\r")
    assert await rx == b"W021=A7\r\nOK\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"R021\r\n021=A7\r\n")))
    await _uart_send_text(dut, "R021\r")
    assert await rx == b"R021\r\n021=A7\r\n"

    observed, drive = await _ce6_read(dut, 0x0021, 0x11)
    assert observed == 0xA7
    assert drive == 1

    await _bus_write(dut, 0x0005, 0x3C)
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"r005\r\n005=3C\r\n")))
    await _uart_send_text(dut, "r005\r")
    assert await rx == b"r005\r\n005=3C\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"\r\nERR\r\n")))
    await _uart_send_text(dut, "x\r")
    assert await rx == b"\r\nERR\r\n"

    stats = await _disable_ft(dut)
    assert stats["REC"] == 0x0, stats
    assert stats["DRP"] == 0x0, stats
    assert stats["WRD"] == 0x0, stats
    assert stats["QMX"] == 0x0, stats
    assert stats["TFF"] == 0x0, stats
    sync, config = await _enable_ft(dut, drain_debug_cycles=0)
    assert _ft_kind(sync) == FT_KIND_SYNC
    assert _ft_kind(config) == FT_KIND_CONFIG


@cocotb.test()
async def ft_disable_reports_stats_and_clears_counters(dut):
    await _init(dut)

    await _enable_ft(dut)
    records = cocotb.start_soon(_ft_recv_records(dut, 2))
    await _bus_write(dut, 0x0005, 0xA5)
    assert await _bus_read(dut, 0x0005) == 0xA5
    await records

    stats = await _disable_ft(dut)
    assert stats["REC"] > 0x4, stats
    assert stats["DRP"] == 0x0, stats
    assert stats["WRD"] == stats["REC"] * FT_RECORD_WORDS, stats
    assert stats["QMX"] > 0, stats
    assert stats["TFF"] == 0x0, stats

    stats = await _disable_ft(dut)
    assert stats["REC"] == 0x0, stats
    assert stats["DRP"] == 0x0, stats
    assert stats["WRD"] == 0x0, stats
    assert stats["QMX"] == 0x0, stats
    assert stats["TFF"] == 0x0, stats


@cocotb.test()
async def usb_uart_write_collisions_return_busy_and_do_not_commit_uart_write(dut):
    await _init(dut)

    phase = await _find_uart_write_collision_phase(dut, "w005=A5\r")

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.ce1.value = 0
    dut.ce6.value = 1
    dut.addr.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 12)
    assert await _uart_recv_line(dut) == expected_boot_banner()

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"w005=A5\r\nBUSY\r\n")))
    tx = cocotb.start_soon(_uart_send_text(dut, "w005=A5\r"))
    await tick(dut.clk, phase)
    await _bus_write(dut, 0x0012, 0x5A)
    await tx
    assert await rx == b"w005=A5\r\nBUSY\r\n"
    assert await _bus_read(dut, 0x0012) == 0x5A
    assert await _bus_read(dut, 0x0005) == 0x00


@cocotb.test()
async def usb_uart_read_collisions_return_busy(dut):
    await _init(dut)

    phase = await _find_uart_read_collision_phase(dut, "r005\r")

    await _init(dut)
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"r005\r\nBUSY\r\n")))
    tx = cocotb.start_soon(_uart_send_text(dut, "r005\r"))
    await tick(dut.clk, phase)
    await _bus_write(dut, 0x0005, 0xA5)
    await tx

    assert await rx == b"r005\r\nBUSY\r\n"
    assert await _bus_read(dut, 0x0005) == 0xA5


@cocotb.test()
async def runtime_reset_scrubs_ram_contents(dut):
    await _init(dut)

    await _bus_write(dut, 0x0005, 0xA5)
    assert await _bus_read(dut, 0x0005) == 0xA5

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.ce1.value = 0
    dut.ce6.value = 1
    dut.addr.value = 0
    _set_data_bus_z(dut)
    await tick(dut.clk, 8)
    dut.rst_n.value = 1
    await tick(dut.clk, 12)
    assert await _uart_recv_line(dut) == expected_boot_banner()

    assert await _bus_read(dut, 0x0005) == 0x00


@cocotb.test()
async def usb_uart_can_set_classify_delay_and_emit_ft_config(dut):
    await _init(dut)
    await _enable_ft(dut)

    ft_config = cocotb.start_soon(_ft_recv_record(dut))
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"t20\r\nT=200ns\r\n")))
    await _uart_send_text(dut, "t20\r")
    assert await rx == b"t20\r\nT=200ns\r\n"

    config = await ft_config
    assert _ft_kind(config) == FT_KIND_CONFIG
    assert _ft_addr(config) == 20
    assert (_ft_aux(config) & 0x1) == 1

    await _bus_write(dut, 0x0005, 0x5A, classify_cycles=20)

    dut.addr.value = 0x0005
    dut.ce1.value = 1
    dut.rw.value = 1
    dut.oe.value = 0
    dut.data_host.value = 0x3C
    dut.data_host_drive.value = 1

    await tick(dut.clk, 15)
    before = int(dut.data.value) & 0xFF
    _set_data_bus_z(dut)
    await tick(dut.clk, 7)
    after = int(dut.data.value) & 0xFF

    await tick(dut.clk, TAIL_CYCLES)
    dut.ce1.value = 0
    dut.oe.value = 1
    await tick(dut.clk, 2)

    assert before == 0x3C
    assert after == 0x5A


@cocotb.test()
async def usb_uart_can_set_control_write_delay(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"c08\r\nC=080ns\r\n")))
    await _uart_send_text(dut, "c08\r")
    assert await rx == b"c08\r\nC=080ns\r\n"


@cocotb.test()
async def measurement_reports_can_be_dumped_and_cleared(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"m?\r\nMS,CNT=00,OVF=00000000,ARM=0\r\n")))
    await _uart_send_text(dut, "m?\r")
    assert await rx == b"m?\r\nMS,CNT=00,OVF=00000000,ARM=0\r\n"

    assert await _ce6_write(dut, 0x1FFF0, 0x12) == 0
    await _bus_write(dut, 0x0012, 0x5A)
    assert await _bus_read(dut, 0x0012) == 0x5A
    assert await _ce6_write(dut, 0x1FFF2, 0x34) == 0

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"m?\r\n")))
    await _uart_send_text(dut, "m?\r")
    assert await rx == b"m?\r\n"
    prefix, status = _parse_key_value_csv(await _uart_recv_line(dut))
    assert prefix == "MS"
    assert status == {"CNT": 0x01, "OVF": 0x00000000, "ARM": 0}

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"m\r\n")))
    await _uart_send_text(dut, "m\r")
    assert await rx == b"m\r\n"

    prefix, report = _parse_key_value_csv(await _uart_recv_line(dut))
    assert prefix == "MR"
    assert report["S"] == 0x12
    assert report["E"] == 0x34
    assert report["TK"] > 0
    assert report["EV"] == 0x00000002, report
    assert report["FT"] == 0x00000000
    assert report["AU"] > 0

    assert await _uart_recv_line(dut) == "MEND\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"m!\r\nOK\r\n")))
    await _uart_send_text(dut, "m!\r")
    assert await rx == b"m!\r\nOK\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"m?\r\nMS,CNT=00,OVF=00000000,ARM=0\r\n")))
    await _uart_send_text(dut, "m?\r")
    assert await rx == b"m?\r\nMS,CNT=00,OVF=00000000,ARM=0\r\n"


@cocotb.test()
async def measurement_dump_preserves_fifo_order_for_multiple_reports(dut):
    await _init(dut)

    assert await _ce6_write(dut, 0x1FFF0, 0x21) == 0
    await tick(dut.clk, 12)
    assert await _ce6_write(dut, 0x1FFF2, 0x22) == 0

    assert await _ce6_write(dut, 0x1FFF0, 0x31) == 0
    await _bus_write(dut, 0x0001, 0x44)
    assert await _ce6_write(dut, 0x1FFF2, 0x32) == 0

    lines = cocotb.start_soon(_uart_recv_exact(dut, len(b"m\r\n")))
    await _uart_send_text(dut, "m\r")
    assert await lines == b"m\r\n"

    prefix0, rec0 = _parse_key_value_csv(await _uart_recv_line(dut))
    prefix1, rec1 = _parse_key_value_csv(await _uart_recv_line(dut))
    end = await _uart_recv_line(dut)

    assert prefix0 == "MR"
    assert rec0["S"] == 0x21
    assert rec0["E"] == 0x22
    assert rec0["EV"] == 0x00000000

    assert prefix1 == "MR"
    assert rec1["S"] == 0x31
    assert rec1["E"] == 0x32
    assert rec1["EV"] == 0x00000001

    assert end == "MEND\r\n"


@cocotb.test()
async def ft_access_fixture_matches_hdl_bytes(dut):
    await _init(dut)

    sync, config = await _enable_ft(dut, drain_debug_cycles=0)
    records = cocotb.start_soon(_ft_recv_records(dut, 3))
    await _bus_write(dut, 0x0123, 0x5A)
    assert await _bus_read(dut, 0x0123) == 0x5A
    assert await _bus_read(dut, 0x0123) == 0x5A

    expected = FT_FIXTURE_PATH.read_bytes()[: 5 * 10]
    actual = _ft_records_to_bytes([sync, config] + await records)
    assert actual == expected, f"actual={actual.hex()} expected={expected.hex()}"


@cocotb.test()
async def ft_ce6_fixture_matches_hdl_bytes(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"W021=A7\r\nOK\r\n")))
    await _uart_send_text(dut, "W021=A7\r")
    assert await rx == b"W021=A7\r\nOK\r\n"

    sync, config = await _enable_ft(dut, drain_debug_cycles=0)
    records = cocotb.start_soon(_ft_recv_records(dut, 2))
    observed, drive = await _ce6_read(dut, 0x0021, 0xA7)
    assert observed == 0xA7
    assert drive == 1

    expected = FT_CE6_FIXTURE_PATH.read_bytes()
    actual = _ft_records_to_bytes([sync, config] + await records)
    assert actual == expected, f"actual={actual.hex()} expected={expected.hex()}"


@cocotb.test()
async def ft_overflow_record_fixture_matches_hdl_bytes(dut):
    await _init(dut)
    await _enable_ft(dut)

    dut.ft_txe.value = 1
    for _ in range(FT_OVERFLOW_TRIGGER_READS):
        await _bus_read(dut, 0x0000)

    dut.ft_txe.value = 0
    overflow = None
    for _ in range(FT_OVERFLOW_TRIGGER_READS + 128):
        rec = await _ft_recv_record(dut, timeout_cycles=60000)
        if _ft_kind(rec) == FT_KIND_OVERFLOW:
            overflow = rec
            break

    assert overflow is not None, "expected FT overflow record"
    assert _ft_kind(overflow) == FT_KIND_OVERFLOW
    assert _ft_overflow_count(overflow) > 0


@cocotb.test()
async def ram_card_writes_reads_and_mirrors_2k(dut):
    await _init(dut)

    await _bus_write(dut, 0x0005, 0x00)
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
async def saleae_control_outputs_and_write_ft_records_report_bus_activity(dut):
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
    dut.ce6.value = 1
    await tick(dut.clk, 1)

    await _enable_ft(dut)

    event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_debug_write = cocotb.start_soon(_fast_uart_recv_bytes(dut.saleae[4], dut.clk, 2))
    data_uart = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[6], dut.clk, 8))
    addr_uart = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[7], dut.clk, 18))
    ft_write = cocotb.start_soon(_ft_recv_records(dut, 2))

    await _bus_write(dut, 0x0012, 0x5A)

    assert await event_write == 0x575A
    assert await ft_debug_write == [ord("W"), ord("W")]
    assert await data_uart == 0x5A
    assert await addr_uart == 0x0012
    assert saleae_bit(int(dut.saleae.value), 5) == 0
    write_records = await ft_write
    assert [_ft_kind(rec) for rec in write_records] == [FT_KIND_CE1_WRITE, FT_KIND_CE1_WRITE]
    assert _ft_addr(write_records[-1]) == 0x0012
    assert _ft_data(write_records[-1]) == 0x5A


@cocotb.test()
async def saleae_read_ft_records_report_bus_activity(dut):
    await _init(dut)

    await _bus_write(dut, 0x0012, 0x5A)
    await _enable_ft(dut)

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_debug_reads = cocotb.start_soon(_fast_uart_recv_bytes(dut.saleae[4], dut.clk, 2))
    ft_reads = cocotb.start_soon(_ft_recv_records(dut, 2))

    assert await _bus_read(dut, 0x0012) == 0x5A
    assert await event_read == 0x525A
    assert await _bus_read(dut, 0x0012) == 0x5A

    assert await ft_debug_reads == [ord("R"), ord("R")]
    reads = await ft_reads
    assert _ft_kind(reads[0]) == FT_KIND_CE1_READ
    assert _ft_kind(reads[1]) == FT_KIND_CE1_READ
    assert _ft_addr(reads[1]) == 0x0012
    assert _ft_data(reads[1]) == 0x5A


@cocotb.test()
async def ce6_low_range_rom_reads_drive_backed_bytes_and_are_logged(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"W021=A7\r\nOK\r\n")))
    await _uart_send_text(dut, "W021=A7\r")
    assert await rx == b"W021=A7\r\nOK\r\n"

    await _enable_ft(dut)

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_read = cocotb.start_soon(_ft_recv_records(dut, 2))
    observed, drive = await _ce6_read(dut, 0x0021, 0x11)
    assert observed == 0xA7
    assert drive == 1
    assert await event_read == 0x72A7
    read_records = await ft_read
    assert [_ft_kind(rec) for rec in read_records] == [FT_KIND_CE6_READ, FT_KIND_CE6_READ]
    assert _ft_addr(read_records[-1]) == 0x0021


@cocotb.test()
async def ce6_reads_alias_on_low16_bits(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"W021=A7\r\nOK\r\n")))
    await _uart_send_text(dut, "W021=A7\r")
    assert await rx == b"W021=A7\r\nOK\r\n"

    await _enable_ft(dut)

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_read = cocotb.start_soon(_ft_recv_records(dut, 2))
    observed, drive = await _ce6_read(dut, 0x10021, 0x11)
    assert observed == 0xA7
    assert drive == 1
    assert await event_read == 0x72A7
    read_records = await ft_read
    assert [_ft_kind(rec) for rec in read_records] == [FT_KIND_CE6_READ, FT_KIND_CE6_READ]
    assert _ft_addr(read_records[-1]) == 0x10021


@cocotb.test()
async def ce6_high_range_reads_remain_passive_and_are_logged(dut):
    await _init(dut)
    await _enable_ft(dut)

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_read = cocotb.start_soon(_ft_recv_records(dut, 2))
    observed, drive = await _ce6_read(dut, 0x0821, 0xA7)
    assert observed == 0xA7
    assert drive == 0
    assert await event_read == 0x72A7
    read_records = await ft_read
    assert [_ft_kind(rec) for rec in read_records] == [FT_KIND_CE6_READ, FT_KIND_CE6_READ]
    assert _ft_addr(read_records[-1]) == 0x0821
    assert _ft_data(read_records[-1]) == 0xA7


@cocotb.test()
async def ce6_write_attempts_are_logged_but_never_drive_bus(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"W021=A7\r\nOK\r\n")))
    await _uart_send_text(dut, "W021=A7\r")
    assert await rx == b"W021=A7\r\nOK\r\n"

    await _enable_ft(dut)

    event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_write = cocotb.start_soon(_ft_recv_records(dut, 2))
    drive = await _ce6_write(dut, 0x0021, 0x3C)
    assert drive == 0
    assert await event_write == 0x773C
    write_records = await ft_write
    assert [_ft_kind(rec) for rec in write_records] == [FT_KIND_CE6_WRITE_ATTEMPT, FT_KIND_CE6_WRITE_ATTEMPT]
    assert _ft_addr(write_records[-1]) == 0x0021
    assert _ft_data(write_records[-1]) == 0x3C
    observed, read_drive = await _ce6_read(dut, 0x0021, 0x11)
    assert observed == 0xA7
    assert read_drive == 1


@cocotb.test()
async def ce6_magic_uart_port_writes_stream_bytes_for_both_aliases(dut):
    await _init(dut)

    rx0 = cocotb.start_soon(_uart_recv_exact(dut, 1))
    assert await _ce6_write(dut, 0x0FFF1, ord("H")) == 0
    assert await rx0 == b"H"

    rx1 = cocotb.start_soon(_uart_recv_exact(dut, 1))
    assert await _ce6_write(dut, 0x1FFF1, ord("i")) == 0
    assert await rx1 == b"i"


@cocotb.test()
async def ce6_control_page_reads_remain_passive_and_are_logged(dut):
    await _init(dut)
    await _enable_ft(dut)

    ft_read = cocotb.start_soon(_ft_recv_records(dut, 2))
    observed, drive = await _ce6_read(dut, 0x1FFF1, 0x5E)
    assert observed == 0x5E
    assert drive == 0
    await _assert_no_fast_uart_start_fall(dut.saleae[3], dut.clk, 128)
    read_records = await ft_read
    assert [_ft_kind(rec) for rec in read_records] == [FT_KIND_CE6_READ, FT_KIND_CE6_READ]
    assert _ft_addr(read_records[-1]) == 0x1FFF1
    assert _ft_data(read_records[-1]) == 0x5E


@cocotb.test()
async def ce6_control_page_writes_use_separate_control_delay(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"t99\r\nT=990ns\r\n")))
    await _uart_send_text(dut, "t99\r")
    assert await rx == b"t99\r\nT=990ns\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"c20\r\nC=200ns\r\n")))
    await _uart_send_text(dut, "c20\r")
    assert await rx == b"c20\r\nC=200ns\r\n"

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))

    dut.addr.value = 0x1FFF1
    dut.ce6.value = 0
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    dut.data_host.value = ord("Z")
    dut.data_host_drive.value = 1
    await tick(dut.clk, 1)
    dut.rw.value = 0
    await _assert_no_fast_uart_start_fall(dut.saleae[3], dut.clk, 10)
    await _assert_no_usb_tx_start_bit(dut, 10)
    await tick(dut.clk, 1)
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    dut.ce6.value = 1
    _set_data_bus_z(dut)

    assert drive == 0
    assert await usb_char == b"Z"
    assert await event_write == 0x775A


@cocotb.test()
async def ce6_control_page_phase_sweep_detects_async_echo_writes(dut):
    await _init(dut)

    cases = [
        (0, 1, ord("A")),
        (1, 3, ord("B")),
        (2, 5, ord("C")),
        (4, 6, ord("D")),
        (5, 8, ord("E")),
        (7, 9, ord("F")),
    ]

    for ce6_phase_ns, rw_phase_ns, value in cases:
        usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
        event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
        drive = await _ce6_ctrl_async_write_phase(
            dut,
            0x1FFF1,
            value,
            ce6_phase_ns=ce6_phase_ns,
            rw_phase_ns=rw_phase_ns,
        )
        assert drive == 0
        assert await usb_char == bytes([value])
        assert await event_write == (0x7700 | value)


@cocotb.test()
async def ce6_control_page_write_can_start_after_addr_enters_range(dut):
    await _init(dut)

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_write = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))

    dut.addr.value = 0x1F000
    dut.ce6.value = 1
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    dut.data_host.value = ord("L")
    dut.data_host_drive.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    await Timer(1, units="ns")
    dut.ce6.value = 0
    await Timer(2, units="ns")
    dut.rw.value = 0
    await Timer(25, units="ns")
    dut.addr.value = 0x1FFF1
    await Timer(120, units="ns")
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    dut.ce6.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)

    assert drive == 0
    assert await usb_char == b"L"
    assert await event_write == 0x774C


@cocotb.test()
async def ce6_control_page_aborted_write_does_not_fire_late(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"c20\r\nC=200ns\r\n")))
    await _uart_send_text(dut, "c20\r")
    assert await rx == b"c20\r\nC=200ns\r\n"

    dut.addr.value = 0x1FFF1
    dut.ce6.value = 1
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 1
    dut.data_host.value = ord("Q")
    dut.data_host_drive.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    await Timer(1, units="ns")
    dut.ce6.value = 0
    await Timer(2, units="ns")
    dut.rw.value = 0
    await Timer(50, units="ns")
    dut.rw.value = 1
    dut.ce6.value = 1
    _set_data_bus_z(dut)

    await _assert_no_fast_uart_start_fall(dut.saleae[3], dut.clk, 40)
    await _assert_no_usb_tx_start_bit(dut, 40)


@cocotb.test()
async def ce6_control_page_c00_and_c01_use_current_cycle_data(dut):
    await _init(dut)

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"c00\r\nC=000ns\r\n")))
    await _uart_send_text(dut, "c00\r")
    assert await rx == b"c00\r\nC=000ns\r\n"

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_word = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF1, ord("A"), ce6_phase_ns=1, rw_phase_ns=3) == 0
    assert await usb_char == b"A"
    assert await event_word == 0x7741

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_word = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF1, ord("B"), ce6_phase_ns=2, rw_phase_ns=5) == 0
    assert await usb_char == b"B"
    assert await event_word == 0x7742

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"c01\r\nC=010ns\r\n")))
    await _uart_send_text(dut, "c01\r")
    assert await rx == b"c01\r\nC=010ns\r\n"

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_word = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF1, ord("C"), ce6_phase_ns=0, rw_phase_ns=2) == 0
    assert await usb_char == b"C"
    assert await event_word == 0x7743

    usb_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    event_word = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF1, ord("D"), ce6_phase_ns=3, rw_phase_ns=6) == 0
    assert await usb_char == b"D"
    assert await event_word == 0x7744


@cocotb.test()
async def ce6_control_page_back_to_back_event_words_are_queued(dut):
    await _init(dut)

    event_words = cocotb.start_soon(_fast_uart_recv_words(dut.saleae[3], dut.clk, 16, 2))
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF0, 0x11, ce6_phase_ns=1, rw_phase_ns=3, hold_low_ns=60) == 0
    assert await _ce6_ctrl_async_write_phase(dut, 0x1FFF2, 0x22, ce6_phase_ns=2, rw_phase_ns=4, hold_low_ns=60) == 0
    assert await event_words == [0x7711, 0x7722]


@cocotb.test()
async def ce6_magic_uart_port_overrun_reports_error(dut):
    await _init(dut)

    first_char = cocotb.start_soon(_uart_recv_exact(dut, 1))
    assert await _ce6_write(dut, 0x0FFF1, ord("A")) == 0
    assert await _ce6_write(dut, 0x1FFF1, ord("B")) == 0
    assert await _ce6_write(dut, 0x1FFF1, ord("C")) == 0

    assert await first_char == b"A"
    assert await _uart_recv_exact(dut, len(b"!OVERRUN\r\n!OVERRUN\r\n")) == b"!OVERRUN\r\n!OVERRUN\r\n"


@cocotb.test()
async def ft_overflow_reports_dropped_accesses_after_host_stall(dut):
    await _init(dut)
    await _enable_ft(dut)

    dut.ft_txe.value = 1
    # E500 now has an 8192-record pre-FT FIFO plus the shared FT tap's
    # 8192-word TX FIFO, which can hold 1638 more full 5-word records.
    for _ in range(FT_OVERFLOW_TRIGGER_READS):
        await _bus_read(dut, 0x0000)

    dut.ft_txe.value = 0
    records = []
    for _ in range(FT_OVERFLOW_TRIGGER_READS + 128):
        rec = await _ft_recv_record(dut, timeout_cycles=60000)
        records.append(rec)
        if _ft_kind(rec) == FT_KIND_OVERFLOW:
            break

    assert records, 'expected at least one FT record after stall'
    assert _ft_kind(records[0]) in (FT_KIND_CE1_READ, FT_KIND_CE1_WRITE, FT_KIND_BUS_CHANGE)
    assert _ft_kind(records[-1]) == FT_KIND_OVERFLOW
    assert _ft_overflow_count(records[-1]) > 0
    assert saleae_bit(int(dut.saleae.value), 5) == 1
    stats = await _disable_ft(dut)
    assert stats["QMX"] <= FT_RECORD_FIFO_RECORDS, stats
    assert stats["TFF"] > 0, stats
