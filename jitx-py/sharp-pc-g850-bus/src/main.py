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
from shared_components.ffc import RetroBus60FfcConnector
from shared_components.testpads import GndTestpads

from src.components import PCG850Bus

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(50.0, 21.0, radius=3.0)
SIGNAL_AREA = rectangle(49.0, 20.0, radius=2.5)
BOARD_LABEL_Y = 21.0 / 2.0 - 2.0


class SharpPcG850BusSubstrate(Substrate):
    # Python replacement for the Stanza `setup-design(...)` default stackup.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()

    class StandardThroughVia(Via):
        start_layer = 0
        stop_layer = 3
        diameter = 0.6
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


FFCConnector = RetroBus60FfcConnector


class SharpPcG850BusCircuit(Circuit):
    # Direct port of `jitx/sharp-pc-g850-bus.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()

        self.ffc = FFCConnector(flip_pins=True)
        self.bus = PCG850Bus()
        self.gnd_testpads = GndTestpads(diameter=3.0, width=50.0, height=21.0)

        gnd_net = Net(name="GND-DATA0") + self.gnd + self.ffc.GND + self.bus.GND + self.gnd_testpads.GND
        vcc_net = Net(name="VCC") + self.vcc + self.ffc.VCC5V + self.bus.VCC

        self.nets = [vcc_net]

        data_mapping = [
            ("GND", None),
            ("MREQ", self.bus.MREQ),
            ("M1", self.bus.M1),
            ("IORESET", self.bus.IORESET),
            ("IORQ", self.bus.IORQ),
            ("INT1", self.bus.INT1),
            ("WAIT", self.bus.WAIT),
            ("RD", self.bus.RD),
            ("WR", self.bus.WR),
            ("BNK0", self.bus.BNK0),
            ("BNK1", self.bus.BNK1),
            ("CERAM2", self.bus.CERAM2),
            ("CEROM2", self.bus.CEROM2),
            ("D6", self.bus.D6),
            ("D7", self.bus.D7),
            ("D4", self.bus.D4),
            ("D5", self.bus.D5),
            ("D2", self.bus.D2),
            ("D3", self.bus.D3),
            ("D0", self.bus.D0),
            ("D1", self.bus.D1),
            ("A14", self.bus.A14),
            ("A15", self.bus.A15),
            ("A12", self.bus.A12),
            ("A13", self.bus.A13),
            ("A10", self.bus.A10),
            ("A11", self.bus.A11),
            ("A8", self.bus.A8),
            ("A9", self.bus.A9),
            ("A6", self.bus.A6),
            ("A7", self.bus.A7),
            ("A4", self.bus.A4),
            ("A5", self.bus.A5),
            ("A2", self.bus.A2),
            ("A3", self.bus.A3),
            ("A0", self.bus.A0),
            ("A1", self.bus.A1),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
            ("GND", None),
        ]

        for index, (name, port) in enumerate(data_mapping):
            if name == "GND":
                gnd_net += self.ffc.data[index]
            else:
                self.nets.append(Net(name=f"{name}-DATA{index}") + port + self.ffc.data[index])

        self.nets.append(gnd_net)

        self.place(self.ffc, Placement((1.5, 1.0), on=Side.Top))
        self.place(self.bus, Placement((-1.0, -5.0), on=Side.Top))
        self.place(self.gnd_testpads, Placement((0.0, 0.0), on=Side.Top))


class SharpPcG850BusBoard(Board):
    # Collects the Stanza board-shape and version-label behavior into Python.
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(
        Text(f"SHARP PC-G850 adapter v4 (c) mblsha {BOARD_DATE}", 1.5).at(0.0, BOARD_LABEL_Y),
        side=FeatureSide.Top,
    )


class SharpPcG850BusDesign(Design):
    # Structural equivalent of `setup-design(...)` + `set-main-module(module)`
    # in `jitx/sharp-pc-g850-bus.stanza`.
    substrate = SharpPcG850BusSubstrate()
    board = SharpPcG850BusBoard()
    circuit = SharpPcG850BusCircuit()
