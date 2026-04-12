from __future__ import annotations

import subprocess
from pathlib import Path

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.sample import SampleFabConstraints, SampleStackup
from jitx.shapes.composites import ShapelyGeometry, rectangle
from jitx.shapes.primitive import Circle, Text
from jitx.substrate import Substrate
from shapely.geometry import box
from shapely.ops import unary_union
from shared_components.ffc import HDGC60PinFfc

from src.components import SharpOrganizerBus

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_WIDTH = 46.0
BOARD_HEIGHT = 48.0
BOARD_RADIUS = 1.0
NARROW_WIDTH = 42.8
TOP_NOTCH_HEIGHT = 7.8
SIGNAL_SHRINK = 0.5
BUS_PAD_HEIGHT = 5.0


def make_board_geometry(*, shrink: float = 0.0) -> ShapelyGeometry:
    width = BOARD_WIDTH - 2.0 * shrink
    height = BOARD_HEIGHT - 2.0 * shrink
    radius = max(BOARD_RADIUS - shrink, 0.0)
    narrow_width = NARROW_WIDTH - 2.0 * shrink
    top_notch_height = TOP_NOTCH_HEIGHT - shrink
    side_width = (width - narrow_width) / 2.0

    outer = rectangle(width, height, radius=radius).to_shapely().g
    cutout_top = height / 2.0 - top_notch_height
    left_cutout = box(-width / 2.0, -height / 2.0, -width / 2.0 + side_width, cutout_top)
    right_cutout = box(width / 2.0 - side_width, -height / 2.0, width / 2.0, cutout_top)
    return ShapelyGeometry(outer.difference(unary_union([left_cutout, right_cutout])))


BOARD_SHAPE = make_board_geometry()
SIGNAL_AREA = make_board_geometry(shrink=SIGNAL_SHRINK)


class SharpOrganizerCardSubstrate(Substrate):
    # Python replacement for `setup-design-flex(...)` for this first pass port.
    stackup = SampleStackup(2)
    constraints = SampleFabConstraints()


class FFCConnector(Circuit):
    # Direct port of `components/FFCConnector.stanza` as used by the board.
    VCC5V = Port()
    GND = Port()
    data = [Port() for _ in range(48)]

    def __init__(self, *, flip_pins: bool = False):
        super().__init__()
        self.connector = HDGC60PinFfc()
        self.place(self.connector, Placement((0.0, 2.8), on=Side.Top))

        vcc_pin = 60 if flip_pins else 1
        gnd_pins = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]

        self.nets = [self.VCC5V + self.connector.p[vcc_pin - 1]]
        for pin in gnd_pins:
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(self.GND + self.connector.p[mapped_pin - 1])

        data_index = 0
        for pin in range(2, 61):
            if pin in gnd_pins:
                continue
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(self.data[data_index] + self.connector.p[mapped_pin - 1])
            data_index += 1

        marker_x = (-18.0 + 1.5) if flip_pins else (18.0 - 1.5)
        self += Silkscreen(Circle(diameter=1.0).at(marker_x, 0.0), side=FeatureSide.Top)


class SharpOrganizerCardCircuit(Circuit):
    # Direct port of `jitx/sharp-organizer-card.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()
        self.ffc = FFCConnector(flip_pins=False)
        self.bus = SharpOrganizerBus()

        data_ports = [
            self.bus.GND,
            self.bus.NC02,
            self.bus.STNBY,
            self.bus.VBATT,
            self.bus.VPP,
            self.bus.A15,
            self.bus.A14,
            self.bus.A13,
            self.bus.A12,
            self.bus.A11,
            self.bus.A10,
            self.bus.A9,
            self.bus.A8,
            self.bus.A7,
            self.bus.A6,
            self.bus.A5,
            self.bus.A4,
            self.bus.A3,
            self.bus.A2,
            self.bus.A1,
            self.bus.A0,
            self.bus.D0,
            self.bus.D1,
            self.bus.D2,
            self.bus.D3,
            self.bus.D4,
            self.bus.D5,
            self.bus.D6,
            self.bus.D7,
            self.bus.MSKROM,
            self.bus.SRAM1,
            self.bus.SRAM2,
            self.bus.EPROM,
            self.bus.RW,
            self.bus.OE,
            self.bus.A19,
            self.bus.A18,
            self.bus.A17,
            self.bus.A16,
            self.bus.CI,
            self.bus.E2,
            self.bus.NC42,
            self.bus.NC43,
            self.bus.NC44,
            self.bus.GND,
            self.bus.GND,
            self.bus.GND,
            self.bus.GND,
        ]
        data_names = [
            "GND",
            "NC02",
            "STNBY",
            "VBATT",
            "VPP",
            "A15",
            "A14",
            "A13",
            "A12",
            "A11",
            "A10",
            "A9",
            "A8",
            "A7",
            "A6",
            "A5",
            "A4",
            "A3",
            "A2",
            "A1",
            "A0",
            "D0",
            "D1",
            "D2",
            "D3",
            "D4",
            "D5",
            "D6",
            "D7",
            "MSKROM",
            "SRAM1",
            "SRAM2",
            "EPROM",
            "RW",
            "OE",
            "A19",
            "A18",
            "A17",
            "A16",
            "CI",
            "E2",
            "NC42",
            "NC43",
            "NC44",
            "GND",
            "GND",
            "GND",
            "GND",
        ]

        gnd_net = Net(name="GND") + self.gnd + self.ffc.GND + self.bus.GND
        self.nets = [Net(name="VCC") + self.vcc + self.ffc.VCC5V + self.bus.VCC]

        ffc_index = 47
        for index, (name, port) in enumerate(zip(data_names, data_ports, strict=True)):
            if name == "GND":
                gnd_net += self.ffc.data[ffc_index]
            else:
                self.nets.append(Net(name=f"{name}-DATA{index}") + port + self.ffc.data[ffc_index])
            ffc_index -= 1

        self.nets.append(gnd_net)

        self.place(self.ffc, Placement((0.0, -15.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.bus, Placement((0.0, BOARD_HEIGHT / 2.0 - BUS_PAD_HEIGHT / 2.0), on=Side.Top))

        self += Silkscreen(Text("SHARP Organizer Card adapter v1", 1.5).at(0.0, 1.5), side=FeatureSide.Bottom)
        self += Silkscreen(Text(f"(c) mblsha {BOARD_DATE}", 1.5).at(0.0, -1.5), side=FeatureSide.Bottom)


class SharpOrganizerCardBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SharpOrganizerCardDesign(Design):
    substrate = SharpOrganizerCardSubstrate()
    board = SharpOrganizerCardBoard()
    circuit = SharpOrganizerCardCircuit()
