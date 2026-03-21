# top = main

import json
from pathlib import Path

import cocotb
from cocotb.triggers import FallingEdge, RisingEdge, Timer

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
DEFAULT_CLASSIFY_CYCLES = 50
TAIL_CYCLES = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FT_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
FT_CE6_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_ce6.ft16"
FT_OVERFLOW_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_overflow_record.ft16"

FT_KIND_CE1_READ = 0x01
FT_KIND_CE1_WRITE = 0x02
FT_KIND_CE6_READ = 0x03
FT_KIND_CE6_WRITE_ATTEMPT = 0x04
FT_KIND_SYNC = 0xF0
FT_KIND_OVERFLOW = 0xF1
FT_KIND_CONFIG = 0xF2


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


async def _fast_uart_recv_word(signal, clk, width: int, timeout_cycles: int = 128) -> int:
    await _fast_uart_wait_start_fall(signal, clk, timeout_cycles)
    value = 0
    for idx in range(width):
        await tick(clk, 1)
        value |= int(signal.value) << idx
    await tick(clk, 1)
    assert int(signal.value) == 1, "invalid fast-UART stop bit"
    return value


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
    dut.ce6.value = 0
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


async def _enable_ft(dut):
    ft_records = cocotb.start_soon(_ft_recv_records(dut, 2))
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"f1\r\nF=1\r\n")))
    await _uart_send_text(dut, "f1\r")
    assert await rx == b"f1\r\nF=1\r\n"
    sync, config = await ft_records
    return sync, config


async def _disable_ft(dut):
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"f0\r\nF=0\r\n")))
    await _uart_send_text(dut, "f0\r")
    assert await rx == b"f0\r\nF=0\r\n"


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
        dut.ce6.value = 0
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
    dut.ce6.value = 1
    dut.ce1.value = 0
    dut.rw.value = 1
    dut.oe.value = 0
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    observed = int(dut.data.value) & 0xFF
    drive = int(dut.data_oe.value)
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce6.value = 0
    dut.oe.value = 1
    _set_data_bus_z(dut)
    await tick(dut.clk, 2)
    return observed, drive


async def _ce6_write(dut, addr: int, value: int, classify_cycles: int = DEFAULT_CLASSIFY_CYCLES):
    dut.addr.value = addr & 0x3FFFF
    dut.ce6.value = 1
    dut.ce1.value = 0
    dut.rw.value = 0
    dut.oe.value = 1
    dut.data_host.value = value & 0xFF
    dut.data_host_drive.value = 1
    await tick(dut.clk, classify_cycles + 2)
    drive = int(dut.data_oe.value)
    dut.rw.value = 1
    await tick(dut.clk, TAIL_CYCLES)
    dut.ce6.value = 0
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

    await _bus_write(dut, 0x0005, 0x3C)
    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"r005\r\n005=3C\r\n")))
    await _uart_send_text(dut, "r005\r")
    assert await rx == b"r005\r\n005=3C\r\n"

    rx = cocotb.start_soon(_uart_recv_exact(dut, len(b"\r\nERR\r\n")))
    await _uart_send_text(dut, "x\r")
    assert await rx == b"\r\nERR\r\n"

    await _disable_ft(dut)
    sync, config = await _enable_ft(dut)
    assert _ft_kind(sync) == FT_KIND_SYNC
    assert _ft_kind(config) == FT_KIND_CONFIG


@cocotb.test()
async def usb_uart_write_collisions_return_busy_and_do_not_commit_uart_write(dut):
    await _init(dut)

    phase = await _find_uart_write_collision_phase(dut, "w005=A5\r")

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    dut.rw.value = 1
    dut.oe.value = 1
    dut.ce1.value = 0
    dut.ce6.value = 0
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
    dut.ce6.value = 0
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
async def ft_access_fixture_matches_hdl_bytes(dut):
    await _init(dut)

    sync, config = await _enable_ft(dut)
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

    sync, config = await _enable_ft(dut)
    records = cocotb.start_soon(_ft_recv_records(dut, 2))
    await _ce6_read(dut, 0x0021, 0xA7)
    await _ce6_write(dut, 0x0021, 0x3C)

    expected = FT_CE6_FIXTURE_PATH.read_bytes()
    actual = _ft_records_to_bytes([sync, config] + await records)
    assert actual == expected, f"actual={actual.hex()} expected={expected.hex()}"


