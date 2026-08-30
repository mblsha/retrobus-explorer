# top = main

import cocotb
from boot_banner_test import assert_boot_banner
from cocotb_helpers import start_clock
from cocotb_helpers import tick
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


CLK_PER_UART_BIT = 100

EXPECTED_HELP_LINES = [
    "Help:\r\n",
    " h : show help\r\n",
    " q : show status (f,r,a,w,m)\r\n",
    " l : show saleae map + legend\r\n",
    " d/s/e/r/c : select saleae mode\r\n",
    "   d=data s=sync e=edge r=raw c=counter\r\n",
    " 0..9 : set wait level (0=min wait)\r\n",
    " a/k : arm or lock FT control\r\n",
    " p/o : allow or block FT remote\r\n",
    " f/x : force FT stream on/off\r\n",
    " legend char_uart: M=op_fetch R=mem_rd r=io_rd W=mem_wr w=io_wr\r\n",
    " note: commands are case-insensitive\r\n",
]


def _saleae_bit(value: int, idx: int) -> int:
    return (value >> idx) & 1


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

    dut.z80_mreq.value = 1
    dut.z80_m1.value = 1
    dut.z80_ioreset.value = 0
    dut.z80_iorq.value = 1
    dut.z80_int1.value = 0
    dut.z80_rd.value = 1
    dut.z80_wr.value = 1

    dut.data.value = 0
    dut.addr.value = 0
    dut.addr_bnk.value = 0
    dut.addr_ceram2.value = 0
    dut.addr_cerom2.value = 0

    await tick(dut.clk, 6)
    dut.rst_n.value = 1
    await tick(dut.clk, 10)
    await _expect_boot_banner(dut, "sharp-pc-g850-bus-spade")


async def _ft_host_send_word(dut, word: int, timeout_cycles: int = 2000):
    dut.ft_data_host.value = word & 0xFFFF
    dut.ft_be_host.value = 0x3
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
    else:
        raise AssertionError("timeout waiting for FT read handshake (ft_oe=0 and ft_rd=0)")


async def _wait_led0(dut, expected: int, timeout_cycles: int = 4000):
    for _ in range(timeout_cycles):
        if (int(dut.led.value) & 0x1) == (expected & 0x1):
            return
        await tick(dut.clk, 1)
    raise AssertionError(f"timeout waiting for led[0]={expected & 0x1}")


async def _uart_send_byte(dut, byte: int):
    dut.usb_rx.value = 1
    await tick(dut.clk, CLK_PER_UART_BIT)

    dut.usb_rx.value = 0
    await tick(dut.clk, CLK_PER_UART_BIT)

    for idx in range(8):
        dut.usb_rx.value = (byte >> idx) & 1
        await tick(dut.clk, CLK_PER_UART_BIT)

    dut.usb_rx.value = 1
    await tick(dut.clk, CLK_PER_UART_BIT)


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
    raise AssertionError("timeout waiting for UART start bit on usb_tx")


