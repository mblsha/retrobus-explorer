from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.sample import SampleFabConstraints, SampleStackup
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Text
from jitx.substrate import Substrate

from src.components import (
    AlchitryA,
    AlchitryB,
    AlchitryC,
    AlchitryD,
    Cap0402,
    GndTestpads,
    HDGC60PinFfc,
    PinHeader2x3,
    SaleaeProbeHeader2x4,
    Txb0108Pwr,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_WIDTH = 65.0
BOARD_HEIGHT = 45.0
BOARD_SHAPE = rectangle(BOARD_WIDTH, BOARD_HEIGHT, radius=3.0)
SIGNAL_AREA = rectangle(BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0, radius=2.5)
FFC_HEIGHT = 5.5
FFC_DISTANCE = FFC_HEIGHT * 4.0
FFC_OFFSET_Y = FFC_HEIGHT / 2.0

ORDERED_PINS = [
    "A2", "A49", "A3", "A48", "A5", "A46", "A6", "A45", "A8", "A43", "A9", "A42", "A11", "A40", "A12", "A39",
    "A14", "A37", "A15", "A36", "A17", "A34", "A18", "A33", "A20", "A31", "A21", "A30", "A23", "A28", "A24", "A27",
    "B2", "B49", "B3", "B48", "B5", "B46", "B6", "B45", "B8", "B43", "B9", "B42", "B11", "B40", "B12", "B39",
    "B14", "B37", "B15", "B36", "B17", "B34", "B18", "B33", "B20", "B31", "B21", "B30", "B23", "B28", "B24", "B27",
    "C2", "C49", "C3", "C48", "C5", "C46", "C6", "C45", "C8", "C43", "C9", "C42", "C11", "C40", "C12", "C39",
    "C14", "C37", "C15", "C36", "C17", "C34", "C18", "C33", "C20", "C31", "C21", "C30", "C23", "C28", "C24", "C27",
    "D8", "D43", "D9", "D42", "D11", "D12",
]
FT_PINS = {
    "A17", "A18", "A20", "A21", "A27", "A28", "A30", "A31",
    "B14", "B15", "B17", "B18", "B20", "B21", "B23", "B24",
    "B27", "B28", "B30", "B31", "B33", "B34", "B36", "B37",
}
SAFE_ORDERED_PINS = [pin for pin in ORDERED_PINS if pin not in FT_PINS]
SAFE_BY_PREFIX = {
    prefix: [pin for pin in SAFE_ORDERED_PINS if pin.startswith(prefix)]
    for prefix in ("A", "B", "C", "D")
}


def chain_net(name: str | None, *ports: Port) -> Net:
    net = Net(name=name) if name is not None else Net()
    for port in ports:
        net = net + port
    return net


def port_attr(obj: object, name: str) -> Port:
    return cast(Port, getattr(obj, name))


class AlchitryAu1LevelShifterSubstrate(Substrate):
    # Python replacement for the Stanza `setup-design(...)` board defaults.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()


class FFCConnector(Circuit):
    # Direct port of `components/FFCConnector.stanza`.
    VCC5V = Port()
    GND = Port()
    data = [Port() for _ in range(48)]

    def __init__(self, *, flip_pins: bool = False):
        super().__init__()
        self.connector = HDGC60PinFfc()
        self.place(self.connector, Placement((0.0, 2.8), on=Side.Top))

        vcc_pin = 60 if flip_pins else 1
        gnd_pins = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

        self.nets = [chain_net(None, self.VCC5V, self.connector.p[vcc_pin - 1])]
        for pin in gnd_pins:
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(chain_net(None, self.GND, self.connector.p[mapped_pin - 1]))

        data_index = 0
        for pin in range(2, 61):
            if pin in gnd_pins:
                continue
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(chain_net(None, self.data[data_index], self.connector.p[mapped_pin - 1]))
            data_index += 1

        marker_x = (-18.0 + 1.5) if flip_pins else (18.0 - 1.5)
        self += Silkscreen(Circle(diameter=1.0).at(marker_x, 0.0), side=FeatureSide.Top)


class Saleae8(Circuit):
    # Direct port of `components/Saleae/saleae8`.
    gnd = Port()
    data = [Port() for _ in range(8)]

    def __init__(self, *, text_angle: float = 0.0):
        super().__init__()
        self.upper = SaleaeProbeHeader2x4()
        self.lower = SaleaeProbeHeader2x4()

        self.nets = [
            chain_net(None, self.gnd, self.upper.GND, self.lower.GND),
            chain_net("SALEAE0", self.data[0], self.lower.p0),
            chain_net("SALEAE1", self.data[1], self.lower.p1),
            chain_net("SALEAE2", self.data[2], self.lower.p2),
            chain_net("SALEAE3", self.data[3], self.lower.p3),
            chain_net("SALEAE4", self.data[4], self.upper.p0),
            chain_net("SALEAE5", self.data[5], self.upper.p1),
            chain_net("SALEAE6", self.data[6], self.upper.p2),
            chain_net("SALEAE7", self.data[7], self.upper.p3),
        ]

        self.place(self.upper, Placement((0.0, 6.731), on=Side.Top))
        self.place(self.lower, Placement((0.0, -6.731), on=Side.Top))

        for index in range(4):
            offset = 2.54 * index
            self += Silkscreen(
                Text(str(7 - index), 1.5).at(3.5, 6.731 + 3.8 - offset, rotate=text_angle),
                side=FeatureSide.Top,
            )
            self += Silkscreen(
                Text(str(3 - index), 1.5).at(3.5, -6.731 + 3.8 - offset, rotate=text_angle),
                side=FeatureSide.Top,
            )


class VccSelectHeader(Circuit):
    # Direct port of `components/VccSelectHeader.stanza`.
    bus = Port()
    fpga_5v = Port()
    fpga_3v3 = Port()

    def __init__(self, *, text_angle: float = 0.0):
        super().__init__()
        self.header = PinHeader2x3()
        self.nets = [
            chain_net("BUS", self.bus, self.header.p[0], self.header.p[2], self.header.p[4]),
            chain_net("FPGA_3V3", self.fpga_3v3, self.header.p[1]),
            chain_net("FPGA_5V", self.fpga_5v, self.header.p[3]),
        ]
        self.place(self.header, Placement((0.0, 0.0), on=Side.Top))

        for index, name in enumerate(["NC", "5V", "3V3"]):
            offset = 2.54 * index - 2.54
            self += Silkscreen(Text(name, 1.5).at(4.1, offset, rotate=text_angle), side=FeatureSide.Top)
            self += Silkscreen(Text("VBus", 1.5).at(-4.5, offset, rotate=text_angle), side=FeatureSide.Top)


class LevelShifter(Circuit):
    # Direct port of `components/LevelShifter/module`.
    vcclo = Port()
    vcchi = Port()
    gnd = Port()
    oe = Port()
    lo = [Port() for _ in range(8)]
    hi = [Port() for _ in range(8)]

    def __init__(self):
        super().__init__()
        self.shifter = Txb0108Pwr()
        self.cap_lo = Cap0402()
        self.cap_hi = Cap0402()

        self.nets = [
            chain_net(None, self.gnd, self.shifter.GND, self.cap_lo.p[1], self.cap_hi.p[1]),
            chain_net(None, self.vcclo, self.shifter.VCCA, self.cap_lo.p[0]),
            chain_net(None, self.vcchi, self.shifter.VCCB, self.cap_hi.p[0]),
            chain_net(None, self.oe, self.shifter.OE),
            chain_net(None, self.lo[0], self.shifter.A1),
            chain_net(None, self.lo[1], self.shifter.A2),
            chain_net(None, self.lo[2], self.shifter.A3),
            chain_net(None, self.lo[3], self.shifter.A4),
            chain_net(None, self.lo[4], self.shifter.A5),
            chain_net(None, self.lo[5], self.shifter.A6),
            chain_net(None, self.lo[6], self.shifter.A7),
            chain_net(None, self.lo[7], self.shifter.A8),
            chain_net(None, self.hi[0], self.shifter.B1),
            chain_net(None, self.hi[1], self.shifter.B2),
            chain_net(None, self.hi[2], self.shifter.B3),
            chain_net(None, self.hi[3], self.shifter.B4),
            chain_net(None, self.hi[4], self.shifter.B5),
            chain_net(None, self.hi[5], self.shifter.B6),
            chain_net(None, self.hi[6], self.shifter.B7),
            chain_net(None, self.hi[7], self.shifter.B8),
        ]

        self.place(self.shifter, Placement((0.0, 0.0), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.cap_lo, Placement((-2.0, 3.9), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.cap_hi, Placement((2.0, 3.9), 270, on=Side.Top))  # ty: ignore[no-matching-overload]


class AlchitryElementBottom(Circuit):
    # Direct port of `components/AlchitryAu/alchitry_element_bottom`.
    data = [Port() for _ in range(len(SAFE_ORDERED_PINS))]
    data_a = [Port() for _ in range(len(SAFE_BY_PREFIX["A"]))]
    data_b = [Port() for _ in range(len(SAFE_BY_PREFIX["B"]))]
    data_c = [Port() for _ in range(len(SAFE_BY_PREFIX["C"]))]
    data_d = [Port() for _ in range(len(SAFE_BY_PREFIX["D"]))]
    VCC5V = Port()
    VCC3V3 = Port()
    GND = Port()

    def __init__(self):
        super().__init__()
        self.a = AlchitryA()
        self.b = AlchitryB()
        self.c = AlchitryC()
        self.d = AlchitryD()

        self.nets = [
            chain_net(None, self.VCC5V, port_attr(self.a, "VCC5V"), port_attr(self.b, "VCC5V"), port_attr(self.c, "VCC5V"), port_attr(self.d, "VCC5V")),
            chain_net(None, self.VCC3V3, port_attr(self.a, "VCC3V3"), port_attr(self.b, "VCC3V3"), port_attr(self.c, "VCC3V3"), port_attr(self.d, "VCC3V3")),
            chain_net(None, self.GND, port_attr(self.a, "GND"), port_attr(self.b, "GND"), port_attr(self.c, "GND"), port_attr(self.d, "GND")),
        ]

        pin_map = {
            "A2": port_attr(self.a, "T8"),
            "A3": port_attr(self.a, "T7"),
            "A5": port_attr(self.a, "T5"),
            "A6": port_attr(self.a, "R5"),
            "A8": port_attr(self.a, "R8"),
            "A9": port_attr(self.a, "P8"),
            "A11": port_attr(self.a, "L2"),
            "A12": port_attr(self.a, "L3"),
            "A14": port_attr(self.a, "J1"),
            "A15": port_attr(self.a, "K1"),
            "A17": port_attr(self.a, "H1"),
            "A18": port_attr(self.a, "H2"),
            "A20": port_attr(self.a, "G1"),
            "A21": port_attr(self.a, "G2"),
            "A23": port_attr(self.a, "K5"),
            "A24": port_attr(self.a, "E6"),
            "A27": port_attr(self.a, "M6"),
            "A28": port_attr(self.a, "N6"),
            "A30": port_attr(self.a, "H5"),
            "A31": port_attr(self.a, "H4"),
            "A33": port_attr(self.a, "J3"),
            "A34": port_attr(self.a, "H3"),
            "A36": port_attr(self.a, "J5"),
            "A37": port_attr(self.a, "J4"),
            "A39": port_attr(self.a, "K3"),
            "A40": port_attr(self.a, "K2"),
            "A42": port_attr(self.a, "N9"),
            "A43": port_attr(self.a, "P9"),
            "A45": port_attr(self.a, "R7"),
            "A46": port_attr(self.a, "R6"),
            "A48": port_attr(self.a, "T9"),
            "A49": port_attr(self.a, "T10"),
            "B2": port_attr(self.b, "D1"),
            "B3": port_attr(self.b, "E2"),
            "B5": port_attr(self.b, "A2"),
            "B6": port_attr(self.b, "B2"),
            "B8": port_attr(self.b, "E1"),
            "B9": port_attr(self.b, "F2"),
            "B11": port_attr(self.b, "F3"),
            "B12": port_attr(self.b, "F4"),
            "B14": port_attr(self.b, "A3"),
            "B15": port_attr(self.b, "B4"),
            "B17": port_attr(self.b, "A4"),
            "B18": port_attr(self.b, "A5"),
            "B20": port_attr(self.b, "B5"),
            "B21": port_attr(self.b, "B6"),
            "B23": port_attr(self.b, "A7"),
            "B24": port_attr(self.b, "B7"),
            "B27": port_attr(self.b, "C7"),
            "B28": port_attr(self.b, "C6"),
            "B30": port_attr(self.b, "D6"),
            "B31": port_attr(self.b, "D5"),
            "B33": port_attr(self.b, "F5"),
            "B34": port_attr(self.b, "E5"),
            "B36": port_attr(self.b, "G5"),
            "B37": port_attr(self.b, "G4"),
            "B39": port_attr(self.b, "D4"),
            "B40": port_attr(self.b, "C4"),
            "B42": port_attr(self.b, "E3"),
            "B43": port_attr(self.b, "D3"),
            "B45": port_attr(self.b, "C3"),
            "B46": port_attr(self.b, "C2"),
            "B48": port_attr(self.b, "C1"),
            "B49": port_attr(self.b, "B1"),
            "C2": port_attr(self.c, "T13"),
            "C3": port_attr(self.c, "R13"),
            "C5": port_attr(self.c, "T12"),
            "C6": port_attr(self.c, "R12"),
            "C8": port_attr(self.c, "R11"),
            "C9": port_attr(self.c, "R10"),
            "C11": port_attr(self.c, "N2"),
            "C12": port_attr(self.c, "N3"),
            "C14": port_attr(self.c, "P3"),
            "C15": port_attr(self.c, "P4"),
            "C17": port_attr(self.c, "M4"),
            "C18": port_attr(self.c, "L4"),
            "C20": port_attr(self.c, "N4"),
            "C21": port_attr(self.c, "M5"),
            "C23": port_attr(self.c, "L5"),
            "C24": port_attr(self.c, "P5"),
            "C27": port_attr(self.c, "T4"),
            "C28": port_attr(self.c, "T3"),
            "C30": port_attr(self.c, "R3"),
            "C31": port_attr(self.c, "T2"),
            "C33": port_attr(self.c, "R2"),
            "C34": port_attr(self.c, "R1"),
            "C36": port_attr(self.c, "N1"),
            "C37": port_attr(self.c, "P1"),
            "C39": port_attr(self.c, "M2"),
            "C40": port_attr(self.c, "M1"),
            "C42": port_attr(self.c, "N13"),
            "C43": port_attr(self.c, "P13"),
            "C45": port_attr(self.c, "N11"),
            "C46": port_attr(self.c, "N12"),
            "C48": port_attr(self.c, "P10"),
            "C49": port_attr(self.c, "P11"),
            "D8": port_attr(self.d, "R16"),
            "D9": port_attr(self.d, "R15"),
            "D11": port_attr(self.d, "P14"),
            "D12": port_attr(self.d, "M15"),
            "D42": port_attr(self.d, "T14"),
            "D43": port_attr(self.d, "T15"),
        }

        prefix_ports = {
            "A": self.data_a,
            "B": self.data_b,
            "C": self.data_c,
            "D": self.data_d,
        }
        prefix_index = {key: 0 for key in prefix_ports}

        for data_index, key in enumerate(SAFE_ORDERED_PINS):
            prefix = key[0]
            scoped_index = prefix_index[prefix]
            self.nets.append(
                chain_net(
                    None,
                    self.data[data_index],
                    prefix_ports[prefix][scoped_index],
                    pin_map[key],
                )
            )
            prefix_index[prefix] += 1

        vertical_outer_spacing = 36.0
        left_to_side = 5.40
        case_width = 15.20
        b_d_offset_left = BOARD_WIDTH / -2.0 + left_to_side + case_width / 2.0
        self.place(self.b, Placement((b_d_offset_left, vertical_outer_spacing / 2.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.a, Placement((b_d_offset_left + 10.3 + case_width, vertical_outer_spacing / 2.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.d, Placement((b_d_offset_left, vertical_outer_spacing / -2.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.c, Placement((b_d_offset_left + 6.3 + case_width, vertical_outer_spacing / -2.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]


@dataclass(frozen=True)
class ConnSpec:
    start_index: int
    shifter_index: int
    invert_shifter_index: bool
    fpga_prefix: str
    shifter_start_index: int
    fpga_pins: tuple[int, ...]


CONVERSION = [
    ConnSpec(0, 0, False, "A", 0, (1, 3, 5, 7, 0, 2, 4, 6)),
    ConnSpec(8, 4, True, "C", 0, (0, 2, 4, 6, 1, 3, 5, 7)),
    ConnSpec(16, 1, False, "A", 0, (8, 10, 12, 14, 16, 18, 22, 23)),
    ConnSpec(24, 2, True, "C", 0, (9, 11, 13, 15, 17, 19, 21, 23)),
    ConnSpec(40, 3, True, "C", 0, (25, 27, 29, 31)),
    ConnSpec(44, 3, True, "D", 4, (0, 2, 1, 3)),
    ConnSpec(32, 5, False, "A", 0, (20, 21)),
    ConnSpec(34, 5, False, "B", 2, (1, 3, 0, 2, 4, 6)),
]


class AlchitryAu1LevelShifterCircuit(Circuit):
    # Direct port of `jitx/alchitry-au1-level-shifter.stanza`.
    gnd = Port()
    vcc3v3 = Port()
    vbus = Port()

    def __init__(self):
        super().__init__()
        self.fpga = AlchitryElementBottom()
        self.ffc1 = FFCConnector(flip_pins=False)
        self.ffc2 = FFCConnector(flip_pins=False)
        self.saleae = Saleae8(text_angle=90.0)
        self.vcc_select = VccSelectHeader(text_angle=180.0)
        self.shift = [LevelShifter() for _ in range(6)]
        self.tp_gnd = GndTestpads(diameter=3.0, width=BOARD_WIDTH, height=BOARD_HEIGHT)

        gnd_net = chain_net("GND", self.gnd, self.fpga.GND, self.ffc1.GND, self.ffc2.GND, self.saleae.gnd, self.tp_gnd.GND)
        vcc3v3_net = chain_net("VCC3V3", self.vcc3v3, self.fpga.VCC3V3, self.vcc_select.fpga_3v3)
        vbus_net = chain_net("VBUS", self.vbus, self.ffc1.VCC5V, self.ffc2.VCC5V, self.vcc_select.bus)
        for shifter in self.shift:
            gnd_net = gnd_net + shifter.gnd
            vcc3v3_net = vcc3v3_net + shifter.vcclo + shifter.oe
            vbus_net = vbus_net + shifter.vcchi

        self.nets = [
            gnd_net,
            vcc3v3_net,
            vbus_net,
            chain_net("VCC5V", self.vcc_select.fpga_5v, self.fpga.VCC5V),
            chain_net("SALEAE7", self.saleae.data[7], self.fpga.data_b[15]),
            chain_net("SALEAE6", self.saleae.data[6], self.fpga.data_b[13]),
            chain_net("SALEAE5", self.saleae.data[5], self.fpga.data_b[12]),
            chain_net("SALEAE4", self.saleae.data[4], self.fpga.data_b[14]),
            chain_net("SALEAE3", self.saleae.data[3], self.fpga.data_b[10]),
            chain_net("SALEAE2", self.saleae.data[2], self.fpga.data_b[8]),
            chain_net("SALEAE1", self.saleae.data[1], self.fpga.data_d[4]),
            chain_net("SALEAE0", self.saleae.data[0], self.fpga.data_d[5]),
        ]

        fpga_ports = {
            "A": self.fpga.data_a,
            "B": self.fpga.data_b,
            "C": self.fpga.data_c,
            "D": self.fpga.data_d,
        }
        for spec in CONVERSION:
            for offset, fpga_index in enumerate(spec.fpga_pins):
                data_index = spec.start_index + offset
                if spec.invert_shifter_index:
                    shifter_pin = 7 - offset - spec.shifter_start_index
                else:
                    shifter_pin = offset + spec.shifter_start_index
                self.nets.append(
                    chain_net(
                        f"DATA{data_index}",
                        self.ffc1.data[data_index],
                        self.ffc2.data[data_index],
                        self.shift[spec.shifter_index].hi[shifter_pin],
                    )
                )
                self.nets.append(
                    chain_net(
                        f"loDATA{data_index}",
                        fpga_ports[spec.fpga_prefix][fpga_index],
                        self.shift[spec.shifter_index].lo[shifter_pin],
                    )
                )

        self.place(self.fpga, Placement((0.0, 0.0), on=Side.Top))
        self.place(self.shift[0], Placement((14.734, 9.468), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.shift[1], Placement((4.8113, 9.468), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.shift[2], Placement((0.3, -9.468), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.shift[3], Placement((-9.2, -9.468), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.shift[4], Placement((9.8165, -9.468), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.shift[5], Placement((-7.0, 9.468), 270, on=Side.Top))  # ty: ignore[no-matching-overload]

        self.place(self.tp_gnd, Placement((0.0, 0.0), on=Side.Top))
        self.place(self.ffc1, Placement((2.3960, FFC_OFFSET_Y - FFC_DISTANCE / 2.0), 180, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.ffc2, Placement((2.3960, FFC_OFFSET_Y + FFC_DISTANCE / 2.0), 180, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.saleae, Placement((BOARD_WIDTH / -2.0 + 10.0, 0.0), on=Side.Bottom))
        self.place(self.vcc_select, Placement((BOARD_WIDTH / 2.0 - 7.0, 0.0), 180, on=Side.Bottom))  # ty: ignore[no-matching-overload]

        self += Silkscreen(Text("Level Shifter Element (Au1) v2", 1.5).at(0.0, 1.0), side=FeatureSide.Bottom)
        self += Silkscreen(Text(f"(c) mblsha {BOARD_DATE}", 1.5).at(0.0, -1.0), side=FeatureSide.Bottom)


class AlchitryAu1LevelShifterBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class AlchitryAu1LevelShifterDesign(Design):
    substrate = AlchitryAu1LevelShifterSubstrate()
    board = AlchitryAu1LevelShifterBoard()
    circuit = AlchitryAu1LevelShifterCircuit()
