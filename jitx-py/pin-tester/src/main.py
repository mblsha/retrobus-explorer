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
from jitx.via import Via, ViaType
from shared_components.ffc import HDGC60PinFfc
from shared_components.testpads import GndTestpads

from src.components import (
    PinHeader2x4,
    PinHeader2x8,
    SignalTestPad,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(50.0, 40.0, radius=3.0)
SIGNAL_AREA = rectangle(49.0, 39.0, radius=2.5)
DATA_HEADER_XS = [12.0, 7.25, 2.5, -2.25, -7.0, -11.75]
POWER_HEADER_POSITIONS = [(16.75, -10.0), (-16.5, 10.0)]
HEADER_ROW_Y = 10.0
DATA_HEADER_LABEL_OFFSET_X = 3.4
DATA_HEADER_START_OFFSET_Y = 3.81
DATA_HEADER_MARKER_DIAMETER = 0.8
DATA_HEADER_MARKER_OFFSET_X = 2.54
DATA_HEADER_MARKER_OFFSET_Y = 5.08


class PinTesterSubstrate(Substrate):
    # Python replacement for the shared design/default stackup setup that the
    # Stanza project gets via `setup-design(...)` and `helpers.stanza`.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()

    class StandardThroughVia(Via):
        start_layer = 0
        stop_layer = 3
        diameter = 0.6
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class PowerPins(Circuit):
    # Direct port of `pcb-module power-pins` in `jitx/pin-tester.stanza`.
    vcc = Port()
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.header = PinHeader2x4()
        self.nets = [
            self.vcc + self.header.p[0] + self.header.p[1],
            self.gnd + self.header.p[2] + self.header.p[3],
        ]
        self.place(self.header, Placement((0.0, 0.0), on=Side.Top))

        for text, y in [("VCC", 1.27), ("GND", -1.27)]:
            self += Silkscreen(Text(text, 1.0).at(3.5, y), side=FeatureSide.Top)
            self += Silkscreen(Text(text, 1.0).at(-3.5, y), side=FeatureSide.Top)


class TestPins(Circuit):
    # Direct port of `pcb-module test-pins(start-index:Int)` in
    # `jitx/pin-tester.stanza`.
    data = [Port() for _ in range(8)]

    def __init__(self, start_index: int):
        super().__init__()
        self.header = PinHeader2x8()
        self.place(self.header, Placement((0.0, 0.0), on=Side.Top))

        self.nets = [self.data[index] + self.header.p[index] for index in range(8)]


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


class PinTesterCircuit(Circuit):
    # Direct port of the main `pcb-module pin-tester` in
    # `jitx/pin-tester.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()

        self.ffc = FFCConnector(flip_pins=True)
        self.power_headers = [PowerPins() for _ in range(2)]
        self.test_headers = [TestPins(8 * idx) for idx in range(6)]
        self.signal_testpad = SignalTestPad()
        self.gnd_testpads = GndTestpads(diameter=3.0, width=50.0, height=40.0)

        gnd_net = Net(name="GND") + self.gnd + self.ffc.GND
        vcc_net = Net(name="VCC") + self.vcc + self.ffc.VCC5V

        self.nets = []

        for power in self.power_headers:
            gnd_net += power.gnd
            vcc_net += power.vcc

        for header_index, header in enumerate(self.test_headers):
            for bit in range(8):
                self.nets.append(header.data[bit] + self.ffc.data[header_index * 8 + bit])

        self.nets.append(self.ffc.data[0] + self.signal_testpad.tp)

        gnd_net += self.gnd_testpads.GND

        self.nets.extend([gnd_net, vcc_net])

        self.place(self.ffc, Placement((0.0, -4.5), on=Side.Bottom))

        for index, header in enumerate(self.test_headers):
            x = DATA_HEADER_XS[index]
            y = HEADER_ROW_Y if index % 2 == 0 else -HEADER_ROW_Y
            self.place(header, Placement((x, y), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
            self += Silkscreen(
                Circle(diameter=DATA_HEADER_MARKER_DIAMETER).at(
                    x + DATA_HEADER_MARKER_OFFSET_X,
                    y + DATA_HEADER_MARKER_OFFSET_Y,
                ),
                side=FeatureSide.Top,
            )
            for column in range(2):
                for row in range(4):
                    num = 8 * index + column * 4 + (3 - row)
                    text_x = x + (DATA_HEADER_LABEL_OFFSET_X if column == 0 else -DATA_HEADER_LABEL_OFFSET_X)
                    text_y = y - DATA_HEADER_START_OFFSET_Y + 2.54 * row
                    self += Silkscreen(Text(str(num), 1.0).at(text_x, text_y), side=FeatureSide.Top)

        self.place(self.power_headers[0], Placement(POWER_HEADER_POSITIONS[0], on=Side.Top))
        self.place(self.power_headers[1], Placement(POWER_HEADER_POSITIONS[1], on=Side.Top))
        self.place(self.signal_testpad, Placement((13.27, 16.35), on=Side.Top))

        self.place(self.gnd_testpads, Placement((0.0, 0.0), on=Side.Top))


class PinTesterBoard(Board):
    # Collects the Stanza board-shape and version-label behavior into the
    # Python board definition.
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(Text(f"pin-tester v1 (c) mblsha {BOARD_DATE}", 1.5).at(0.0, 18.0), side=FeatureSide.Top)


class PinTesterDesign(Design):
    # Structural equivalent of `setup-design(...)` + `set-main-module(pin-tester)`
    # in `jitx/pin-tester.stanza`.
    substrate = PinTesterSubstrate()
    board = PinTesterBoard()
    circuit = PinTesterCircuit()
