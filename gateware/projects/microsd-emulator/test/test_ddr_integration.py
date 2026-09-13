import cocotb
from test_integration import exercise_image


from ddr_support import memory_model


@cocotb.test()
async def complete_image_loader_native_ddr_sd_path(d):
    d.writable.value = 0
    d.dat_in.value = 15
    d.diagnostic_status.value = 0
    d.initialized.value = 1
    d.ddr_cmd_ready.value = 0
    d.ddr_wdata_ready.value = 0
    d.ddr_rdata_valid.value = 0
    d.ddr_rdata.value = 0
    read_addresses = []
    task = cocotb.start_soon(memory_model(d, read_addresses=read_addresses))
    await exercise_image(d)
    for lba in (128, 16383):
        assert set(range(lba * 32, (lba + 1) * 32)) <= set(read_addresses)
    task.kill()
