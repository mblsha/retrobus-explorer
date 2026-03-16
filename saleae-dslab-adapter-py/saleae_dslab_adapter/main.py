from jitx.board import Board
from jitx.circuit import Circuit
from jitx.feature import Silkscreen
from jitx.layerindex import Side
from jitx.net import Port
from jitx.placement import Placement
from jitx.sample import SampleDesign
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Text

from saleae_dslab_adapter.components import DSLabFemaleHeader2x4, SaleaeProbeHeader2x4


class SaleaeConnectorBank(Circuit):
    gnd = Port()
    data = [Port() for _ in range(8)]

    upper = SaleaeProbeHeader2x4()
    lower = SaleaeProbeHeader2x4()

    def __init__(self):
        super().__init__()

        self.nets = [
            self.gnd + self.upper.GND + self.lower.GND,
            # Legacy mapping preserves channels 0-3 on the lower Saleae header.
            self.data[0] + self.lower.p0,
            self.data[1] + self.lower.p1,
            self.data[2] + self.lower.p2,
            self.data[3] + self.lower.p3,
            self.data[4] + self.upper.p0,
            self.data[5] + self.upper.p1,
            self.data[6] + self.upper.p2,
            self.data[7] + self.upper.p3,
        ]

        distance_mm = 13.462
        self.place(self.upper, Placement((0.0, distance_mm / 2.0)))
        self.place(self.lower, Placement((0.0, distance_mm / -2.0)))


class SaleaeDSLabAdapterCircuit(Circuit):
    gnd = Port()

    saleae = SaleaeConnectorBank()
    left = DSLabFemaleHeader2x4()
    right = DSLabFemaleHeader2x4()

    def __init__(self):
        super().__init__()

        self.nets = [
            self.gnd + self.saleae.gnd + self.left.GND + self.right.GND,
            self.saleae.data[0] + self.left.p0,
            self.saleae.data[1] + self.left.p1,
            self.saleae.data[2] + self.left.p2,
            self.saleae.data[3] + self.left.p3,
            self.saleae.data[4] + self.right.p0,
            self.saleae.data[5] + self.right.p1,
            self.saleae.data[6] + self.right.p2,
            self.saleae.data[7] + self.right.p3,
        ]

        offset_y_mm = -2.5
        self.place(
            self.saleae,
            Placement((0.0, offset_y_mm), 270.0, on=Side.Bottom),
        )
        self.place(
            self.left,
            Placement((-6.5, 4.1 + offset_y_mm), on=Side.Bottom),
        )
        self.place(
            self.right,
            Placement((6.5, 4.1 + offset_y_mm), on=Side.Bottom),
        )


class SaleaeDSLabAdapterBoard(Board):
    shape = rectangle(25.0, 12.0, radius=1.0)
    title = Silkscreen(Text("saleae-dslab", 1.2).at(0.0, 4.0))


class SaleaeDSLabAdapter(SampleDesign):
    board = SaleaeDSLabAdapterBoard()
    circuit = SaleaeDSLabAdapterCircuit()
