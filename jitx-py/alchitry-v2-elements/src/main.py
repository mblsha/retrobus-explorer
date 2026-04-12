from __future__ import annotations

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.placement import Placement
from jitx.sample import SampleFabConstraints, SampleStackup
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Text
from jitx.substrate import Substrate

from src.components import (
    AlchitryV2BothElement,
    AlchitryV2BottomElement,
    AlchitryV2TopElement,
)

BOARD_SHAPE = rectangle(210.0, 80.0, radius=3.0)
SIGNAL_AREA = rectangle(209.0, 79.0, radius=2.5)
ELEMENT_CENTER_XS = (-65.0, 0.0, 65.0)
ELEMENT_CENTER_Y = 0.0
ELEMENT_WIDTH = 55.0
ELEMENT_HEIGHT = 45.0



def centered_placement(center_x: float, center_y: float) -> Placement:
    return Placement((center_x - ELEMENT_WIDTH / 2.0, center_y + ELEMENT_HEIGHT / 2.0))


class AlchitryV2ElementsSubstrate(Substrate):
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()


class AlchitryV2ElementsCircuit(Circuit):
    def __init__(self):
        super().__init__()
        self.top = AlchitryV2TopElement()
        self.bottom = AlchitryV2BottomElement()
        self.both = AlchitryV2BothElement()

        self.place(self.top, centered_placement(ELEMENT_CENTER_XS[0], ELEMENT_CENTER_Y))
        self.place(self.bottom, centered_placement(ELEMENT_CENTER_XS[1], ELEMENT_CENTER_Y))
        self.place(self.both, centered_placement(ELEMENT_CENTER_XS[2], ELEMENT_CENTER_Y))

        for x, label in zip(ELEMENT_CENTER_XS, ("V2_TOP", "V2_BOTTOM", "V2_BOTH"), strict=True):
            self += Silkscreen(Text(label, 2.0).at(x, 31.0), side=FeatureSide.Top)


class AlchitryV2ElementsBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class AlchitryV2ElementsDemoDesign(Design):
    substrate = AlchitryV2ElementsSubstrate()
    board = AlchitryV2ElementsBoard()
    circuit = AlchitryV2ElementsCircuit()