async def _uart_recv_byte(dut, timeout_cycles: int = 12000) -> int:
    await _uart_wait_start_fall(dut, timeout_cycles)

    await tick(dut.clk, CLK_PER_UART_BIT + (CLK_PER_UART_BIT // 2))

    value = 0
    for idx in range(8):
        bit = int(dut.usb_tx.value)
        value |= bit << idx
        await tick(dut.clk, CLK_PER_UART_BIT)

    stop = int(dut.usb_tx.value)
    assert stop == 1, f"invalid UART stop bit: {stop}"
    await tick(dut.clk, CLK_PER_UART_BIT // 2)
    return value


async def _uart_recv_line(dut, max_bytes: int = 128) -> bytes:
    out = bytearray()
    for _ in range(max_bytes):
        out.append(await _uart_recv_byte(dut))
        if out[-1] == 0x0A:
            return bytes(out)
    raise AssertionError("timeout waiting for UART line terminator")


async def _uart_recv_lines(dut, count: int) -> list[bytes]:
    lines: list[bytes] = []
    for _ in range(count):
        lines.append(await _uart_recv_line(dut))
    return lines


async def _expect_boot_banner(dut, project_name: str) -> None:
    assert_boot_banner(await _uart_recv_line(dut, max_bytes=160), project_name)


@cocotb.test()
async def uart_commands_control_wait_and_saleae_mode(dut):
    await _init(dut)

    await _uart_send_byte(dut, ord("1"))
    await tick(dut.clk, CLK_PER_UART_BIT * 4)

    dut.z80_mreq.value = 0
    saw_wait_low = False
    for _ in range(160):
        if int(dut.z80_wait.value) == 0:
            saw_wait_low = True
        await tick(dut.clk, 1)
    dut.z80_mreq.value = 1
    assert saw_wait_low, "expected wait insertion after enabling wait depth with UART digit command"

    await _uart_send_byte(dut, ord("c"))
    await tick(dut.clk, CLK_PER_UART_BIT * 4)
    await tick(dut.clk, 4)

    c0 = int(dut.saleae.value)
    await tick(dut.clk, 1)
    c1 = int(dut.saleae.value)
    await tick(dut.clk, 1)
    c2 = int(dut.saleae.value)
    assert (c1 - c0) & 0xFF == 1
    assert (c2 - c1) & 0xFF == 1


@cocotb.test()
async def data_mode_emits_data_event_and_address_uart_on_saleae(dut):
    await _init(dut)

    await _uart_send_byte(dut, ord("0"))
    await tick(dut.clk, CLK_PER_UART_BIT * 4)
    await _uart_send_byte(dut, ord("d"))
    await tick(dut.clk, CLK_PER_UART_BIT * 4)

    dut.addr.value = 0x1234
    dut.data.value = 0xA5
    dut.z80_m1.value = 1
    dut.z80_iorq.value = 1
    dut.z80_mreq.value = 1
    dut.z80_rd.value = 1
    await tick(dut.clk, 8)

    idle_saleae = int(dut.saleae.value)
    assert _saleae_bit(idle_saleae, 5) == 1
    assert _saleae_bit(idle_saleae, 6) == 1
    assert _saleae_bit(idle_saleae, 7) == 1

    dut.z80_mreq.value = 0
    await tick(dut.clk, 10)
    dut.z80_rd.value = 0
    await tick(dut.clk, 8)
    dut.z80_rd.value = 1

    saw_data_start = False
    saw_event_start = False
    saw_addr_start = False
    for _ in range(300):
        v = int(dut.saleae.value)
        if _saleae_bit(v, 5) == 0:
            saw_data_start = True
        if _saleae_bit(v, 6) == 0:
            saw_event_start = True
        if _saleae_bit(v, 7) == 0:
            saw_addr_start = True
        if saw_data_start and saw_event_start and saw_addr_start:
            break
        await tick(dut.clk, 1)

    assert saw_data_start, "expected tx_data UART start bit on saleae[5]"
    assert saw_event_start, "expected tx_event UART start bit on saleae[6]"
    assert saw_addr_start, "expected tx_addr UART start bit on saleae[7]"


@cocotb.test()
async def invalid_read_bus_state_reports_error_over_usb_uart(dut):
    await _init(dut)

    err_task = cocotb.start_soon(_uart_recv_byte(dut))

    dut.z80_mreq.value = 1
    dut.z80_iorq.value = 1
    dut.z80_rd.value = 1
    await tick(dut.clk, 8)

    dut.z80_rd.value = 0
    await tick(dut.clk, 8)
    dut.z80_rd.value = 1

    err = await err_task
    assert err == ord("E"), f"expected 'E' on invalid read combination, got 0x{err:02x}"


@cocotb.test()
async def ft_host_stream_commands_toggle_enable_and_echo(dut):
    await _init(dut)

    assert (int(dut.led.value) & 0x1) == 0, "expected FT streaming disabled after reset"

    # Host sends "S+" while FT remote is locked: command must be ignored.
    await _ft_host_send_word(dut, 0x2B53)
    await tick(dut.clk, 200)
    assert (int(dut.led.value) & 0x1) == 0, "FT host command should be ignored while locked"

    # USB console unlock sequence: arm + remote-on.
    arm_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "a")
    arm_line = (await arm_task).decode("ascii")
    assert arm_line == "ok\r\n", f"unexpected arm response: {arm_line!r}"

    remote_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "p")
    remote_line = (await remote_task).decode("ascii")
    assert remote_line == "ok\r\n", f"unexpected remote-enable response: {remote_line!r}"

    # Host sends "S+" again; now it should enable stream mode.
    await _ft_host_send_word(dut, 0x2B53)
    await _wait_led0(dut, 1)

    # Host sends "S-" to disable stream mode.
    await _ft_host_send_word(dut, 0x2D53)
    await _wait_led0(dut, 0)


@cocotb.test()
async def uart_help_and_status_commands_report_state(dut):
    await _init(dut)

    help_task = cocotb.start_soon(_uart_recv_lines(dut, 12))
    await _uart_send_text(dut, "h")
    help_lines = [line.decode("ascii") for line in await help_task]
    assert help_lines == EXPECTED_HELP_LINES, f"unexpected help lines: {help_lines!r}"

    status_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "q")
    status_line = (await status_task).decode("ascii")
    assert status_line == "stat f=0 r=0 a=0 w=0 m=d\r\n", f"unexpected status line: {status_line!r}"

    # Arm + direct enable from USB, then verify status reflects FT state bits.
    arm_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "a")
    assert (await arm_task).decode("ascii") == "ok\r\n"
    ft_on_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "f")
    assert (await ft_on_task).decode("ascii") == "ok\r\n"

    status_on_task = cocotb.start_soon(_uart_recv_line(dut))
    await _uart_send_text(dut, "q")
    status_on = (await status_on_task).decode("ascii")
    assert status_on == "stat f=1 r=0 a=1 w=0 m=d\r\n", f"unexpected status line after enable: {status_on!r}"


