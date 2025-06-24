#!/usr/bin/env python3
"""
Alchitry Au pin mappings for various boards.
Converts JITX pin definitions to Alchitry Labs constraint files.
"""

import re
from typing import Dict, List, Tuple

# AlchitryAu.stanza (print pin mapping)
ALCHITRY_ELEMENT_MAPPING = """
A[0] → a.T8 (A2)
A[1] → a.T10 (A49)
A[2] → a.T7 (A3)
A[3] → a.T9 (A48)
A[4] → a.T5 (A5)
A[5] → a.R6 (A46)
A[6] → a.R5 (A6)
A[7] → a.R7 (A45)
A[8] → a.R8 (A8)
A[9] → a.P9 (A43)
A[10] → a.P8 (A9)
A[11] → a.N9 (A42)
A[12] → a.L2 (A11)
A[13] → a.K2 (A40)
A[14] → a.L3 (A12)
A[15] → a.K3 (A39)
A[16] → a.J1 (A14)
A[17] → a.J4 (A37)
A[18] → a.K1 (A15)
A[19] → a.J5 (A36)
A[20] → a.H3 (A34)
A[21] → a.J3 (A33)
A[22] → a.K5 (A23)
A[23] → a.E6 (A24)
B[0] → b.D1 (B2)
B[1] → b.B1 (B49)
B[2] → b.E2 (B3)
B[3] → b.C1 (B48)
B[4] → b.A2 (B5)
B[5] → b.C2 (B46)
B[6] → b.B2 (B6)
B[7] → b.C3 (B45)
B[8] → b.E1 (B8)
B[9] → b.D3 (B43)
B[10] → b.F2 (B9)
B[11] → b.E3 (B42)
B[12] → b.F3 (B11)
B[13] → b.C4 (B40)
B[14] → b.F4 (B12)
B[15] → b.D4 (B39)
C[0] → c.T13 (C2)
C[1] → c.P11 (C49)
C[2] → c.R13 (C3)
C[3] → c.P10 (C48)
C[4] → c.T12 (C5)
C[5] → c.N12 (C46)
C[6] → c.R12 (C6)
C[7] → c.N11 (C45)
C[8] → c.R11 (C8)
C[9] → c.P13 (C43)
C[10] → c.R10 (C9)
C[11] → c.N13 (C42)
C[12] → c.N2 (C11)
C[13] → c.M1 (C40)
C[14] → c.N3 (C12)
C[15] → c.M2 (C39)
C[16] → c.P3 (C14)
C[17] → c.P1 (C37)
C[18] → c.P4 (C15)
C[19] → c.N1 (C36)
C[20] → c.M4 (C17)
C[21] → c.R1 (C34)
C[22] → c.L4 (C18)
C[23] → c.R2 (C33)
C[24] → c.N4 (C20)
C[25] → c.T2 (C31)
C[26] → c.M5 (C21)
C[27] → c.R3 (C30)
C[28] → c.L5 (C23)
C[29] → c.T3 (C28)
C[30] → c.P5 (C24)
C[31] → c.T4 (C27)
D[0] → d.R16 (D8)
D[1] → d.T15 (D43)
D[2] → d.R15 (D9)
D[3] → d.T14 (D42)
D[4] → d.P14 (D11)
D[5] → d.M15 (D12)
""".strip()

