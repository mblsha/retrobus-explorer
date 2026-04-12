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
from retrobus_jitx_parts.saleae import SaleaeProbeHeader2x4

from src.components import DSLabFemaleHeader2x4

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(25.0, 12.0, radius=1.0)
SIGNAL_AREA = rectangle(24.0, 11.0, radius=0.5)
SALEAE_DISTANCE = 13.462
LABEL_Y = 12.0 / 2.0 - 2.0
OFFSET_Y = -2.5


class SaleaeDslabAdapterSubstrate(Substrate):
    # Python replacement for the Stanza `setup-design(...)` default stackup.
    stackup = SampleStackup(4)
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
            Net(name="GND") + self.gnd + self.upper.GND + self.lower.GND,
            Net(name="SALEAE0") + self.data[0] + self.lower.p0,
            Net(name="SALEAE1") + self.data[1] + self.lower.p1,
            Net(name="SALEAE2") + self.data[2] + self.lower.p2,
            Net(name="SALEAE3") + self.data[3] + self.lower.p3,
            Net(name="SALEAE4") + self.data[4] + self.upper.p0,
            Net(name="SALEAE5") + self.data[5] + self.upper.p1,
            Net(name="SALEAE6") + self.data[6] + self.upper.p2,
            Net(name="SALEAE7") + self.data[7] + self.upper.p3,
        ]

        self.place(self.upper, Placement((0.0, SALEAE_DISTANCE / 2.0), on=Side.Top))
        self.place(self.lower, Placement((0.0, -SALEAE_DISTANCE / 2.0), on=Side.Top))

        for index in range(4):
            offset = 2.54 * index
            self += Silkscreen(Text(str(7 - index), 1.5).at(3.5, SALEAE_DISTANCE / 2.0 + 3.8 - offset, rotate=text_angle), side=FeatureSide.Top)
            self += Silkscreen(Text(str(3 - index), 1.5).at(3.5, -SALEAE_DISTANCE / 2.0 + 3.8 - offset, rotate=text_angle), side=FeatureSide.Top)


class SaleaeDslabAdapterCircuit(Circuit):
    # Direct port of `pcb-module saleae-dslab-adapter` in
    # `jitx/saleae-dslab-adapter.stanza`.
    gnd = Port()

    def __init__(self):
        super().__init__()
        self.saleae = Saleae8(text_angle=270.0)
        self.left = DSLabFemaleHeader2x4()
        self.right = DSLabFemaleHeader2x4()

        self.nets = [
            Net(name="GND") + self.gnd + self.saleae.gnd + self.left.GND + self.right.GND,
            Net(name="SALEAE0") + self.left.p0 + self.saleae.data[0],
            Net(name="SALEAE1") + self.left.p1 + self.saleae.data[1],
            Net(name="SALEAE2") + self.left.p2 + self.saleae.data[2],
            Net(name="SALEAE3") + self.left.p3 + self.saleae.data[3],
            Net(name="SALEAE4") + self.right.p0 + self.saleae.data[4],
            Net(name="SALEAE5") + self.right.p1 + self.saleae.data[5],
            Net(name="SALEAE6") + self.right.p2 + self.saleae.data[6],
            Net(name="SALEAE7") + self.right.p3 + self.saleae.data[7],
        ]

        self.place(self.saleae, Placement((0.0, OFFSET_Y), 270, on=Side.Bottom))  # ty: ignore[no-matching-overload]
        self.place(self.left, Placement((-6.5, 4.1 + OFFSET_Y), on=Side.Bottom))
        self.place(self.right, Placement((6.5, 4.1 + OFFSET_Y), on=Side.Bottom))


class SaleaeDslabAdapterBoard(Board):
    # Collects the Stanza board shape and version-label behavior into Python.
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(Text(f"saleae-dslab {BOARD_DATE}", 1.5).at(0.0, LABEL_Y), side=FeatureSide.Top)


class SaleaeDslabAdapterDesign(Design):
    # Structural equivalent of `setup-design(...)` +
    # `set-main-module(saleae-dslab-adapter)`.
    substrate = SaleaeDslabAdapterSubstrate()
    board = SaleaeDslabAdapterBoard()
    circuit = SaleaeDslabAdapterCircuit()
