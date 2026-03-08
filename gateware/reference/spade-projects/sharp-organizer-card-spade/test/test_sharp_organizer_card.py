# top = main

import cocotb
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_UART_BIT_CYCLES = 100
SALEAE_UART_BIT_CYCLES = 4


def _saleae_bit(value: int, idx: int) -> int:
    return (value >> idx) & 1


def _set_ft_bus_z(dut):
    dut.ft_data_host.value = 0
    dut.ft_be_host.value = 0
    dut.ft_host_drive.value = 0


def _misc_word(
    rw: int,
    oe: int,
    ci: int,
    e2: int,
    mskrom: int,
    sram1: int,
    sram2: int,
    eprom: int,
    stnby: int,
    vbatt: int,
    vpp: int,
) -> int:
    return (
        (rw << 10)
        | (oe << 9)
        | (ci << 8)
        | (e2 << 7)
        | (mskrom << 6)
        | (sram1 << 5)
        | (sram2 << 4)
        | (eprom << 3)
        | (stnby << 2)
        | (vbatt << 1)
        | vpp
    )


async def _init(dut):
    start_clock(dut.clk)
    start_clock(dut.ft_clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1

    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    _set_ft_bus_z(dut)

    dut.conn_rw.value = 0
    dut.conn_oe.value = 0
    dut.conn_ci.value = 0
    dut.conn_e2.value = 0
    dut.conn_mskrom.value = 0
    dut.conn_sram1.value = 0
    dut.conn_sram2.value = 0
    dut.conn_eprom.value = 0
    dut.conn_stnby.value = 0
    dut.conn_vbatt.value = 0
    dut.conn_vpp.value = 0
    dut.addr.value = 0
    dut.data.value = 0

    await tick(dut.clk, 6)
    dut.rst_n.value = 1
    await tick(dut.clk, 10)


async def _uart_send_byte(dut, byte: int):
    dut.usb_rx.value = 1
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    dut.usb_rx.value = 0
    await tick(dut.clk, USB_UART_BIT_CYCLES)

    for idx in range(8):
        dut.usb_rx.value = (byte >> idx) & 1
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
    assert stop == 1, f"invalid USB UART stop bit: {stop}"
    return value


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
    raise AssertionError("timeout waiting for FT read handshake")


async def _collect_ft_writes(dut, count: int, timeout_cycles: int = 4000) -> list[tuple[int, int]]:
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


async def _ft_recv_stream_word(dut, timeout_cycles: int = 4000) -> int:
    words = await _collect_ft_writes(dut, 2, timeout_cycles)
    assert words[0][1] == 0x3
    assert words[1][1] == 0x3
    return words[0][0] | (words[1][0] << 16)


async def _wait_saleae_fall(dut, bit_idx: int, timeout_cycles: int = 4000):
    prev = _saleae_bit(int(dut.saleae.value), bit_idx)
    for _ in range(timeout_cycles):
        cur = _saleae_bit(int(dut.saleae.value), bit_idx)
        if prev == 1 and cur == 0:
            return
        prev = cur
        await tick(dut.clk, 1)
    raise AssertionError(f"timeout waiting for saleae[{bit_idx}] UART start bit")


async def _uart_recv_saleae_word(dut, bit_idx: int, width: int, timeout_cycles: int = 4000) -> int:
    await _wait_saleae_fall(dut, bit_idx, timeout_cycles)

    await tick(dut.clk, SALEAE_UART_BIT_CYCLES + (SALEAE_UART_BIT_CYCLES // 2))

    value = 0
    for idx in range(width):
        value |= _saleae_bit(int(dut.saleae.value), bit_idx) << idx
        await tick(dut.clk, SALEAE_UART_BIT_CYCLES)

    stop = _saleae_bit(int(dut.saleae.value), bit_idx)
    assert stop == 1, f"invalid stop bit on saleae[{bit_idx}]"
    return value


@cocotb.test()
async def leds_and_ft_host_commands_match_lucid(dut):
    await _init(dut)

    assert int(dut.led.value) == 0x02
    dut.ft_rxf.value = 0
    dut.ft_txe.value = 0
    await tick(dut.clk, 1)
    assert int(dut.led.value) & 0x30 == 0x30
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    await tick(dut.clk, 1)

    recv_plus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    assert await recv_plus == ord("+")
    await tick(dut.clk, 4)
    assert int(dut.led.value) & 0x01 == 1

    await tick(dut.clk, USB_UART_BIT_CYCLES)
    recv_minus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("-") << 8))
    assert await recv_minus == ord("-")
    await tick(dut.clk, 4)
    assert int(dut.led.value) & 0x01 == 0


@cocotb.test()
async def usb_uart_commands_select_saleae_modes_and_echo(dut):
    await _init(dut)

    dut.conn_rw.value = 1
    dut.conn_oe.value = 0
    dut.conn_ci.value = 1
    dut.conn_e2.value = 0
    dut.conn_mskrom.value = 1
    dut.conn_sram1.value = 0
    dut.conn_sram2.value = 1
    dut.conn_eprom.value = 0
    dut.conn_stnby.value = 1
    dut.conn_vbatt.value = 0
    dut.conn_vpp.value = 1
    await tick(dut.clk, 4)

    recv_standard = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, ord("s"))
    assert await recv_standard == ord("s")
    await tick(dut.clk, 4)
    assert int(dut.saleae.value) == 0xF5

    await tick(dut.clk, USB_UART_BIT_CYCLES)
    recv_memory = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, ord("S"))
    assert await recv_memory == ord("S")
    await tick(dut.clk, 4)
    assert int(dut.saleae.value) == 0xEB


