import cocotb
import os
from cocotb_helpers import start_clock, tick
from microsd_image import packet, decode_ack
from sd_support import Host


async def upload(d, raw):
    for b in raw:
        d.rx_byte.value = b
        d.rx_valid.value = 1
        await tick(d.clk)
    d.rx_valid.value = 0
    ack = bytearray()
    for _ in range(6000):
        d.tx_ready.value = 1
        if int(d.tx_valid.value):
            ack.append(int(d.tx_byte.value))
        await tick(d.clk)
        if len(ack) == 16:
            break
    d.tx_ready.value = 0
    assert decode_ack(bytes(ack))[1] == 0


async def exercise_image(d, writable=False, leave_armed=False):
    start_clock(d.clk, period_ns=float(os.environ.get("MICROSD_SYS_PERIOD_NS", "12.5")))
    if hasattr(d, "fast_mode"):
        d.fast_mode.value = int(os.environ.get("MICROSD_FAST_MODE", "0"))
    if hasattr(d, "writable"):
        d.writable.value = int(writable)
        d.dat_in.value = 15
    d.rst.value = 1
    if hasattr(d, "memory_rst"):
        d.memory_rst.value = 1
    d.rx_valid.value = 0
    d.rx_byte.value = 0
    d.tx_ready.value = 0
    d.sd_clk.value = 1
    d.cmd_in.value = 1
    await tick(d.clk, 40 if hasattr(d, "memory_rst") else 10)
    if hasattr(d, "memory_rst"):
        d.memory_rst.value = 0
    d.rst.value = 0
    await tick(d.clk, 5)
    assert (
        not int(d.armed_status.value)
        and not int(d.cmd_oe.value)
        and not int(d.dat_oe.value)
    )
    image = bytes((i * 17 + (i >> 9)) & 255 for i in range(65536))
    for sector in range(128):
        await upload(
            d, packet(1, sector, sector, image[sector * 512 : (sector + 1) * 512])
        )
    await upload(d, packet(2, 0, 128))
    assert int(d.armed_status.value)
    h = Host(d)
    await h.init(writable=writable)
    await h.command(55, 0x10000)
    await h.command(6, 2)
    for lba in (0, 127, 128, 16383):
        await h.command(17, lba * 512)
        assert await h.data(wide=True) == (
            image[lba * 512 : (lba + 1) * 512] if lba < 128 else bytes(512)
        )
    if not leave_armed:
        await upload(d, packet(3, 0, 129))
        assert not int(d.armed_status.value) and not int(d.dat_oe.value)
    return h, image


@cocotb.test()
async def complete_image_loader_bram_sd_path(d):
    await exercise_image(d)