@cocotb.test()
async def uart_unknown_command_prints_help(dut):
    await _init(dut)

    help_task = cocotb.start_soon(_uart_recv_lines(dut, 12))
    await _uart_send_text(dut, "?")
    help_lines = [line.decode("ascii") for line in await help_task]
    assert help_lines == EXPECTED_HELP_LINES, f"unexpected help lines for unknown command: {help_lines!r}"


@cocotb.test()
async def uart_map_command_reports_saleae_pin_meanings(dut):
    await _init(dut)

    map_task = cocotb.start_soon(_uart_recv_lines(dut, 9))
    await _uart_send_text(dut, "l")
    map_lines = [line.decode("ascii") for line in await map_task]
    assert map_lines == [
        "map mode=d\r\n",
        "d: d0=wr_sync d1=rd_sync d2=iorq_sync d3=mreq_sync\r\n",
        "   d4=m1_sync d5=data_uart d6=char_uart d7=addr_uart\r\n",
        "s: d0=wr_rise d1=rd_rise d2=mreq_fall d3=m1_sync d4=wr_sync d5=rd_sync d6=iorq_sync d7=mreq_sync\r\n",
        "e: d0=wr_rise d1=rd_rise d2=iorq_fall d3=mreq_fall d4=wr_sync d5=rd_sync d6=iorq_sync d7=mreq_sync\r\n",
        "r: d0=wr_raw d1=rd_raw d2=iorq_raw d3=mreq_raw d4=wr_sync d5=rd_sync d6=iorq_sync d7=mreq_sync\r\n",
        "c: d0..d7=ctr[0..7]\r\n",
        "legend: u=uart s=sync ^=fall n=active_low\r\n",
        "legend char_uart: M=op_fetch R=mem_rd r=io_rd W=mem_wr w=io_wr\r\n",
    ], f"unexpected map lines: {map_lines!r}"
