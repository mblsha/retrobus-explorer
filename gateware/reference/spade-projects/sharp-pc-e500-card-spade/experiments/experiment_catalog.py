from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

FT_STREAM_ARM_ADDR = 0x1FFF4


@dataclass(frozen=True)
class CatalogExperiment:
    name: str
    default_count: int
    build_asm: Callable[..., str]
    timing: int
    control_timing: int
    timeout_s: float
    start_tag: int
    stop_tag: int
    flags: int
    args: list[int]
    fill_experiment_region: bool
    supports_ft_capture_flag: bool
    include_ft_capture_in_parse: bool
    ft_max_retained_words: int | None = None
    supports_arm_ft_stream: bool = False


def _append_ft_stream_arm(lines: list[str], *, enabled: bool) -> None:
    if not enabled:
        return
    lines.extend(
        [
            "    MV A, 0x01",
            f"    MV [0x{FT_STREAM_ARM_ADDR:05X}], A",
        ]
    )


def _append_ft_stream_disarm(lines: list[str], *, enabled: bool) -> None:
    if not enabled:
        return
    lines.extend(
        [
            "    MV A, 0x00",
            f"    MV [0x{FT_STREAM_ARM_ADDR:05X}], A",
        ]
    )


def build_asm_and_abs_imm_ce1_rmw_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
    ]
    for _ in range(count):
        lines.append("    AND [0x040000], 0x0F")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_and_abs_imm_ce6_rmw_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    AND [0x107E6], 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_and_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    AND (0x20), 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_and_ustack_reserved_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    MV (0x20), 0xA5",
        "    MV [U], (0x20)",
    ]
    for _ in range(count):
        lines.append("    AND [0x3F692], 0x0F")
    lines.extend(
        [
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_call_ret_chain(count: int, *, arm_ft_stream: bool = False) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    _append_ft_stream_arm(lines, enabled=arm_ft_stream)
    for idx in range(count):
        lines.append(f"    CALL sub_{idx:03d}")
    _append_ft_stream_disarm(lines, enabled=arm_ft_stream)
    lines.append("    RETF")
    lines.append("")
    for idx in range(count):
        lines.append(f"sub_{idx:03d}:")
        lines.append("    RET")
    lines.append("")
    return "\n".join(lines)

def build_asm_callf_retf_chain(count: int, *, arm_ft_stream: bool = False) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    _append_ft_stream_arm(lines, enabled=arm_ft_stream)
    for idx in range(count):
        lines.append(f"    CALLF sub_{idx:03d}")
    _append_ft_stream_disarm(lines, enabled=arm_ft_stream)
    lines.append("    RETF")
    lines.append("")
    for idx in range(count):
        lines.append(f"sub_{idx:03d}:")
        lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_imr_roundtrip_via_a_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    PUSHU IMR")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jp_chain_skip_nop(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for idx in range(count):
        lines.append(f"    JP target_{idx:03d}")
        lines.append("    NOP")
        lines.append(f"target_{idx:03d}:")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jpnz_fallthrough_nop(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0",
        "    CMP A, 0",
    ]
    for idx in range(count):
        lines.append(f"    JPNZ target_{idx:03d}")
        lines.append("    NOP")
        lines.append(f"target_{idx:03d}:")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jpz_taken_skip_nop(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0",
        "    CMP A, 0",
    ]
    for idx in range(count):
        lines.append(f"    JPZ target_{idx:03d}")
        lines.append("    NOP")
        lines.append(f"target_{idx:03d}:")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jr_chain_skip_nop(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    JR +1")
        lines.append("    NOP")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jrnz_fallthrough_nop(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0",
        "    CMP A, 0",
    ]
    for _ in range(count):
        lines.append("    JRNZ +1")
        lines.append("    NOP")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_jrz_taken_skip_nop(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0",
        "    CMP A, 0",
    ]
    for _ in range(count):
        lines.append("    JRZ +1")
        lines.append("    NOP")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_abs_read_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    MV A, [0x107E6]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_ce1_seeded_abs_read_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
    ]
    for _ in range(count):
        lines.append("    MV A, [0x040000]")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mv_a_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xFF",
    ]
    for _ in range(count):
        lines.append("    MV A, (IMR)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_isr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV A, (ISR)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_kol_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV A, (KOL)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_scr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV A, (SCR)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_ssr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV A, (SSR)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_a_usr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV A, (USR)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_abs_a_ce1_write_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [0x040000], A")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mv_abs_a_ce6_write_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [0x107E6], A")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_abs_a_ctrl_write_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [0x1FFF5], A")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_abs_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [0x107E6], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_ememreg_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [X], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_imem_abs_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (0x20), [0x107E6]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_imem_ememreg_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
    ]
    for _ in range(count):
        lines.append("    MV (0x20), [X]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_imem_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (0x28), 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV (0x2C), (0x28)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (0x28), 0xA5")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_imr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (IMR), 0xFF")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_isr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (ISR), 0x00")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_scr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (SCR), 0x00")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_ssr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MV (SSR), 0x04")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mv_ustack_reserved_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    MV [U], (0x20)")
    lines.extend(
        [
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mvp_abs_ce1_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVP (0x20), 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    MVP [0x040000], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_abs_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVP (0x20), 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    MVP [0x107E6], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_ememreg_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
        "    MVP (0x20), 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    MVP [X], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_imem_abs_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MVP (0x20), [0x107E6]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_imem_ce1_seeded_abs_read_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
        "    MV A, 0x5A",
        "    MV [0x040001], A",
        "    MV A, 0x3C",
        "    MV [0x040002], A",
    ]
    for _ in range(count):
        lines.append("    MVP (0x20), [0x040000]")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mvp_imem_ememreg_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
    ]
    for _ in range(count):
        lines.append("    MVP (0x20), [X]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_imem_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVP (0x28), 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    MVP (0x2C), (0x28)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MVP (0x24), 0x3C5AA5")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_userstack_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        f"    MV U, 0x{USER_STACK_ADDR:05X}",
        "    MVP (0x20), 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    MVP [U], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvp_ustack_reserved_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVP (0x20), 0x3C5AA5",
        "    PUSHU A",
        "    PUSHU A",
        "    PUSHU A",
    ]
    for _ in range(count):
        lines.append("    MVP [U], (0x20)")
    lines.extend(
        [
            "    POPU A",
            "    POPU A",
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mvw_abs_ce1_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVW (0x20), 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    MVW [0x040000], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_abs_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVW (0x20), 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    MVW [0x107E6], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_ememreg_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
        "    MVW (0x20), 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    MVW [X], (0x20)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_imem_abs_read_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    MVW (0x20), [0x107E6]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_imem_ce1_seeded_abs_read_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
        "    MV A, 0x5A",
        "    MV [0x040001], A",
    ]
    for _ in range(count):
        lines.append("    MVW (0x20), [0x040000]")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_mvw_imem_ememreg_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x107E6",
    ]
    for _ in range(count):
        lines.append("    MVW (0x20), [X]")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_imem_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MVW (0x28), 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    MVW (0x2C), (0x28)")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    MVW (0x20), 0x5AA5")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_mvw_ustack_reserved_imem_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    PUSHU A",
        "    MVW (0x20), 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    MVW [U], (0x20)")
    lines.extend(
        [
            "    POPU A",
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_nop_block(count: int) -> str:
    body = "\n".join("    NOP" for _ in range(count))
    return f""".ORG 0x10100

start:
{body}
    RETF
"""

def build_asm_or_abs_imm_ce1_rmw_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
    ]
    for _ in range(count):
        lines.append("    OR [0x040000], 0x0F")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_or_abs_imm_ce6_rmw_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    OR [0x107E6], 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_or_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    OR (0x20), 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_or_ustack_reserved_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    MV (0x20), 0xA5",
        "    MV [U], (0x20)",
    ]
    for _ in range(count):
        lines.append("    OR [0x3F692], 0x0F")
    lines.extend(
        [
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_pushs_pops_f_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHS F")
        lines.append("    POPS F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_01_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x01",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_21_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x21",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_81_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_a0_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA0",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_a1_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA1",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_a4_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA4",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_nop_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    NOP")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_01_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x01",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_20_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x20",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_21_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x21",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_7f_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x7F",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_80_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x80",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_81_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_a1_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA1",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_a4_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA4",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_ff_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xFF",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_ff_delta_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xFF",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_onebit_delta_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xA4",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_popu_imr_same_mask_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xA5",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_21_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x21",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_21_pre_nop_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x21",
        "    NOP",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_21_pre_sc_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x21",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_81_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_81_nop_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
        lines.append("    NOP")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_81_pre_nop_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
        "    NOP",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_81_pre_sc_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a0_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA0",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a0_pre_nop_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA0",
        "    NOP",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a0_pre_sc_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA0",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a1_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA1",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a1_pre_nop_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA1",
        "    NOP",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_a1_pre_sc_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA1",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_roundtrip_then_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_sc_popu_imr_81_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x81",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    SC")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_a_sc_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    SC")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_f_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU F")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_f_to_a_then_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU F")
        lines.append("    POPU A")
        lines.append("    PUSHU A")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xFF",
    ]
    for _ in range(count):
        lines.append("    PUSHU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_a_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU A")
        lines.append("    POPU A")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_ba_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV BA, 0x5AA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU BA")
        lines.append("    POPU BA")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_f_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    SC",
    ]
    for _ in range(count):
        lines.append("    PUSHU F")
        lines.append("    POPU F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_imr_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (IMR), 0xFF",
    ]
    for _ in range(count):
        lines.append("    PUSHU IMR")
        lines.append("    POPU IMR")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_x_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV X, 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU X")
        lines.append("    POPU X")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_pushu_popu_y_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV Y, 0x3C5AA5",
    ]
    for _ in range(count):
        lines.append("    PUSHU Y")
        lines.append("    POPU Y")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_test_abs_imm_ce1_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
    ]
    for _ in range(count):
        lines.append("    TEST [0x040000], 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_test_abs_imm_ce6_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    TEST [0x107E6], 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_test_imr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    TEST (IMR), 0x01")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_test_isr_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
    ]
    for _ in range(count):
        lines.append("    TEST (ISR), 0x01")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_test_ustack_reserved_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    MV (0x20), 0xA5",
        "    MV [U], (0x20)",
    ]
    for _ in range(count):
        lines.append("    TEST [0x3F692], 0x0F")
    lines.extend(
        [
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_xor_abs_imm_ce1_rmw_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0xA5",
        "    MV [0x040000], A",
    ]
    for _ in range(count):
        lines.append("    XOR [0x040000], 0x0F")
    lines.extend(
        [
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

def build_asm_xor_abs_imm_ce6_rmw_chain(count: int) -> str:
    lines = [".ORG 0x10100", "", "start:"]
    for _ in range(count):
        lines.append("    XOR [0x107E6], 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_xor_imem_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV (0x20), 0xA5",
    ]
    for _ in range(count):
        lines.append("    XOR (0x20), 0x0F")
    lines.append("    RETF")
    lines.append("")
    return "\n".join(lines)

def build_asm_xor_ustack_reserved_imm_chain(count: int) -> str:
    lines = [
        ".ORG 0x10100",
        "",
        "start:",
        "    MV A, 0x00",
        "    PUSHU A",
        "    MV (0x20), 0xA5",
        "    MV [U], (0x20)",
    ]
    for _ in range(count):
        lines.append("    XOR [0x3F692], 0x0F")
    lines.extend(
        [
            "    POPU A",
            "    RETF",
            "",
        ]
    )
    return "\n".join(lines)

EXPERIMENTS: dict[str, CatalogExperiment] = {
    'and_abs_imm_ce1_rmw_chain': CatalogExperiment(
        name='and_abs_imm_ce1_rmw_chain',
        default_count=64,
        build_asm=build_asm_and_abs_imm_ce1_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=75,
        stop_tag=76,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'and_abs_imm_ce6_rmw_chain': CatalogExperiment(
        name='and_abs_imm_ce6_rmw_chain',
        default_count=64,
        build_asm=build_asm_and_abs_imm_ce6_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=75,
        stop_tag=76,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'and_imem_imm_chain': CatalogExperiment(
        name='and_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_and_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=75,
        stop_tag=76,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'and_ustack_reserved_imm_chain': CatalogExperiment(
        name='and_ustack_reserved_imm_chain',
        default_count=64,
        build_asm=build_asm_and_ustack_reserved_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=91,
        stop_tag=92,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'call_ret_chain': CatalogExperiment(
        name='call_ret_chain',
        default_count=64,
        build_asm=build_asm_call_ret_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=67,
        stop_tag=68,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        supports_arm_ft_stream=True,
    ),
    'callf_retf_chain': CatalogExperiment(
        name='callf_retf_chain',
        default_count=64,
        build_asm=build_asm_callf_retf_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=65,
        stop_tag=66,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        supports_arm_ft_stream=True,
    ),
    'imr_roundtrip_via_a_chain': CatalogExperiment(
        name='imr_roundtrip_via_a_chain',
        default_count=64,
        build_asm=build_asm_imr_roundtrip_via_a_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'jp_chain_skip_nop': CatalogExperiment(
        name='jp_chain_skip_nop',
        default_count=64,
        build_asm=build_asm_jp_chain_skip_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=51,
        stop_tag=52,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'jpnz_fallthrough_nop': CatalogExperiment(
        name='jpnz_fallthrough_nop',
        default_count=64,
        build_asm=build_asm_jpnz_fallthrough_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=53,
        stop_tag=54,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'jpz_taken_skip_nop': CatalogExperiment(
        name='jpz_taken_skip_nop',
        default_count=64,
        build_asm=build_asm_jpz_taken_skip_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=55,
        stop_tag=56,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'jr_chain_skip_nop': CatalogExperiment(
        name='jr_chain_skip_nop',
        default_count=64,
        build_asm=build_asm_jr_chain_skip_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=57,
        stop_tag=58,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'jrnz_fallthrough_nop': CatalogExperiment(
        name='jrnz_fallthrough_nop',
        default_count=64,
        build_asm=build_asm_jrnz_fallthrough_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=61,
        stop_tag=62,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'jrz_taken_skip_nop': CatalogExperiment(
        name='jrz_taken_skip_nop',
        default_count=64,
        build_asm=build_asm_jrz_taken_skip_nop,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=59,
        stop_tag=60,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'mv_a_abs_read_chain': CatalogExperiment(
        name='mv_a_abs_read_chain',
        default_count=64,
        build_asm=build_asm_mv_a_abs_read_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=69,
        stop_tag=70,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_a_ce1_seeded_abs_read_chain': CatalogExperiment(
        name='mv_a_ce1_seeded_abs_read_chain',
        default_count=64,
        build_asm=build_asm_mv_a_ce1_seeded_abs_read_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=69,
        stop_tag=70,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_a_imr_chain': CatalogExperiment(
        name='mv_a_imr_chain',
        default_count=64,
        build_asm=build_asm_mv_a_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_a_isr_chain': CatalogExperiment(
        name='mv_a_isr_chain',
        default_count=64,
        build_asm=build_asm_mv_a_isr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_a_kol_chain': CatalogExperiment(
        name='mv_a_kol_chain',
        default_count=64,
        build_asm=build_asm_mv_a_kol_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_a_scr_chain': CatalogExperiment(
        name='mv_a_scr_chain',
        default_count=64,
        build_asm=build_asm_mv_a_scr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_a_ssr_chain': CatalogExperiment(
        name='mv_a_ssr_chain',
        default_count=64,
        build_asm=build_asm_mv_a_ssr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_a_usr_chain': CatalogExperiment(
        name='mv_a_usr_chain',
        default_count=64,
        build_asm=build_asm_mv_a_usr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_abs_a_ce1_write_chain': CatalogExperiment(
        name='mv_abs_a_ce1_write_chain',
        default_count=64,
        build_asm=build_asm_mv_abs_a_ce1_write_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=73,
        stop_tag=74,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_abs_a_ce6_write_chain': CatalogExperiment(
        name='mv_abs_a_ce6_write_chain',
        default_count=64,
        build_asm=build_asm_mv_abs_a_ce6_write_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=73,
        stop_tag=74,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_abs_a_ctrl_write_chain': CatalogExperiment(
        name='mv_abs_a_ctrl_write_chain',
        default_count=64,
        build_asm=build_asm_mv_abs_a_ctrl_write_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=71,
        stop_tag=72,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_abs_imem_chain': CatalogExperiment(
        name='mv_abs_imem_chain',
        default_count=64,
        build_asm=build_asm_mv_abs_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_ememreg_imem_chain': CatalogExperiment(
        name='mv_ememreg_imem_chain',
        default_count=64,
        build_asm=build_asm_mv_ememreg_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_imem_abs_chain': CatalogExperiment(
        name='mv_imem_abs_chain',
        default_count=64,
        build_asm=build_asm_mv_imem_abs_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_imem_ememreg_chain': CatalogExperiment(
        name='mv_imem_ememreg_chain',
        default_count=64,
        build_asm=build_asm_mv_imem_ememreg_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_imem_imem_chain': CatalogExperiment(
        name='mv_imem_imem_chain',
        default_count=64,
        build_asm=build_asm_mv_imem_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_imem_imm_chain': CatalogExperiment(
        name='mv_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_mv_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mv_imr_imm_chain': CatalogExperiment(
        name='mv_imr_imm_chain',
        default_count=64,
        build_asm=build_asm_mv_imr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_isr_imm_chain': CatalogExperiment(
        name='mv_isr_imm_chain',
        default_count=64,
        build_asm=build_asm_mv_isr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_scr_imm_chain': CatalogExperiment(
        name='mv_scr_imm_chain',
        default_count=64,
        build_asm=build_asm_mv_scr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_ssr_imm_chain': CatalogExperiment(
        name='mv_ssr_imm_chain',
        default_count=64,
        build_asm=build_asm_mv_ssr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'mv_ustack_reserved_imem_chain': CatalogExperiment(
        name='mv_ustack_reserved_imem_chain',
        default_count=64,
        build_asm=build_asm_mv_ustack_reserved_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=87,
        stop_tag=88,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_abs_ce1_imem_chain': CatalogExperiment(
        name='mvp_abs_ce1_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_abs_ce1_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=85,
        stop_tag=86,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_abs_imem_chain': CatalogExperiment(
        name='mvp_abs_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_abs_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_ememreg_imem_chain': CatalogExperiment(
        name='mvp_ememreg_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_ememreg_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_imem_abs_chain': CatalogExperiment(
        name='mvp_imem_abs_chain',
        default_count=64,
        build_asm=build_asm_mvp_imem_abs_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[165, 90, 60],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_imem_ce1_seeded_abs_read_chain': CatalogExperiment(
        name='mvp_imem_ce1_seeded_abs_read_chain',
        default_count=64,
        build_asm=build_asm_mvp_imem_ce1_seeded_abs_read_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=83,
        stop_tag=84,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_imem_ememreg_chain': CatalogExperiment(
        name='mvp_imem_ememreg_chain',
        default_count=64,
        build_asm=build_asm_mvp_imem_ememreg_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[165, 90, 60],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_imem_imem_chain': CatalogExperiment(
        name='mvp_imem_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_imem_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_imem_imm_chain': CatalogExperiment(
        name='mvp_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_mvp_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_userstack_imem_chain': CatalogExperiment(
        name='mvp_userstack_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_userstack_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvp_ustack_reserved_imem_chain': CatalogExperiment(
        name='mvp_ustack_reserved_imem_chain',
        default_count=64,
        build_asm=build_asm_mvp_ustack_reserved_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_abs_ce1_imem_chain': CatalogExperiment(
        name='mvw_abs_ce1_imem_chain',
        default_count=64,
        build_asm=build_asm_mvw_abs_ce1_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_abs_imem_chain': CatalogExperiment(
        name='mvw_abs_imem_chain',
        default_count=64,
        build_asm=build_asm_mvw_abs_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_ememreg_imem_chain': CatalogExperiment(
        name='mvw_ememreg_imem_chain',
        default_count=64,
        build_asm=build_asm_mvw_ememreg_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=79,
        stop_tag=80,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_imem_abs_read_chain': CatalogExperiment(
        name='mvw_imem_abs_read_chain',
        default_count=64,
        build_asm=build_asm_mvw_imem_abs_read_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=77,
        stop_tag=78,
        flags=0,
        args=[165, 90],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_imem_ce1_seeded_abs_read_chain': CatalogExperiment(
        name='mvw_imem_ce1_seeded_abs_read_chain',
        default_count=64,
        build_asm=build_asm_mvw_imem_ce1_seeded_abs_read_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=77,
        stop_tag=78,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_imem_ememreg_chain': CatalogExperiment(
        name='mvw_imem_ememreg_chain',
        default_count=64,
        build_asm=build_asm_mvw_imem_ememreg_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[165, 90],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_imem_imem_chain': CatalogExperiment(
        name='mvw_imem_imem_chain',
        default_count=64,
        build_asm=build_asm_mvw_imem_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_imem_imm_chain': CatalogExperiment(
        name='mvw_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_mvw_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'mvw_ustack_reserved_imem_chain': CatalogExperiment(
        name='mvw_ustack_reserved_imem_chain',
        default_count=64,
        build_asm=build_asm_mvw_ustack_reserved_imem_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=89,
        stop_tag=90,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'nop_block': CatalogExperiment(
        name='nop_block',
        default_count=64,
        build_asm=build_asm_nop_block,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=49,
        stop_tag=50,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=False,
        include_ft_capture_in_parse=False,
    ),
    'or_abs_imm_ce1_rmw_chain': CatalogExperiment(
        name='or_abs_imm_ce1_rmw_chain',
        default_count=64,
        build_asm=build_asm_or_abs_imm_ce1_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=101,
        stop_tag=102,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'or_abs_imm_ce6_rmw_chain': CatalogExperiment(
        name='or_abs_imm_ce6_rmw_chain',
        default_count=64,
        build_asm=build_asm_or_abs_imm_ce6_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=97,
        stop_tag=98,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'or_imem_imm_chain': CatalogExperiment(
        name='or_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_or_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=141,
        stop_tag=142,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'or_ustack_reserved_imm_chain': CatalogExperiment(
        name='or_ustack_reserved_imm_chain',
        default_count=64,
        build_asm=build_asm_or_ustack_reserved_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=93,
        stop_tag=94,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushs_pops_f_chain': CatalogExperiment(
        name='pushs_pops_f_chain',
        default_count=64,
        build_asm=build_asm_pushs_pops_f_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushu_a_nop_popu_imr_01_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_01_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_01_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_21_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_21_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_21_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_81_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_81_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_81_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_a0_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_a0_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_a0_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_a1_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_a1_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_a1_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_a4_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_a4_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_a4_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_nop_popu_imr_chain': CatalogExperiment(
        name='pushu_a_nop_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_nop_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_01_chain': CatalogExperiment(
        name='pushu_a_popu_imr_01_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_01_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_20_chain': CatalogExperiment(
        name='pushu_a_popu_imr_20_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_20_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_21_chain': CatalogExperiment(
        name='pushu_a_popu_imr_21_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_21_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_7f_chain': CatalogExperiment(
        name='pushu_a_popu_imr_7f_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_7f_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_80_chain': CatalogExperiment(
        name='pushu_a_popu_imr_80_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_80_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_81_chain': CatalogExperiment(
        name='pushu_a_popu_imr_81_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_81_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_a1_chain': CatalogExperiment(
        name='pushu_a_popu_imr_a1_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_a1_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_a4_chain': CatalogExperiment(
        name='pushu_a_popu_imr_a4_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_a4_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_chain': CatalogExperiment(
        name='pushu_a_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_ff_chain': CatalogExperiment(
        name='pushu_a_popu_imr_ff_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_ff_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_ff_delta_chain': CatalogExperiment(
        name='pushu_a_popu_imr_ff_delta_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_ff_delta_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_onebit_delta_chain': CatalogExperiment(
        name='pushu_a_popu_imr_onebit_delta_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_onebit_delta_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_popu_imr_same_mask_chain': CatalogExperiment(
        name='pushu_a_popu_imr_same_mask_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_popu_imr_same_mask_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_21_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_21_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_21_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_21_pre_nop_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_21_pre_nop_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_21_pre_nop_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_21_pre_sc_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_21_pre_sc_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_21_pre_sc_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_81_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_81_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_81_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_81_nop_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_81_nop_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_81_nop_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_81_pre_nop_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_81_pre_nop_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_81_pre_nop_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_81_pre_sc_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_81_pre_sc_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_81_pre_sc_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a0_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a0_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a0_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a0_pre_nop_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a0_pre_nop_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a0_pre_nop_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a0_pre_sc_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a0_pre_sc_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a0_pre_sc_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a1_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a1_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a1_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a1_pre_nop_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a1_pre_nop_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a1_pre_nop_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_a1_pre_sc_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_a1_pre_sc_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_a1_pre_sc_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_roundtrip_then_popu_imr_chain': CatalogExperiment(
        name='pushu_a_roundtrip_then_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_roundtrip_then_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_sc_popu_imr_81_chain': CatalogExperiment(
        name='pushu_a_sc_popu_imr_81_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_sc_popu_imr_81_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_a_sc_popu_imr_chain': CatalogExperiment(
        name='pushu_a_sc_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_a_sc_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_f_popu_imr_chain': CatalogExperiment(
        name='pushu_f_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_f_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_f_to_a_then_popu_imr_chain': CatalogExperiment(
        name='pushu_f_to_a_then_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_f_to_a_then_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_imr_chain': CatalogExperiment(
        name='pushu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_popu_a_chain': CatalogExperiment(
        name='pushu_popu_a_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_a_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushu_popu_ba_chain': CatalogExperiment(
        name='pushu_popu_ba_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_ba_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushu_popu_f_chain': CatalogExperiment(
        name='pushu_popu_f_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_f_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushu_popu_imr_chain': CatalogExperiment(
        name='pushu_popu_imr_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_imr_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'pushu_popu_x_chain': CatalogExperiment(
        name='pushu_popu_x_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_x_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'pushu_popu_y_chain': CatalogExperiment(
        name='pushu_popu_y_chain',
        default_count=64,
        build_asm=build_asm_pushu_popu_y_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'test_abs_imm_ce1_chain': CatalogExperiment(
        name='test_abs_imm_ce1_chain',
        default_count=64,
        build_asm=build_asm_test_abs_imm_ce1_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=154,
        stop_tag=155,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'test_abs_imm_ce6_chain': CatalogExperiment(
        name='test_abs_imm_ce6_chain',
        default_count=64,
        build_asm=build_asm_test_abs_imm_ce6_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=152,
        stop_tag=153,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'test_imr_imm_chain': CatalogExperiment(
        name='test_imr_imm_chain',
        default_count=64,
        build_asm=build_asm_test_imr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'test_isr_imm_chain': CatalogExperiment(
        name='test_isr_imm_chain',
        default_count=64,
        build_asm=build_asm_test_isr_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=81,
        stop_tag=82,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
        ft_max_retained_words=32768,
    ),
    'test_ustack_reserved_imm_chain': CatalogExperiment(
        name='test_ustack_reserved_imm_chain',
        default_count=64,
        build_asm=build_asm_test_ustack_reserved_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=156,
        stop_tag=157,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'xor_abs_imm_ce1_rmw_chain': CatalogExperiment(
        name='xor_abs_imm_ce1_rmw_chain',
        default_count=64,
        build_asm=build_asm_xor_abs_imm_ce1_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=103,
        stop_tag=104,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'xor_abs_imm_ce6_rmw_chain': CatalogExperiment(
        name='xor_abs_imm_ce6_rmw_chain',
        default_count=64,
        build_asm=build_asm_xor_abs_imm_ce6_rmw_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=99,
        stop_tag=100,
        flags=0,
        args=[165],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'xor_imem_imm_chain': CatalogExperiment(
        name='xor_imem_imm_chain',
        default_count=64,
        build_asm=build_asm_xor_imem_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=148,
        stop_tag=149,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
    'xor_ustack_reserved_imm_chain': CatalogExperiment(
        name='xor_ustack_reserved_imm_chain',
        default_count=64,
        build_asm=build_asm_xor_ustack_reserved_imm_chain,
        timing=5,
        control_timing=10,
        timeout_s=2.0,
        start_tag=95,
        stop_tag=96,
        flags=0,
        args=[],
        fill_experiment_region=False,
        supports_ft_capture_flag=True,
        include_ft_capture_in_parse=True,
    ),
}