FFC_TO_ALCHITRY_MAPPING = """
loDATA0 → fpga.data_a[1]
loDATA1 → fpga.data_a[3]
loDATA2 → fpga.data_a[5]
loDATA3 → fpga.data_a[7]
loDATA4 → fpga.data_a[0]
loDATA5 → fpga.data_a[2]
loDATA6 → fpga.data_a[4]
loDATA7 → fpga.data_a[6]
loDATA8 → fpga.data_c[0]
loDATA9 → fpga.data_c[2]
loDATA10 → fpga.data_c[4]
loDATA11 → fpga.data_c[6]
loDATA12 → fpga.data_c[1]
loDATA13 → fpga.data_c[3]
loDATA14 → fpga.data_c[5]
loDATA15 → fpga.data_c[7]
loDATA16 → fpga.data_a[8]
loDATA17 → fpga.data_a[10]
loDATA18 → fpga.data_a[12]
loDATA19 → fpga.data_a[14]
loDATA20 → fpga.data_a[16]
loDATA21 → fpga.data_a[18]
loDATA22 → fpga.data_a[22]
loDATA23 → fpga.data_a[23]
loDATA24 → fpga.data_c[9]
loDATA25 → fpga.data_c[11]
loDATA26 → fpga.data_c[13]
loDATA27 → fpga.data_c[15]
loDATA28 → fpga.data_c[17]
loDATA29 → fpga.data_c[19]
loDATA30 → fpga.data_c[21]
loDATA31 → fpga.data_c[23]
loDATA40 → fpga.data_c[25]
loDATA41 → fpga.data_c[27]
loDATA42 → fpga.data_c[29]
loDATA43 → fpga.data_c[31]
loDATA44 → fpga.data_d[0]
loDATA45 → fpga.data_d[2]
loDATA46 → fpga.data_d[1]
loDATA47 → fpga.data_d[3]
loDATA32 → fpga.data_a[20]
loDATA33 → fpga.data_a[21]
loDATA34 → fpga.data_b[1]
loDATA35 → fpga.data_b[3]
loDATA36 → fpga.data_b[0]
loDATA37 → fpga.data_b[2]
loDATA38 → fpga.data_b[4]
loDATA39 → fpga.data_b[6]
""".strip()

# From alchitry-au1-level-shifter.stanza lines 106-113
SALEAE_TO_ALCHITRY_MAPPING = """
saleae3 → fpga.data_b[15]
saleae2 → fpga.data_b[13]
saleae1 → fpga.data_b[12]
saleae0 → fpga.data_b[14]
saleae7 → fpga.data_b[10]
saleae6 → fpga.data_b[8]
saleae5 → fpga.data_d[4]
saleae4 → fpga.data_d[5]
""".strip()

# sharp-pc-g850-bus.stanza (print pin mapping)
SHARP_PC_G850_BUS_MAPPING = """
0 → bus.GND
1 → bus.MREQ
2 → bus.M1
3 → bus.IORESET
4 → bus.IORQ
5 → bus.INT1
6 → bus.WAIT
7 → bus.RD
8 → bus.WR
9 → bus.BNK0
10 → bus.BNK1
11 → bus.CERAM2
12 → bus.CEROM2
13 → bus.D6
14 → bus.D7
15 → bus.D4
16 → bus.D5
17 → bus.D2
18 → bus.D3
19 → bus.D0
20 → bus.D1
21 → bus.A14
22 → bus.A15
23 → bus.A12
24 → bus.A13
25 → bus.A10
26 → bus.A11
27 → bus.A8
28 → bus.A9
29 → bus.A6
30 → bus.A7
31 → bus.A4
32 → bus.A5
33 → bus.A2
34 → bus.A3
35 → bus.A0
36 → bus.A1
""".strip()

# sharp-pc-e500-bus.stanza (print pin mapping)
SHARP_PC_E500_BUS_MAPPING = """
FPGA_MAP: 2 → bus.RW
FPGA_MAP: 3 → bus.A0
FPGA_MAP: 4 → bus.A1
FPGA_MAP: 6 → bus.A2
FPGA_MAP: 7 → bus.A3
FPGA_MAP: 8 → bus.A4
FPGA_MAP: 10 → bus.A5
FPGA_MAP: 11 → bus.A6
FPGA_MAP: 12 → bus.A7
FPGA_MAP: 14 → bus.A8
FPGA_MAP: 15 → bus.A9
FPGA_MAP: 16 → bus.A10
FPGA_MAP: 18 → bus.A11
FPGA_MAP: 19 → bus.A12
FPGA_MAP: 20 → bus.A13
FPGA_MAP: 22 → bus.A14
FPGA_MAP: 23 → bus.A15
FPGA_MAP: 24 → bus.A16
FPGA_MAP: 26 → bus.A17
FPGA_MAP: 27 → bus.VCC2
FPGA_MAP: 28 → bus.D0
FPGA_MAP: 30 → bus.D1
FPGA_MAP: 31 → bus.D2
FPGA_MAP: 33 → bus.D3
FPGA_MAP: 34 → bus.D4
FPGA_MAP: 35 → bus.D5
FPGA_MAP: 37 → bus.D6
FPGA_MAP: 38 → bus.D7
FPGA_MAP: 39 → bus.CE1
FPGA_MAP: 41 → bus.CE6
FPGA_MAP: 42 → bus.NC
FPGA_MAP: 43 → bus.OE
""".strip()

