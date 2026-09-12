import cocotb
from cocotb.triggers import Timer
from cocotb_helpers import start_clock, tick
from test_native_bist import run_memory


def client_request(d):
    d.client_cmd_valid.value = 1
    d.client_cmd_address.value = 1234
    d.client_cmd_write.value = 1
    d.client_wdata_valid.value = 1
    d.client_wdata.value = 0x123456789ABCDEF
    d.client_wdata_mask.value = 0xA55A
    d.client_rdata_ready.value = 1


async def check_exclusion(d):
    await tick(d.clk)
    while not int(d.passed.value):
        assert not int(d.client_cmd_ready.value)
        assert not int(d.client_wdata_ready.value)
        assert not int(d.client_rdata_valid.value)
        await tick(d.clk)


@cocotb.test()
async def client_blocked_until_qualification_then_all_channels_forward(d):
    start_clock(d.clk, 12)
    client_request(d)
    monitor = cocotb.start_soon(check_exclusion(d))
    writes, reads, _ = await run_memory(d, count=17)
    assert int(d.passed.value) and writes == reads == 51
    await monitor
    d.cmd_ready.value = 1
    d.wdata_ready.value = 1
    d.rdata_valid.value = 1
    d.rdata.value = 0xABCD
    await Timer(1, units="ns")
    assert int(d.cmd_valid.value) and int(d.cmd_address.value) == 1234
    assert int(d.cmd_write.value) and int(d.client_cmd_ready.value)
    assert int(d.wdata_valid.value) and int(d.wdata.value) == 0x123456789ABCDEF
    assert int(d.wdata_mask.value) == 0xA55A and int(d.client_wdata_ready.value)
    assert int(d.client_rdata_valid.value) and int(d.client_rdata.value) == 0xABCD
    assert int(d.rdata_ready.value)
    d.rst.value = 1
    await Timer(1, units="ns")
    assert not int(d.cmd_valid.value) and not int(d.wdata_valid.value)
    assert not int(d.client_cmd_ready.value) and not int(d.client_rdata_valid.value)


@cocotb.test()
async def failed_qualification_never_grants_client(d):
    start_clock(d.clk, 12)
    client_request(d)
    monitor = cocotb.start_soon(check_exclusion(d))
    await run_memory(d, count=5, corrupt=(3, 1, 127))
    assert int(d.failed.value) and int(d.progress.value) == 3
    d.cmd_ready.value = d.wdata_ready.value = d.rdata_valid.value = 1
    await tick(d.clk, 20)
    assert not int(d.passed.value) and not int(d.cmd_valid.value)
    assert not int(d.wdata_valid.value) and not int(d.client_cmd_ready.value)
    monitor.kill()
