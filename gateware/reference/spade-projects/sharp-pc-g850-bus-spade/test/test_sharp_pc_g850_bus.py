# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


CLK_PER_UART_BIT = 100


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
    await tick(dut.clk, CLK_PER_UART_BIT * 2)


async def _uart_recv_byte(dut, timeout_cycles: int = 8000) -> int:
    for _ in range(timeout_cycles):
        if int(dut.usb_tx.value) == 0:
            break
        await tick(dut.clk, 1)
    else:
        raise AssertionError("timeout waiting for UART start bit on usb_tx")

    await tick(dut.clk, CLK_PER_UART_BIT + (CLK_PER_UART_BIT // 2))

    value = 0
    for idx in range(8):
        bit = int(dut.usb_tx.value)
        value |= bit << idx
        await tick(dut.clk, CLK_PER_UART_BIT)

    stop = int(dut.usb_tx.value)
    assert stop == 1, f"invalid UART stop bit: {stop}"
    return value


async def _uart_recv_until(dut, expected: int, max_bytes: int = 8):
    seen: list[int] = []
    for _ in range(max_bytes):
        value = await _uart_recv_byte(dut)
        seen.append(value)
        if value == expected:
            return
    raise AssertionError(
        f"expected UART byte 0x{expected:02x}, saw {[f'0x{v:02x}' for v in seen]}"
    )


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
async def data_mode_emits_event_and_address_uart_on_saleae(dut):
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
    assert _saleae_bit(idle_saleae, 6) == 1
    assert _saleae_bit(idle_saleae, 7) == 1

    dut.z80_mreq.value = 0
    await tick(dut.clk, 10)
    dut.z80_rd.value = 0
    await tick(dut.clk, 8)
    dut.z80_rd.value = 1

    saw_event_start = False
    saw_addr_start = False
    for _ in range(300):
        v = int(dut.saleae.value)
        if _saleae_bit(v, 6) == 0:
            saw_event_start = True
        if _saleae_bit(v, 7) == 0:
            saw_addr_start = True
        if saw_event_start and saw_addr_start:
            break
        await tick(dut.clk, 1)

    assert saw_event_start, "expected tx_event UART start bit on saleae[6]"
    assert saw_addr_start, "expected tx_addr UART start bit on saleae[7]"


@cocotb.test()
async def invalid_read_bus_state_reports_error_over_usb_uart(dut):
    await _init(dut)

    dut.z80_mreq.value = 1
    dut.z80_iorq.value = 1
    dut.z80_rd.value = 1
    await tick(dut.clk, 8)

    dut.z80_rd.value = 0
    await tick(dut.clk, 8)
    dut.z80_rd.value = 1

    err = await _uart_recv_byte(dut)
    assert err == ord("E"), f"expected 'E' on invalid read combination, got 0x{err:02x}"


@cocotb.test()
async def ft_host_stream_commands_toggle_enable_and_echo(dut):
    await _init(dut)

    assert (int(dut.led.value) & 0x1) == 0, "expected FT streaming disabled after reset"

    # Host sends "S+" as a single 16-bit FT word (little-endian bytes: 0x53, 0x2b).
    await _ft_host_send_word(dut, 0x2B53)
    await _wait_led0(dut, 1)
    plus = await _uart_recv_byte(dut)
    assert plus == ord("+"), f"expected '+' echo for FT enable command, got 0x{plus:02x}"

    # Host sends "S-" to disable stream mode.
    await _ft_host_send_word(dut, 0x2D53)
    await _wait_led0(dut, 0)
