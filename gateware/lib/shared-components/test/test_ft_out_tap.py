# top = tb_ft_out_tap

import random

import cocotb
from cocotb.triggers import Timer


def _value(signal, mask: int) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & mask


@cocotb.test()
async def typed_ft_out_tap_maps_every_field_without_transformation(dut):
    rng = random.Random(0xF760_2026)
    mappings = (
        ("ft_data_out", 0xFFFF),
        ("ft_be_out", 0x3),
        ("ft_rd", 0x1),
        ("ft_wr", 0x1),
        ("ft_oe", 0x1),
        ("ui_din_full", 0x1),
        ("ui_dout", 0xFFFF),
        ("ui_dout_be", 0x3),
        ("ui_dout_empty", 0x1),
    )

    for _ in range(256):
        expected: dict[str, int] = {}
        for name, mask in mappings:
            value = rng.randrange(mask + 1)
            expected[name] = value
            getattr(dut, f"in_{name}").value = value

        await Timer(1, units="ns")
        for name, mask in mappings:
            assert _value(getattr(dut, name), mask) == expected[name]
