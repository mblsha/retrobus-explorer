# top = main

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


USB_BIT_CYCLES = 100
FAST_UART_CHANNELS = [
    (6, 100_000_000),
    (7, 200_000_000),
]
FAST_BIT_CYCLES = {
    idx: ((400_000_000 + baud) // baud) - 1 for idx, baud in FAST_UART_CHANNELS
}


def saleae_bit(dut, idx: int) -> int:
    return (int(dut.saleae.value) >> idx) & 1


async def send_uart_byte(dut, value: int):
    dut.usb_rx.value = 1
    await tick(dut.clk, USB_BIT_CYCLES)

    dut.usb_rx.value = 0
    await tick(dut.clk, USB_BIT_CYCLES)

    for bit_idx in range(8):
        dut.usb_rx.value = (value >> bit_idx) & 1
        await tick(dut.clk, USB_BIT_CYCLES)

    dut.usb_rx.value = 1
    await tick(dut.clk, USB_BIT_CYCLES)


async def send_uart_text(dut, text: str):
    for ch in text.encode("ascii"):
        await send_uart_byte(dut, ch)


async def recv_uart_byte_from_line(
    dut,
    read_line,
    bit_cycles: int,
    timeout_cycles: int,
    max_resync_attempts: int = 16,
):
    for _ in range(max_resync_attempts):
        prev = read_line()
        saw_high = prev == 1
        for _ in range(timeout_cycles):
            await tick(dut.clk, 1)
            cur = read_line()
            if cur == 1:
                saw_high = True
            if saw_high and prev == 1 and cur == 0:
                break
            prev = cur
        else:
            assert False, "timed out waiting for UART start bit"

        await tick(dut.clk, bit_cycles + (bit_cycles // 2))

        value = 0
        for idx in range(8):
            value |= read_line() << idx
            await tick(dut.clk, bit_cycles)

        stop = read_line()
        if stop == 1:
            return value

    assert False, "failed to decode UART byte after resync attempts"


async def recv_uart_line(dut, timeout_cycles: int = USB_BIT_CYCLES * 150, max_len: int = 160) -> str:
    data = bytearray()
    for _ in range(max_len):
        value = await recv_uart_byte_from_line(
            dut,
            lambda: int(dut.usb_tx.value),
            USB_BIT_CYCLES,
            timeout_cycles=timeout_cycles,
        )
        data.append(value)
        if value == 0x0A:
            return data.decode("ascii", errors="replace")
    assert False, f"line too long without LF: {data!r}"


async def recv_rbx_line(dut, attempts: int = 8) -> str:
    for _ in range(attempts):
        line = await recv_uart_line(dut)
        marker = line.find("RBX ")
        if marker >= 0:
            return line[marker:]
    assert False, "failed to receive RBX-prefixed UART line"


async def recv_rbx_line_matching(dut, token: str, attempts: int = 16) -> str:
    for _ in range(attempts):
        line = await recv_rbx_line(dut)
        if token in line:
            return line
    assert False, f"failed to receive RBX line containing {token!r}"


async def assert_saleae_quiet(dut, first_idx: int = 1, cycles: int = 20):
    for _ in range(cycles):
        await tick(dut.clk, 1)
        for idx in range(first_idx, 8):
            assert saleae_bit(dut, idx) == 0, f"saleae[{idx}] expected low in clock-tester mode"


async def assert_saleae0_toggles(dut, cycles: int = 64):
    saw_zero = False
    saw_one = False
    for _ in range(cycles):
        await tick(dut.clk, 1)
        bit0 = saleae_bit(dut, 0)
        saw_zero |= bit0 == 0
        saw_one |= bit0 == 1
    assert saw_zero and saw_one, "saleae[0] must toggle in clock-tester mode"


@cocotb.test()
async def command_interface_and_mode_switching(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 8)

    dut.rst_n.value = 1
    # Allow the boot banner to drain before issuing command traffic.
    await tick(dut.clk, 30000)

    status_default_task = cocotb.start_soon(recv_rbx_line_matching(dut, "STATUS"))
    await send_uart_text(dut, "!S")
    status_default = await status_default_task
    assert status_default == "RBX STATUS M=C F=0\r\n", f"unexpected default status: {status_default!r}"
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
    await assert_saleae0_toggles(dut, cycles=96)

    help_line_task = cocotb.start_soon(recv_rbx_line_matching(dut, "HELP"))
    await send_uart_text(dut, "!H")
    help_line = await help_line_task
    assert help_line == "RBX HELP !H !S !C !E !F0-5 M:CLOCK E:ECHO\r\n", f"unexpected help: {help_line!r}"

    ok_clock_task = cocotb.start_soon(recv_rbx_line_matching(dut, "OK"))
    await send_uart_text(dut, "!F5")
    ok_clock = await ok_clock_task
    assert ok_clock == "RBX OK M=C F=5\r\n", f"unexpected !F5 response: {ok_clock!r}"

    ok_clock_100_task = cocotb.start_soon(recv_rbx_line_matching(dut, "OK"))
    await send_uart_text(dut, "!F3")
    ok_clock_100 = await ok_clock_100_task
    assert ok_clock_100 == "RBX OK M=C F=3\r\n", f"unexpected !F3 response: {ok_clock_100!r}"
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
    await assert_saleae0_toggles(dut, cycles=48)

    status_clock_task = cocotb.start_soon(recv_rbx_line_matching(dut, "STATUS"))
    await send_uart_text(dut, "!S")
    status_clock = await status_clock_task
    assert status_clock == "RBX STATUS M=C F=3\r\n", f"unexpected status: {status_clock!r}"

    err_freq_task = cocotb.start_soon(recv_rbx_line_matching(dut, "ERR FREQ"))
    await send_uart_text(dut, "!F9")
    err_freq = await err_freq_task
    assert err_freq == "RBX ERR FREQ\r\n", f"unexpected !F9 response: {err_freq!r}"

    ok_echo_task = cocotb.start_soon(recv_rbx_line_matching(dut, "OK"))
    await send_uart_text(dut, "!E")
    ok_echo = await ok_echo_task
    assert ok_echo == "RBX OK M=E F=3\r\n", f"unexpected !E response: {ok_echo!r}"

    payload = 0x41
    echo_task = cocotb.start_soon(
        recv_uart_byte_from_line(
            dut,
            lambda: int(dut.usb_tx.value),
            USB_BIT_CYCLES,
            timeout_cycles=USB_BIT_CYCLES * 80,
        )
    )
    fast_tasks = [
        cocotb.start_soon(
            recv_uart_byte_from_line(
                dut,
                lambda idx=idx: saleae_bit(dut, idx),
                FAST_BIT_CYCLES[idx],
                timeout_cycles=USB_BIT_CYCLES * 120,
            )
        )
        for idx, _ in FAST_UART_CHANNELS
    ]

    await send_uart_byte(dut, payload)
    echoed = await echo_task
    assert echoed == payload, f"usb echo mismatch: expected 0x{payload:02x}, got 0x{echoed:02x}"

    for task_idx, task in enumerate(fast_tasks):
        idx = FAST_UART_CHANNELS[task_idx][0]
        got = await task
        assert got == payload, (
            f"saleae[{idx}] UART mismatch at bit_cycles={FAST_BIT_CYCLES[idx]}: "
            f"expected 0x{payload:02x}, got 0x{got:02x}"
        )

    ok_clock_2_task = cocotb.start_soon(recv_rbx_line_matching(dut, "OK"))
    await send_uart_text(dut, "!C")
    ok_clock_2 = await ok_clock_2_task
    assert ok_clock_2 == "RBX OK M=C F=3\r\n", f"unexpected !C response: {ok_clock_2!r}"
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