# sharp-sharp_organizer_card.stanza (print pin mapping)
SHARP_ORGANIZER_CARD_MAPPING = """
FPGA_MAP: 46 → NC02
FPGA_MAP: 45 → STNBY
FPGA_MAP: 44 → VBATT
FPGA_MAP: 43 → VPP
FPGA_MAP: 42 → A15
FPGA_MAP: 41 → A14
FPGA_MAP: 40 → A13
FPGA_MAP: 39 → A12
FPGA_MAP: 38 → A11
FPGA_MAP: 37 → A10
FPGA_MAP: 36 → A9
FPGA_MAP: 35 → A8
FPGA_MAP: 34 → A7
FPGA_MAP: 33 → A6
FPGA_MAP: 32 → A5
FPGA_MAP: 31 → A4
FPGA_MAP: 30 → A3
FPGA_MAP: 29 → A2
FPGA_MAP: 28 → A1
FPGA_MAP: 27 → A0
FPGA_MAP: 26 → D0
FPGA_MAP: 25 → D1
FPGA_MAP: 24 → D2
FPGA_MAP: 23 → D3
FPGA_MAP: 22 → D4
FPGA_MAP: 21 → D5
FPGA_MAP: 20 → D6
FPGA_MAP: 19 → D7
FPGA_MAP: 18 → MSKROM
FPGA_MAP: 17 → SRAM1
FPGA_MAP: 16 → SRAM2
FPGA_MAP: 15 → EPROM
FPGA_MAP: 14 → RW
FPGA_MAP: 13 → OE
FPGA_MAP: 12 → A19
FPGA_MAP: 11 → A18
FPGA_MAP: 10 → A17
FPGA_MAP: 9 → A16
FPGA_MAP: 8 → CI
FPGA_MAP: 7 → E2
FPGA_MAP: 6 → NC42
FPGA_MAP: 5 → NC43
FPGA_MAP: 4 → NC44
""".strip()

# sharp-sc62015-interposer.stanza (print pin mapping)
SHARP_SC62015_MAPPING = """
FPGA_MAP: 0 → cpu.D[0]
FPGA_MAP: 1 → cpu.D[1]
FPGA_MAP: 2 → cpu.D[2]
FPGA_MAP: 3 → cpu.D[3]
FPGA_MAP: 4 → cpu.D[4]
FPGA_MAP: 5 → cpu.D[5]
FPGA_MAP: 6 → cpu.D[6]
FPGA_MAP: 7 → cpu.D[7]
FPGA_MAP: 8 → cpu.A[0]
FPGA_MAP: 9 → cpu.A[1]
FPGA_MAP: 10 → cpu.A[2]
FPGA_MAP: 11 → cpu.A[3]
FPGA_MAP: 12 → cpu.A[4]
FPGA_MAP: 13 → cpu.A[5]
FPGA_MAP: 14 → cpu.A[6]
FPGA_MAP: 15 → cpu.A[7]
FPGA_MAP: 16 → cpu.A[8]
FPGA_MAP: 17 → cpu.A[9]
FPGA_MAP: 18 → cpu.A[10]
FPGA_MAP: 19 → cpu.A[11]
FPGA_MAP: 20 → cpu.A[12]
FPGA_MAP: 21 → cpu.A[13]
FPGA_MAP: 22 → cpu.A[14]
FPGA_MAP: 23 → cpu.A[15]
FPGA_MAP: 24 → cpu.A[16]
FPGA_MAP: 25 → cpu.A[17]
FPGA_MAP: 26 → cpu.A[18]
FPGA_MAP: 27 → cpu.DCLK
FPGA_MAP: 28 → cpu.OUT
FPGA_MAP: 29 → cpu.CE[7]
FPGA_MAP: 30 → cpu.CE[6]
FPGA_MAP: 31 → cpu.CE[5]
FPGA_MAP: 32 → cpu.CE[4]
FPGA_MAP: 33 → cpu.CE[3]
FPGA_MAP: 34 → cpu.CE[2]
FPGA_MAP: 35 → cpu.CE[1]
FPGA_MAP: 36 → cpu.CE[0]
FPGA_MAP: 37 → cpu.ACLK
FPGA_MAP: 38 → cpu.DIS
FPGA_MAP: 39 → cpu.RD
FPGA_MAP: 40 → cpu.RXD
FPGA_MAP: 41 → cpu.TXD
FPGA_MAP: 42 → cpu.RESET
FPGA_MAP: 43 → cpu.TEST
FPGA_MAP: 44 → cpu.ON
FPGA_MAP: 45 → cpu.WR
FPGA_MAP: 46 → cpu.MRQ
""".strip()


