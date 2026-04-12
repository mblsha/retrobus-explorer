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
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Text
from jitx.substrate import Substrate
from retrobus_jitx_parts.ffc import HDGC60PinFfc

from src.components import SharpPcE500RamCard

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(54.0, 42.0, radius=2.0)
SIGNAL_AREA = rectangle(53.0, 41.0, radius=1.5)
BUS_PAD_HEIGHT = 10.0


class SharpPcE500RamCardSubstrate(Substrate):
    # Python replacement for `setup-design(...)` default stackup.
    stackup = SampleStackup(4)
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


class SharpPcE500RamCardCircuit(Circuit):
    # Direct port of `jitx/sharp-pc-e500-ram-card.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()
        self.ffc = FFCConnector(flip_pins=True)
        self.bus = SharpPcE500RamCard()

        self.nets = [
            Net(name="VCC") + self.vcc + self.ffc.VCC5V + self.bus.VCC,
        ]

        # The archived KiCad board uses one shared ground net name,
        # `GND-DATA1`, for both the dedicated FFC ground pins and the extra
        # interleaved ground lanes, plus the RAM-card ground blade.
        gnd_data_net = Net(name="GND-DATA1") + self.gnd + self.ffc.GND + self.bus.GND

        data_entries = [
            ("GND", self.bus.GND),
            ("GND", self.bus.GND),
            ("RW", self.bus.RW),
            ("A0", self.bus.A0),
            ("A1", self.bus.A1),
            ("GND", self.bus.GND),
            ("A2", self.bus.A2),
            ("A3", self.bus.A3),
            ("A4", self.bus.A4),
            ("GND", self.bus.GND),
            ("A5", self.bus.A5),
            ("A6", self.bus.A6),
            ("A7", self.bus.A7),
            ("GND", self.bus.GND),
            ("A8", self.bus.A8),
            ("A9", self.bus.A9),
            ("A10", self.bus.A10),
            ("GND", self.bus.GND),
            ("A11", self.bus.A11),
            ("A12", self.bus.A12),
            ("A13", self.bus.A13),
            ("GND", self.bus.GND),
            ("A14", self.bus.A14),
            ("A15", self.bus.A15),
            ("A16", self.bus.A16),
            ("GND", self.bus.GND),
            ("A17", self.bus.A17),
            ("VCC2", self.bus.VCC2),
            ("D0", self.bus.D0),
            ("GND", self.bus.GND),
            ("D1", self.bus.D1),
            ("D2", self.bus.D2),
            ("GND", self.bus.GND),
            ("D3", self.bus.D3),
            ("D4", self.bus.D4),
            ("D5", self.bus.D5),
            ("GND", self.bus.GND),
            ("D6", self.bus.D6),
            ("D7", self.bus.D7),
            ("CE1", self.bus.CE1),
            ("GND", self.bus.GND),
            ("CE6", self.bus.CE6),
            ("NC", self.bus.NC),
            ("OE", self.bus.OE),
            ("GND", self.bus.GND),
            ("GND", self.bus.GND),
            ("GND", self.bus.GND),
            ("GND", self.bus.GND),
        ]

        for index, (name, port) in enumerate(data_entries):
            if name == "GND":
                gnd_data_net += self.ffc.data[index]
            elif name != "GND":
                self.nets.append(Net(name=f"{name}-DATA{index}") + port + self.ffc.data[index])

        self.nets.append(gnd_data_net)

        self.place(self.ffc, Placement((0.0, 0.0), 180, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.bus, Placement((0.0, 42.0 / 2.0 - BUS_PAD_HEIGHT / 2.0), on=Side.Top))

        label_text = f"SHARP PC-E500 adapter v1 (c) mblsha {BOARD_DATE}"
        self += Silkscreen(Text(label_text, 1.5).at(0.0, -42.0 / 2.0 + 2.0), side=FeatureSide.Bottom)


class SharpPcE500RamCardBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SharpPcE500RamCardDesign(Design):
    substrate = SharpPcE500RamCardSubstrate()
    board = SharpPcE500RamCardBoard()
    circuit = SharpPcE500RamCardCircuit()
