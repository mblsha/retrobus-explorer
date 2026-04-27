# top = main

import cocotb
from cocotb.triggers import Edge
from cocotb.triggers import with_timeout
from cocotb.utils import get_sim_time
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
FREQ_HALF_PERIOD_PS = {
    # Under VERILATOR, clk_wiz_0.v models 200/400 outputs as passthrough of 100 MHz input.
    # So clk_fast and probe clocks are both 100 MHz in simulation.
    0: 160_000,  # clk_div[4] -> 3.125 MHz
    1: 80_000,   # clk_div[3] -> 6.25 MHz
    2: 40_000,   # clk_div[2] -> 12.5 MHz
    3: 20_000,   # clk_div[1] -> 25 MHz
    4: 5_000,    # clk200_probe passthrough -> 100 MHz
    5: 5_000,    # clk400_probe passthrough -> 100 MHz
}
CLOCK_TASK = None


def saleae_bit(dut, idx: int) -> int:
    return (int(dut.saleae.value) >> idx) & 1


def led_bit(dut, idx: int) -> int:
    return (int(dut.led.value) >> idx) & 1


async def reset_and_capture_ready(dut):
    global CLOCK_TASK
    if CLOCK_TASK is None or CLOCK_TASK.done():
        CLOCK_TASK = start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 8)

    dut.rst_n.value = 1
    ready = await recv_rbx_line_matching(dut, "READY", attempts=24)
    assert ready == "RBX READY M=C F=0\r\n", f"unexpected boot banner: {ready!r}"


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

        await tick(dut.clk, bit_cycles // 2)
        if read_line() != 0:
            continue

        await tick(dut.clk, bit_cycles)

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


async def send_cmd_expect_line(dut, cmd: str, token: str, expected: str):
    task = cocotb.start_soon(recv_rbx_line_matching(dut, token))
    await send_uart_text(dut, cmd)
    line = await task
    assert line == expected, f"unexpected response for {cmd!r}: {line!r}"
    return line


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


async def wait_for_saleae_bit_toggle(dut, idx: int, timeout_ps: int):
    start = get_sim_time(units="ps")
    prev = saleae_bit(dut, idx)
    while True:
        now = get_sim_time(units="ps")
        if now - start >= timeout_ps:
            assert False, f"saleae[{idx}] did not toggle within {timeout_ps} ps"
        remaining = max(1, timeout_ps - (now - start))
        await with_timeout(Edge(dut.saleae), remaining, timeout_unit="ps")
        cur = saleae_bit(dut, idx)
        if cur != prev:
            return


async def measure_saleae0_half_period_ps(dut, settle_edges: int = 4, samples: int = 12) -> float:
    prev = saleae_bit(dut, 0)
    last_transition_ps = None
    intervals_ps: list[int] = []

    needed = settle_edges + samples
    timeout_ps = 20_000_000
    start_ps = get_sim_time(units="ps")
    while len(intervals_ps) < needed:
        now_ps = get_sim_time(units="ps")
        if now_ps - start_ps >= timeout_ps:
            assert False, "timed out while measuring saleae[0] period"
        remaining = max(1, timeout_ps - (now_ps - start_ps))
        await with_timeout(Edge(dut.saleae), remaining, timeout_unit="ps")
        cur = saleae_bit(dut, 0)
        if cur == prev:
            continue
        t_ps = get_sim_time(units="ps")
        if last_transition_ps is not None:
            intervals_ps.append(t_ps - last_transition_ps)
        last_transition_ps = t_ps
        prev = cur

    trimmed = intervals_ps[settle_edges:]
    return sum(trimmed) / len(trimmed)


async def wait_for_led_high(dut, idx: int, cycles: int) -> bool:
    for _ in range(cycles):
        await tick(dut.clk, 1)
        if led_bit(dut, idx):
            return True
    return False


async def assert_no_usb_tx_start_bit(dut, cycles: int):
    prev = int(dut.usb_tx.value)
    for _ in range(cycles):
        await tick(dut.clk, 1)
        cur = int(dut.usb_tx.value)
        assert not (prev == 1 and cur == 0), "unexpected extra USB TX start bit"
        prev = cur


async def wait_for_usb_tx_start_bit(dut, cycles: int) -> bool:
    prev = int(dut.usb_tx.value)
    for _ in range(cycles):
        await tick(dut.clk, 1)
        cur = int(dut.usb_tx.value)
        if prev == 1 and cur == 0:
            return True
        prev = cur
    return False


async def wait_for_saleae_start_bit(dut, idx: int, cycles: int) -> bool:
    prev = saleae_bit(dut, idx)
    for _ in range(cycles):
        await tick(dut.clk, 1)
        cur = saleae_bit(dut, idx)
        if prev == 1 and cur == 0:
            return True
        prev = cur
    return False


@cocotb.test()
async def boot_banner_and_command_parser_paths(dut):
    await reset_and_capture_ready(dut)

    await send_cmd_expect_line(dut, "!S", "STATUS", "RBX STATUS M=C F=0\r\n")
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
    await assert_saleae0_toggles(dut, cycles=96)

    await send_cmd_expect_line(
        dut,
        "!h",
        "HELP",
        "RBX HELP !H !S !C !E !F0-5 M:CLOCK E:ECHO\r\n",
    )
    await send_cmd_expect_line(dut, "!Q", "ERR CMD", "RBX ERR CMD\r\n")
    await send_cmd_expect_line(dut, "!F9", "ERR FREQ", "RBX ERR FREQ\r\n")
    await send_cmd_expect_line(dut, "!e", "OK", "RBX OK M=E F=0\r\n")
    await send_cmd_expect_line(dut, "!S", "STATUS", "RBX STATUS M=E F=0\r\n")
    await send_cmd_expect_line(dut, "!f2", "OK", "RBX OK M=E F=2\r\n")
    await send_cmd_expect_line(dut, "!S", "STATUS", "RBX STATUS M=E F=2\r\n")
    await send_cmd_expect_line(dut, "!C", "OK", "RBX OK M=C F=2\r\n")


@cocotb.test()
async def clock_tester_frequency_map_all_codes(dut):
    await reset_and_capture_ready(dut)

    for code, expected_half_ps in FREQ_HALF_PERIOD_PS.items():
        await send_cmd_expect_line(dut, f"!F{code}", "OK", f"RBX OK M=C F={code}\r\n")
        await assert_saleae_quiet(dut, first_idx=1, cycles=24)

        measured_half_ps = await measure_saleae0_half_period_ps(dut)
        tolerance_ps = max(expected_half_ps * 0.30, 250)
        diff_ps = abs(measured_half_ps - expected_half_ps)
        assert diff_ps <= tolerance_ps, (
            f"F{code} half-period mismatch: expected {expected_half_ps:.1f} ps, "
            f"measured {measured_half_ps:.1f} ps, tolerance {tolerance_ps:.1f} ps"
        )


@cocotb.test()
async def echo_mode_forwarding_and_drop_behavior(dut):
    await reset_and_capture_ready(dut)
    await send_cmd_expect_line(dut, "!E", "OK", "RBX OK M=E F=0\r\n")

    await wait_for_saleae_bit_toggle(dut, 0, timeout_ps=100_000)
    await wait_for_saleae_bit_toggle(dut, 1, timeout_ps=100_000)
    await wait_for_saleae_bit_toggle(dut, 2, timeout_ps=100_000)
    await wait_for_saleae_bit_toggle(dut, 3, timeout_ps=100_000)

    dut.usb_rx.value = 0
    await tick(dut.clk, 4)
    assert saleae_bit(dut, 4) == 0, "saleae[4] should mirror usb_rx low"
    dut.usb_rx.value = 1
    await tick(dut.clk, 4)
    assert saleae_bit(dut, 4) == 1, "saleae[4] should mirror usb_rx high"
    await tick(dut.clk, USB_BIT_CYCLES * 4)

    payload = 0x41
    accept_watch = cocotb.start_soon(wait_for_led_high(dut, 5, cycles=USB_BIT_CYCLES * 30))
    drop_watch = cocotb.start_soon(wait_for_led_high(dut, 6, cycles=USB_BIT_CYCLES * 30))
    usb_start_task = cocotb.start_soon(wait_for_usb_tx_start_bit(dut, cycles=USB_BIT_CYCLES * 80))
    tx6_start_task = cocotb.start_soon(wait_for_saleae_start_bit(dut, 6, cycles=USB_BIT_CYCLES * 80))
    tx7_start_task = cocotb.start_soon(wait_for_saleae_start_bit(dut, 7, cycles=USB_BIT_CYCLES * 80))

    await send_uart_byte(dut, payload)
    saw_accept = await accept_watch
    saw_drop = await drop_watch
    assert saw_accept, "accepted LED was never asserted for payload in echo mode"
    assert not saw_drop, "dropped LED asserted unexpectedly for accepted payload"
    saw_usb_start = await usb_start_task
    assert saw_usb_start, "usb_tx never emitted a frame start for echoed payload"
    saw_tx6_start = await tx6_start_task
    assert saw_tx6_start, "saleae[6] never emitted a UART frame start in echo mode"
    saw_tx7_start = await tx7_start_task
    assert saw_tx7_start, "saleae[7] never emitted a UART frame start in echo mode"
    for _ in range(128):
        await tick(dut.clk, 1)
        assert saleae_bit(dut, 5) == int(dut.usb_tx.value), "saleae[5] must mirror usb_tx"

    for _ in range(16):
        await tick(dut.clk, 1)
        assert led_bit(dut, 6) == 0, "dropped LED should be low before drop scenario"

    help_task = cocotb.start_soon(recv_rbx_line_matching(dut, "HELP"))
    await send_uart_text(dut, "!H")
    await tick(dut.clk, 16)
    drop_watch = cocotb.start_soon(wait_for_led_high(dut, 6, cycles=USB_BIT_CYCLES * 30))
    await send_uart_byte(dut, 0x55)
    saw_drop = await drop_watch
    assert saw_drop, "dropped LED was never asserted while payload was blocked by command TX"

    help_line = await help_task
    assert help_line == "RBX HELP !H !S !C !E !F0-5 M:CLOCK E:ECHO\r\n", f"unexpected help: {help_line!r}"
    await assert_no_usb_tx_start_bit(dut, cycles=USB_BIT_CYCLES * 12)

    await send_cmd_expect_line(dut, "!C", "OK", "RBX OK M=C F=0\r\n")
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
    ok_clock_2_task = cocotb.start_soon(recv_rbx_line_matching(dut, "OK"))
    await send_uart_text(dut, "!C")
    ok_clock_2 = await ok_clock_2_task
    assert ok_clock_2 == "RBX OK M=C F=0\r\n", f"unexpected !C response: {ok_clock_2!r}"
    await assert_saleae_quiet(dut, first_idx=1, cycles=24)