@cocotb.test()
async def ft_overflow_record_fixture_matches_hdl_bytes(dut):
    await _init(dut)
    await _enable_ft(dut)

    dut.ft_txe.value = 1
    for _ in range(2000):
        await _bus_read(dut, 0x0000)

    dut.ft_txe.value = 0
    overflow = None
    for _ in range(2100):
        rec = await _ft_recv_record(dut, timeout_cycles=60000)
        if _ft_kind(rec) == FT_KIND_OVERFLOW:
            overflow = rec
            break

    assert overflow is not None, "expected FT overflow record"
    expected = FT_OVERFLOW_FIXTURE_PATH.read_bytes()
    actual = _ft_records_to_bytes([overflow])
    assert actual == expected, f"actual={actual.hex()} expected={expected.hex()}"


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
async def saleae_sniffers_and_ft_records_report_bus_activity(dut):
    await _init(dut)
    await _enable_ft(dut)

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
    ft_write = cocotb.start_soon(_ft_recv_record(dut))

    await _bus_write(dut, 0x0012, 0x5A)

    assert await event_write == 0x575A
    assert await data_uart == 0x5A
    assert await addr_uart == 0x0012
    rec = await ft_write
    assert _ft_kind(rec) == FT_KIND_CE1_WRITE
    assert _ft_addr(rec) == 0x0012
    assert _ft_data(rec) == 0x5A

    event_read = cocotb.start_soon(_fast_uart_recv_word(dut.saleae[3], dut.clk, 16))
    ft_reads = cocotb.start_soon(_ft_recv_records(dut, 2))
    assert await _bus_read(dut, 0x0012) == 0x5A
    assert await event_read == 0x525A
    assert await _bus_read(dut, 0x0012) == 0x5A
    reads = await ft_reads
    assert _ft_kind(reads[0]) == FT_KIND_CE1_READ
    assert _ft_kind(reads[1]) == FT_KIND_CE1_READ
    assert _ft_addr(reads[0]) == 0x0012
    assert _ft_addr(reads[1]) == 0x0012
    assert _ft_data(reads[0]) == 0x5A
    assert _ft_data(reads[1]) == 0x5A
    assert (_ft_aux(reads[1]) >> 4) & 0x1 == 1
    assert (_ft_aux(reads[1]) >> 5) & 0x1 == 1


@cocotb.test()
async def ce6_events_are_logged_but_never_drive_bus(dut):
    await _init(dut)
    await _enable_ft(dut)

    ft_read = cocotb.start_soon(_ft_recv_record(dut))
    observed, drive = await _ce6_read(dut, 0x0021, 0xA7)
    assert observed == 0xA7
    assert drive == 0
    rec = await ft_read
    assert _ft_kind(rec) == FT_KIND_CE6_READ
    assert _ft_addr(rec) == 0x0021
    assert _ft_data(rec) == 0xA7

    ft_write = cocotb.start_soon(_ft_recv_record(dut))
    drive = await _ce6_write(dut, 0x0021, 0x3C)
    assert drive == 0
    rec = await ft_write
    assert _ft_kind(rec) == FT_KIND_CE6_WRITE_ATTEMPT
    assert _ft_addr(rec) == 0x0021
    assert _ft_data(rec) == 0x3C
    assert await _bus_read(dut, 0x0021) == 0x00


@cocotb.test()
async def ft_overflow_reports_dropped_accesses_after_host_stall(dut):
    await _init(dut)
    await _enable_ft(dut)

    dut.ft_txe.value = 1
    # au_ft_tap_u16 has an 8192-word TX FIFO, so this needs to exceed
    # roughly 1638 full 5-word FT records before overflow can occur.
    for _ in range(2000):
        await _bus_read(dut, 0x0000)

    dut.ft_txe.value = 0
    records = []
    for _ in range(2100):
        rec = await _ft_recv_record(dut, timeout_cycles=60000)
        records.append(rec)
        if _ft_kind(rec) == FT_KIND_OVERFLOW:
            break

    assert records, 'expected at least one FT record after stall'
    assert _ft_kind(records[0]) == FT_KIND_CE1_READ
    assert _ft_kind(records[-1]) == FT_KIND_OVERFLOW
    for rec in records[:-1]:
        assert _ft_kind(rec) == FT_KIND_CE1_READ
    assert _ft_overflow_count(records[-1]) > 0
