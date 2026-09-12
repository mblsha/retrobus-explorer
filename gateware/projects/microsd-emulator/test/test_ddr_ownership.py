"""An accepted SD write must drain before a newly disarmed UART load."""
import cocotb
from cocotb_helpers import tick
from microsd_image import packet
from test_ddr_integration import memory_model
from test_integration import exercise_image, upload
from test_sd_write import send_packet


@cocotb.test()
async def stalled_sd_commit_precedes_disarmed_loader(d):
    d.diagnostic_status.value = 0
    d.initialized.value = 1
    d.ddr_cmd_ready.value = d.ddr_wdata_ready.value = d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    memory = {}
    allow = [True]
    task = cocotb.start_soon(memory_model(d, memory, allow=allow))
    h, _ = await exercise_image(d, writable=True, leave_armed=True)
    await h.command(24, 4096 * 512)
    allow[0] = False
    before = dict(memory)
    expected = await send_packet(h, True, 91, wait_complete=False)
    await upload(d, packet(3, 0, 129))
    assert not int(d.armed_status.value) and not int(d.dat_oe.value)
    replacement = bytes((i * 19 + 3) & 255 for i in range(512))
    loading = cocotb.start_soon(upload(d, packet(1, 0, 130, replacement)))
    await tick(d.clk, 700)
    assert not loading.done(), "loader bypassed the accepted SD commit"
    assert memory == before, "DDR mutated while both channels were stalled"
    allow[0] = True
    await loading
    actual = b''.join(memory[4096 * 32 + word].to_bytes(16, 'little') for word in range(32))
    assert actual == expected
    actual = b''.join(memory[word].to_bytes(16, 'little') for word in range(32))
    assert actual == replacement
    assert not int(d.armed_status.value)
    task.kill()
