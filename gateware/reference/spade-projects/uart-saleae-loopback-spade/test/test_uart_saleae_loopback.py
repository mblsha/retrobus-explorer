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


async def recv_uart_byte_from_line(dut, read_line, bit_cycles: int, timeout_cycles: int):
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
    assert stop == 1, f"invalid stop bit: {stop}"
    return value


@cocotb.test()
async def usb_echo_and_fast_saleae_uart_outputs(dut):
    start_clock(dut.clk)

    dut.rst_n.value = 0
    dut.usb_rx.value = 1
    await tick(dut.clk, 8)

    dut.rst_n.value = 1
    await tick(dut.clk, 16)

    payload = [0x41, 0x5A, 0x30]

    for byte in payload:
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

        await send_uart_byte(dut, byte)
        echoed = await echo_task
        assert echoed == byte, f"usb echo mismatch: expected 0x{byte:02x}, got 0x{echoed:02x}"

        for task_idx, task in enumerate(fast_tasks):
            idx = FAST_UART_CHANNELS[task_idx][0]
            got = await task
            assert got == byte, (
                f"saleae[{idx}] UART mismatch at bit_cycles={FAST_BIT_CYCLES[idx]}: "
                f"expected 0x{byte:02x}, got 0x{got:02x}"
            )
