import cocotb
from cocotb.triggers import Timer
from cocotb_helpers import start_clock, tick
from microsd_image import packet
from test_emulator_uart import receive
from test_ddr_integration import memory_model


@cocotb.test()
async def uart_upload_waits_for_ddr_and_preserves_all_byte_masks(d):
    period_ns = (
        5
        if d._name == "ddr_uart_200"
        else (
            10
            if d._name == "ddr_uart_100"
            else (12.5 if d._name == "ddr_uart_80" else 12)
        )
    )
    start_clock(d.clk, period_ns=period_ns)
    d.rst.value = 1
    d.writable.value = 0
    d.dat_in.value = 15
    d.diagnostic_status.value = 0x6543217
    d.initialized.value = 0
    d.usb_rx.value = 1
    d.sd_clk.value = 1
    d.cmd_in.value = 1
    d.ddr_cmd_ready.value = 0
    d.ddr_wdata_ready.value = 0
    d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    await tick(d.clk, 10)
    d.rst.value = 0
    await tick(d.clk, 10)
    for selector in (0, 11, 127):
        status_task = cocotb.start_soon(receive(d))
        for byte in packet(4, selector, 999):
            for bit in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
                d.usb_rx.value = bit
                await Timer(1000, units="ns")
        assert await status_task == (4, 0, 0x6543217 << 5)
        assert int(d.status_selector.value) == selector
    memory = {}
    model = cocotb.start_soon(memory_model(d, memory))
    response = cocotb.start_soon(receive(d))
    expected = bytes((i * 7 + (i >> 8)) & 255 for i in range(512))
    for byte in packet(1, 0, 713, expected):
        for bit in [0] + [(byte >> i) & 1 for i in range(8)] + [1]:
            d.usb_rx.value = bit
            await Timer(1000, units="ns")
    await tick(d.clk, 100)
    assert not memory
    assert not int(d.ddr_cmd_valid.value)
    d.initialized.value = 1
    assert await response == (1, 0, 713)
    actual = b"".join(memory[i].to_bytes(16, "little") for i in range(32))
    assert actual == expected
    assert not int(d.armed_status.value)
    assert not int(d.cmd_oe.value) and not int(d.dat_oe.value)
    model.kill()