@cocotb.test()
async def counter_mode_increments_every_cycle(dut):
    await _init(dut)

    recv_counter = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, ord("c"))
    assert await recv_counter == ord("c")
    await tick(dut.clk, 4)

    c0 = int(dut.saleae.value)
    await tick(dut.clk, 1)
    c1 = int(dut.saleae.value)
    await tick(dut.clk, 1)
    c2 = int(dut.saleae.value)
    assert (c1 - c0) & 0xFF == 1
    assert (c2 - c1) & 0xFF == 1


@cocotb.test()
async def stable_bus_changes_emit_debounced_uart_monitor_streams(dut):
    await _init(dut)

    recv_standard = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, ord("s"))
    assert await recv_standard == ord("s")
    await tick(dut.clk, 4)

    dut.conn_rw.value = 1
    dut.conn_oe.value = 0
    dut.conn_ci.value = 1
    dut.conn_e2.value = 0
    dut.conn_mskrom.value = 1
    dut.conn_sram1.value = 0
    dut.conn_sram2.value = 1
    dut.conn_eprom.value = 0
    dut.conn_stnby.value = 1
    dut.conn_vbatt.value = 0
    dut.conn_vpp.value = 1
    dut.addr.value = 0x5A35
    dut.data.value = 0xC3

    await tick(dut.clk, 5)
    saleae_before = int(dut.saleae.value)
    assert _saleae_bit(saleae_before, 5) == 1
    assert _saleae_bit(saleae_before, 6) == 1
    assert _saleae_bit(saleae_before, 7) == 1

    expected_misc = _misc_word(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1)

    addr_task = cocotb.start_soon(_uart_recv_saleae_word(dut, 7, 20))
    data_task = cocotb.start_soon(_uart_recv_saleae_word(dut, 6, 8))
    misc_task = cocotb.start_soon(_uart_recv_saleae_word(dut, 5, 11))

    assert await addr_task == 0x5A35
    assert await data_task == 0xC3
    assert await misc_task == expected_misc


@cocotb.test()
async def ft_stream_emits_tagged_monitor_words_when_enabled(dut):
    await _init(dut)

    recv_plus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    assert await recv_plus == ord("+")
    await tick(dut.clk, 4)

    dut.ft_txe.value = 0

    dut.addr.value = 0x13579
    await tick(dut.clk, 16)
    assert await _ft_recv_stream_word(dut) == ((ord("A") << 24) | 0x13579)

    dut.data.value = 0xC3
    await tick(dut.clk, 16)
    assert await _ft_recv_stream_word(dut) == ((ord("D") << 24) | 0xC3)

    dut.conn_rw.value = 1
    dut.conn_ci.value = 1
    dut.conn_mskrom.value = 1
    dut.conn_sram2.value = 1
    dut.conn_stnby.value = 1
    dut.conn_vpp.value = 1
    expected_misc = _misc_word(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1)
    await tick(dut.clk, 16)
    assert await _ft_recv_stream_word(dut) == ((ord("M") << 24) | expected_misc)