def get_alchitry_element_mapping() -> Dict[str, str]:
    """
    Maps from internal shield mapping to the Alchitry Labs constraint pin name
    """
    mapping = {}
    for line in ALCHITRY_ELEMENT_MAPPING.split("\n"):
        m = re.match(r"([A-D])\[(\d+)\] → [a-d]\.(\w+) \(([\w\d]+)\)", line)
        if m:
            bank, pin, bga_pin, internal_pin = m.groups()
            mapping[f"{bank}{pin}"] = (
                internal_pin  # Use internal pin name for Alchitry Labs
            )
    return mapping


def get_alchitry_ffc_mapping() -> Dict[int, str]:
    """
    Maps from FFC data pin to the internal bank name
    """
    mapping = {}
    for line in FFC_TO_ALCHITRY_MAPPING.split("\n"):
        m = re.match(r"loDATA(\d+) → fpga.data_([a-d])\[(\d+)\]", line)
        if m:
            ffc_pin, bank, bank_num = m.groups()
            mapping[int(ffc_pin)] = f"{bank.upper()}{bank_num}"
    return mapping


def get_saleae_mapping() -> Dict[int, str]:
    """
    Maps from Saleae pin to the internal bank name
    """
    mapping = {}
    for line in SALEAE_TO_ALCHITRY_MAPPING.split("\n"):
        m = re.match(r"saleae(\d+) → fpga.data_([a-d])\[(\d+)\]", line)
        if m:
            saleae_pin, bank, bank_num = m.groups()
            mapping[int(saleae_pin)] = f"{bank.upper()}{bank_num}"
    return mapping


def get_sharp_pc_g850_bus_mapping() -> Dict[str, str]:
    """
    Maps from internal shield mapping to the Sharp PC-G850 bus pin name
    """
    mapping = {}
    for line in SHARP_PC_G850_BUS_MAPPING.split("\n"):
        m = re.match(r"(\d+) → bus.(\w+)", line)
        if m:
            pin, name = m.groups()
            if name != "GND":
                mapping[pin] = name
    return mapping


def get_sharp_pc_e500_bus_mapping() -> Dict[str, str]:
    """
    Maps from internal element mapping to the Sharp PC-E500 bus pin name
    """
    mapping = {}
    for line in SHARP_PC_E500_BUS_MAPPING.split("\n"):
        if not line:
            continue
        m = re.match(r"FPGA_MAP: (\d+) → bus\.(\w+)", line)
        if m:
            pin, name = m.groups()
            if name != "GND":
                mapping[pin] = name
    return mapping


def get_sharp_organizer_card_mapping() -> Dict[str, str]:
    """
    Maps from internal element mapping to the Sharp Organizer Card
    """
    mapping = {}
    for line in SHARP_ORGANIZER_CARD_MAPPING.split("\n"):
        if not line:
            continue
        m = re.match(r"FPGA_MAP: (\d+) → (\w+)", line)
        if m:
            pin, name = m.groups()
            if name != "GND":
                mapping[pin] = name
    return mapping


