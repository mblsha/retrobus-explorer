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
from jitx.shapes.primitive import Text
from jitx.substrate import Substrate
from jitx.via import Via, ViaType

from src.components import PinHeader1x20, PinHeader2x20

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

CONNECTORS_SPACING = 7.0
FORTY_PIN_WIDTH = 5.0
PICO_WIDTH = 17.78
BOARD_WIDTH = 52.0
BOARD_HEIGHT = PICO_WIDTH + CONNECTORS_SPACING + FORTY_PIN_WIDTH
BOARD_RADIUS = 1.0
Y_OFFSET = -5.0

BOARD_SHAPE = rectangle(BOARD_WIDTH, BOARD_HEIGHT, radius=BOARD_RADIUS)
SIGNAL_AREA = rectangle(BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0, radius=BOARD_RADIUS - 0.5)


class RpiPico40PinAdapterSubstrate(Substrate):
    # Python replacement for the Stanza `setup-design(...)` default stackup.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()

    class StandardThroughVia(Via):
        start_layer = 0
        stop_layer = 3
        diameter = 0.6
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class RPiPico(Circuit):
    # Direct port of `components/RPiPico/module`. The archived KiCad board
    # leaves the GP28-side pad as a standalone named pad net rather than
    # exporting it as `BCM-28`, so this port keeps the external BCM bus at
    # `0..27` for parity with the golden reference.
    BCM = [Port() for _ in range(28)]
    gnd = Port()
    p3v3 = Port()

    def __init__(self):
        super().__init__()
        self.left_header = PinHeader1x20()
        self.right_header = PinHeader1x20()

        self.place(self.left_header, Placement((-PICO_WIDTH / 2.0, 0.0), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.right_header, Placement((PICO_WIDTH / 2.0, 0.0), 270, on=Side.Top))  # ty: ignore[no-matching-overload]

        self.nets = [
            Net(name="pico_header0_p1") + self.left_header.p[0],
            Net(name="pico_header0_p2") + self.left_header.p[1],
            self.gnd + self.left_header.p[2] + self.left_header.p[7] + self.left_header.p[12] + self.left_header.p[17],
            self.BCM[2] + self.left_header.p[3],
            self.BCM[3] + self.left_header.p[4],
            self.BCM[4] + self.left_header.p[5],
            self.BCM[5] + self.left_header.p[6],
            self.BCM[6] + self.left_header.p[8],
            self.BCM[7] + self.left_header.p[9],
            self.BCM[8] + self.left_header.p[10],
            self.BCM[9] + self.left_header.p[11],
            self.BCM[10] + self.left_header.p[13],
            self.BCM[11] + self.left_header.p[14],
            self.BCM[12] + self.left_header.p[15],
            self.BCM[13] + self.left_header.p[16],
            self.BCM[14] + self.left_header.p[18],
            self.BCM[15] + self.left_header.p[19],
            self.BCM[16] + self.right_header.p[0],
            self.BCM[17] + self.right_header.p[1],
            self.gnd + self.right_header.p[2] + self.right_header.p[7] + self.right_header.p[12] + self.right_header.p[16],
            self.BCM[18] + self.right_header.p[3],
            self.BCM[19] + self.right_header.p[4],
            self.BCM[20] + self.right_header.p[5],
            self.BCM[21] + self.right_header.p[6],
            self.BCM[22] + self.right_header.p[8],
            self.BCM[26] + self.right_header.p[10],
            self.BCM[27] + self.right_header.p[11],
            Net(name="pico_header1_p14") + self.right_header.p[13],
        ]


class RaspberryPi40PinHeader(Circuit):
    # Closest Python replacement for
    # `ocdb/components/raspberry-pi/gpio-header/module`. The golden KiCad board
    # leaves physical pins 1, 2, 4, 17, 27, and 28 as standalone header nets.
    BCM = [Port() for _ in range(28)]
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.header = PinHeader2x20()
        self.place(self.header, Placement((0.0, 0.0), 90, on=Side.Top))  # ty: ignore[no-matching-overload]

        self.nets = [
            Net(name="header_p1") + self.header.p[0] + self.header.p[16],
            Net(name="header_p4") + self.header.p[1] + self.header.p[3],
            self.BCM[2] + self.header.p[2],
            self.BCM[3] + self.header.p[4],
            self.gnd + self.header.p[5] + self.header.p[8] + self.header.p[13] + self.header.p[19] + self.header.p[24] + self.header.p[29] + self.header.p[33] + self.header.p[38],
            self.BCM[4] + self.header.p[6],
            self.BCM[14] + self.header.p[7],
            self.BCM[15] + self.header.p[9],
            self.BCM[17] + self.header.p[10],
            self.BCM[18] + self.header.p[11],
            self.BCM[27] + self.header.p[12],
            self.BCM[22] + self.header.p[14],
            self.BCM[23] + self.header.p[15],
            self.BCM[24] + self.header.p[17],
            self.BCM[10] + self.header.p[18],
            self.BCM[9] + self.header.p[20],
            self.BCM[25] + self.header.p[21],
            self.BCM[11] + self.header.p[22],
            self.BCM[8] + self.header.p[23],
            self.BCM[7] + self.header.p[25],
            Net(name="header_p27") + self.header.p[26],
            Net(name="header_p28") + self.header.p[27],
            self.BCM[5] + self.header.p[28],
            self.BCM[6] + self.header.p[30],
            self.BCM[12] + self.header.p[31],
            self.BCM[13] + self.header.p[32],
            self.BCM[19] + self.header.p[34],
            self.BCM[16] + self.header.p[35],
            self.BCM[26] + self.header.p[36],
            self.BCM[20] + self.header.p[37],
            self.BCM[21] + self.header.p[39],
        ]


class RpiPico40PinAdapterCircuit(Circuit):
    # Direct port of `pcb-module rpi-pico-40-pin-adapter` in
    # `jitx/rpi-pico-40-pin-adapter.stanza`, with BCM mapping aligned to the
    # archived KiCad export.
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.pico = RPiPico()
        self.forty_pin = RaspberryPi40PinHeader()

        self.place(self.pico, Placement((0.0, PICO_WIDTH / 2.0 + Y_OFFSET), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.forty_pin, Placement((0.0, -CONNECTORS_SPACING + Y_OFFSET), 270, on=Side.Top))  # ty: ignore[no-matching-overload]

        self.nets = [
            Net(name="GND") + self.gnd + self.pico.gnd + self.forty_pin.gnd,
        ]

        for index in range(2, 28):
            self.nets.append(Net(name=f"BCM-{index}") + self.pico.BCM[index] + self.forty_pin.BCM[index])


class RpiPico40PinAdapterBoard(Board):
    # Collects the Stanza board shape and version-label behavior into Python.
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(Text(f"rpi-pico 40-pin {BOARD_DATE}", 1.5).at(0.0, 0.0), side=FeatureSide.Top)


class RpiPico40PinAdapterDesign(Design):
    # Structural equivalent of `setup-design(...)` +
    # `set-main-module(rpi-pico-40-pin-adapter)`.
    substrate = RpiPico40PinAdapterSubstrate()
    board = RpiPico40PinAdapterBoard()
    circuit = RpiPico40PinAdapterCircuit()