@cocotb.test()
async def ft_stream_queues_simultaneous_samples_before_overflowing(dut):
    await _init(dut)

    recv_plus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    assert await recv_plus == ord("+")
    await tick(dut.clk, 4)

    dut.ft_txe.value = 1
    dut.addr.value = 0x2468A
    dut.data.value = 0x5C
    dut.conn_rw.value = 1
    dut.conn_ci.value = 1
    dut.conn_mskrom.value = 1
    dut.conn_sram2.value = 1
    dut.conn_stnby.value = 1
    dut.conn_vpp.value = 1
    await tick(dut.clk, 16)

    dut.ft_txe.value = 0
    assert await _ft_recv_stream_word(dut) == ((ord("A") << 24) | 0x2468A)
    assert await _ft_recv_stream_word(dut) == ((ord("D") << 24) | 0x5C)
    assert await _ft_recv_stream_word(dut) == ((ord("M") << 24) | _misc_word(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1))


@cocotb.test()
async def ft_stream_preserves_later_stable_samples_under_ft_backpressure(dut):
    await _init(dut)

    recv_plus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    assert await recv_plus == ord("+")
    await tick(dut.clk, 4)

    dut.ft_txe.value = 1

    dut.addr.value = 0x2468A
    dut.data.value = 0x5C
    dut.conn_rw.value = 1
    dut.conn_ci.value = 1
    dut.conn_mskrom.value = 1
    dut.conn_sram2.value = 1
    dut.conn_stnby.value = 1
    dut.conn_vpp.value = 1
    await tick(dut.clk, 16)

    dut.addr.value = 0x13579
    await tick(dut.clk, 16)

    dut.data.value = 0xC3
    await tick(dut.clk, 16)

    dut.ft_txe.value = 0
    assert await _ft_recv_stream_word(dut) == ((ord("A") << 24) | 0x2468A)
    assert await _ft_recv_stream_word(dut) == ((ord("D") << 24) | 0x5C)
    assert await _ft_recv_stream_word(dut) == ((ord("M") << 24) | _misc_word(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1))
    assert await _ft_recv_stream_word(dut) == ((ord("A") << 24) | 0x13579)
    assert await _ft_recv_stream_word(dut) == ((ord("D") << 24) | 0xC3)


@cocotb.test()
async def reply_stream_delivers_sequential_messages_with_shared_stream_state(dut):
    await _init(dut)

    recv_first = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    await tick(dut.clk, 20)
    await _ft_host_send_word(dut, ord("S") | (ord("-") << 8))
    await tick(dut.clk, 20)
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))

    assert await recv_first == ord("+")
    recv_second = cocotb.start_soon(_uart_recv_byte(dut))
    assert await recv_second == ord("-")
    recv_third = cocotb.start_soon(_uart_recv_byte(dut))
    assert await recv_third == ord("+")


@cocotb.test()
async def ft_stream_and_command_replies_survive_contention_and_backpressure(dut):
    await _init(dut)

    recv_plus = cocotb.start_soon(_uart_recv_byte(dut))
    await _ft_host_send_word(dut, ord("S") | (ord("+") << 8))
    assert await recv_plus == ord("+")
    await tick(dut.clk, 4)

    dut.ft_txe.value = 1
    dut.addr.value = 0x2468A
    await tick(dut.clk, 16)

    recv_counter = cocotb.start_soon(_uart_recv_byte(dut))
    await _uart_send_byte(dut, ord("c"))
    await tick(dut.clk, 20)
    await _ft_host_send_word(dut, ord("S") | (ord("-") << 8))

    assert await recv_counter == ord("c")
    recv_disable = cocotb.start_soon(_uart_recv_byte(dut))
    assert await recv_disable == ord("-")

    await tick(dut.clk, 8)
    assert int(dut.led.value) & 0x01 == 0

    dut.ft_txe.value = 0
    assert await _ft_recv_stream_word(dut) == ((ord("A") << 24) | 0x2468A)