def get_sharp_sc62015_mapping() -> Dict[str, str]:
    """
    Maps from internal element mapping to the Sharp sc62015
    """
    mapping = {}
    for line in SHARP_SC62015_MAPPING.split("\n"):
        if not line:
            continue
        m = re.match(r"FPGA_MAP: (\d+) → cpu.([\w\[\]]+)", line)
        if m:
            pin, name = m.groups()
            if name != "GND":
                mapping[pin] = name
    return mapping


def format_acf_content(pin_list: List[Tuple[str, str]]) -> str:
    """Format pin list as ACF content"""
    lines = ["STANDARD(LVCMOS33) {"]
    for signal, pin in pin_list:
        lines.append(f"    pin {signal} {pin}")
    lines.append("}")
    return "\n".join(lines)


def generate_pin_tester_acf() -> str:
    """Generate Pin Tester ACF content"""
    ffc = get_alchitry_ffc_mapping()
    alchitry_mapping = get_alchitry_element_mapping()

    pins = []
    for ffc_pin in sorted(ffc.keys()):
        if ffc_pin < 48:  # Only first 48 pins
            alchitry_pin = ffc[ffc_pin]
            pins.append((f"ffc_data[{ffc_pin}]", alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


def generate_saleae_acf() -> str:
    """Generate Saleae ACF content"""
    saleae = get_saleae_mapping()
    alchitry_mapping = get_alchitry_element_mapping()

    pins = []
    for saleae_pin in saleae.keys():
        alchitry_pin = saleae[saleae_pin]
        pins.append((f"saleae[{saleae_pin}]", alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


def generate_sharp_pc_g850_bus_acf() -> str:
    """Generate Sharp PC-G850 Bus ACF content"""
    ffc = get_alchitry_ffc_mapping()
    alchitry_mapping = get_alchitry_element_mapping()
    pcg850_mapping = get_sharp_pc_g850_bus_mapping()

    pins = []
    for pin, name in sorted(pcg850_mapping.items(), key=lambda x: int(x[0])):
        alchitry_pin = ffc[int(pin)]
        pins.append((name, alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


def generate_sharp_pc_e500_bus_acf() -> str:
    """Generate Sharp PC-E500 Bus ACF content"""
    ffc = get_alchitry_ffc_mapping()
    alchitry_mapping = get_alchitry_element_mapping()
    pce500_mapping = get_sharp_pc_e500_bus_mapping()

    pins = []
    for pin, name in sorted(pce500_mapping.items(), key=lambda x: int(x[0])):
        alchitry_pin = ffc[int(pin)]
        pins.append((name, alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


def generate_sharp_organizer_card_acf() -> str:
    """Generate Sharp Organizer Card ACF content"""
    ffc = get_alchitry_ffc_mapping()
    alchitry_mapping = get_alchitry_element_mapping()
    organizer_mapping = get_sharp_organizer_card_mapping()

    pins = []
    for pin, name in sorted(organizer_mapping.items(), key=lambda x: int(x[0])):
        alchitry_pin = ffc[int(pin)]
        pins.append((name, alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


def generate_sharp_sc62015_acf() -> str:
    """Generate Sharp SC62015 ACF content"""
    ffc = get_alchitry_ffc_mapping()
    alchitry_mapping = get_alchitry_element_mapping()
    sc62015_mapping = get_sharp_sc62015_mapping()

    pins = []
    for pin, name in sorted(sc62015_mapping.items(), key=lambda x: int(x[0])):
        alchitry_pin = ffc[int(pin)]
        pins.append((name, alchitry_mapping[alchitry_pin]))

    return format_acf_content(pins)


if __name__ == "__main__":
    # Example usage - print all mappings
    print("=== Pin Tester ===")
    print(generate_pin_tester_acf())
    print("\n=== Saleae ===")
    print(generate_saleae_acf())
    print("\n=== Sharp PC-G850 Bus ===")
    print(generate_sharp_pc_g850_bus_acf())
    print("\n=== Sharp PC-E500 Bus ===")
    print(generate_sharp_pc_e500_bus_acf())
    print("\n=== Sharp Organizer Card ===")
    print(generate_sharp_organizer_card_acf())
    print("\n=== Sharp SC62015 ===")
    print(generate_sharp_sc62015_acf())
