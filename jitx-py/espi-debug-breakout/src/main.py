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

from src.components import JushuoAfa01S10Fca00, PinHeader2x10, SaleaeProbeHeader2x4

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(35.0, 28.0, radius=1.0)
SIGNAL_AREA = rectangle(34.0, 27.0, radius=0.5)
SALEAE_DISTANCE = 13.462


class EspiDebugBreakoutSubstrate(Substrate):
    # Python replacement for the Stanza `setup-design(...)` default stackup.
    stackup = SampleStackup(2)
    constraints = SampleFabConstraints()


class Saleae8(Circuit):
    # Direct port of `components/Saleae/saleae8`.
    gnd = Port()
    data = [Port() for _ in range(8)]

    def __init__(self, *, text_angle: float = 0.0):
        super().__init__()
        self.upper = SaleaeProbeHeader2x4()
        self.lower = SaleaeProbeHeader2x4()

        self.nets = [
            Net(name='GND') + self.gnd + self.upper.GND + self.lower.GND,
            Net(name='ESPI_D0') + self.data[0] + self.lower.p0,
            Net(name='ESPI_D1') + self.data[1] + self.lower.p1,
            Net(name='ESPI_D2') + self.data[2] + self.lower.p2,
            Net(name='ESPI_D3') + self.data[3] + self.lower.p3,
            Net(name='ESPI_D4') + self.data[4] + self.upper.p0,
            Net(name='ESPI_D5') + self.data[5] + self.upper.p1,
            Net(name='ESPI_D6') + self.data[6] + self.upper.p2,
            Net(name='ESPI_D7') + self.data[7] + self.upper.p3,
        ]

        self.place(self.upper, Placement((0.0, SALEAE_DISTANCE / 2.0), on=Side.Top))
        self.place(self.lower, Placement((0.0, -SALEAE_DISTANCE / 2.0), on=Side.Top))

        for index in range(4):
            offset = 2.54 * index
            self += Silkscreen(Text(str(7 - index), 1.5).at(3.5, SALEAE_DISTANCE / 2.0 + 3.8 - offset, rotate=text_angle), side=FeatureSide.Top)
            self += Silkscreen(Text(str(3 - index), 1.5).at(3.5, -SALEAE_DISTANCE / 2.0 + 3.8 - offset, rotate=text_angle), side=FeatureSide.Top)


class EspiDebugBreakoutCircuit(Circuit):
    # Direct port of `pcb-module espi-debug-breakout-module` in
    # `jitx/espi-debug-breakout.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()
        self.ffc = JushuoAfa01S10Fca00()
        self.saleae = Saleae8(text_angle=90.0)
        self.gpio_header = PinHeader2x10()

        self.nets = [
            Net(name='GND') + self.gnd + self.ffc.p[0] + self.saleae.gnd + self.ffc.p[10] + self.ffc.p[11],
            Net(name='VCC') + self.vcc + self.ffc.p[1],
        ]

        for index in range(8):
            ffc_index = index + 2
            saleae_index = 7 - index
            self.nets.append(Net(name=f'ESPI_D{saleae_index}') + self.ffc.p[ffc_index] + self.saleae.data[saleae_index])

        for index in range(10):
            self.nets.append(Net(name=f'GPIO_SIG_{index}') + self.ffc.p[9 - index] + self.gpio_header.p[index * 2])
            self.nets.append(Net(name=f'GPIO_GND_{index}') + self.gnd + self.gpio_header.p[index * 2 + 1])

        self.place(self.ffc, Placement((0.0, -10.0), 180, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.saleae, Placement((0.0, 0.0), 270, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.gpio_header, Placement((0.0, 10.0), 90, on=Side.Top))  # ty: ignore[no-matching-overload]

        self += Silkscreen(Text('1', 1.0).at(8.5, -10.0), side=FeatureSide.Top)


class EspiDebugBreakoutBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(Text(f'eSPI-Debug-Breakout {BOARD_DATE}', 1.5).at(0.0, 5.0), side=FeatureSide.Top)


class EspiDebugBreakoutDesign(Design):
    substrate = EspiDebugBreakoutSubstrate()
    board = EspiDebugBreakoutBoard()
    circuit = EspiDebugBreakoutCircuit()
