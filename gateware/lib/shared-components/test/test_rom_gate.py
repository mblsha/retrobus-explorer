# top = tb_rom_gate

import cocotb


def expected_byte(addr: int, bnk: int, stream_counter: int) -> int:
    a = [(addr >> i) & 1 for i in range(8)]
    b0 = (bnk >> 0) & 1
    b1 = (bnk >> 1) & 1
    c = [(stream_counter >> i) & 1 for i in range(8)]
    bits = [
        a[0] ^ b0,
        a[1] ^ b1,
        a[2] ^ c[0],
        a[3] ^ c[1],
        a[4] ^ c[2],
        a[5] ^ c[3],
        (a[6] ^ b0) ^ c[4],
        (a[7] ^ b1) ^ c[5],
    ]
    return sum((bit & 1) << i for i, bit in enumerate(bits))


@cocotb.test()
async def rom_and_gated_outputs_match_expected_pattern(dut):
    dut.addr.value = 0x005A
    dut.addr_bnk.value = 0x1
    dut.stream_counter.value = 0x12
    dut.enable.value = 0
    await cocotb.triggers.Timer(1, units="ns")

    exp0 = expected_byte(0x005A, 0x1, 0x12)
    assert dut.rom_byte.value.integer == exp0
    assert dut.gated_byte.value.integer == 0

    dut.enable.value = 1
    await cocotb.triggers.Timer(1, units="ns")
    assert dut.gated_byte.value.integer == exp0

    dut.addr.value = 0x00A5
    dut.addr_bnk.value = 0x2
    dut.stream_counter.value = 0x21
    await cocotb.triggers.Timer(1, units="ns")
    exp1 = expected_byte(0x00A5, 0x2, 0x21)
    assert dut.rom_byte.value.integer == exp1
    assert dut.gated_byte.value.integer == exp1
