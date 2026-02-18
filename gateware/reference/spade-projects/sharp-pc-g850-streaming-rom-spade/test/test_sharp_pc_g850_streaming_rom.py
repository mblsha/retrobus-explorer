# top = main

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


async def tick(clk, cycles=1):
    for _ in range(cycles):
        await RisingEdge(clk)
        await Timer(1, units="ps")


def expected_byte(addr, bnk, c0=0, c1=0, c2=0, c3=0, c4=0, c5=0):
    a = [(addr >> i) & 1 for i in range(8)]
    b0 = (bnk >> 0) & 1
    b1 = (bnk >> 1) & 1
    bits = [
        a[0] ^ b0,
        a[1] ^ b1,
        a[2] ^ c0,
        a[3] ^ c1,
        a[4] ^ c2,
        a[5] ^ c3,
        a[6] ^ b0 ^ c4,
        a[7] ^ b1 ^ c5,
    ]
    return sum((bit & 1) << i for i, bit in enumerate(bits))


@cocotb.test()
async def drives_rom_pattern_when_read_is_active(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.usb_rx.value = 0
    dut.ft_clk.value = 0
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    dut.ft_data.value = 0
    dut.ft_be.value = 0

    dut.z80_mreq.value = 1
    dut.z80_m1.value = 1
    dut.z80_ioreset.value = 0
    dut.z80_iorq.value = 1
    dut.z80_int1.value = 0
    dut.z80_wait.value = 1
    dut.z80_rd.value = 1
    dut.z80_wr.value = 1

    dut.addr.value = 0x005A
    dut.addr_bnk.value = 0x1
    dut.addr_ceram2.value = 0
    dut.addr_cerom2.value = 1

    await tick(dut.clk, 3)
    dut.rst_n.value = 1
    await tick(dut.clk, 2)

    assert dut.data.value.integer == 0

    dut.z80_mreq.value = 0
    dut.z80_rd.value = 0
    await tick(dut.clk, 1)

    exp = expected_byte(0x5A, 0x1)
    assert dut.data.value.integer == exp
