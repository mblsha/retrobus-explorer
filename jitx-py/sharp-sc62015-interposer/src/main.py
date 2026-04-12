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
from shared_components.ffc import RetroBus60FfcConnector
from shared_components.testpads import SignalTestPad

from src.components import Sc62015Interposer

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ['git', 'log', '-1', '--format=%cs'],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(40.0, 50.0, radius=0.0)
SIGNAL_AREA = rectangle(39.0, 49.0, radius=0.0)


class SharpSc62015InterposerSubstrate(Substrate):
    # Python replacement for the Stanza flex setup used for the first rigid-board pass.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()


FFCConnector = RetroBus60FfcConnector


class SharpSc62015InterposerCircuit(Circuit):
    # Direct port of `jitx/sharp-sc62015-interposer.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()
        self.ffc = FFCConnector(flip_pins=False)
        self.cpu = Sc62015Interposer()
        self.tp_gnd = SignalTestPad()
        self.tp_vcc = SignalTestPad()

        self.nets = [
            Net(name='GND') + self.gnd + self.ffc.GND + self.cpu.GND + self.tp_gnd.p,
            Net(name='VCC') + self.vcc + self.ffc.VCC5V + self.tp_vcc.p,
        ]

        data_entries = [
            ('D[0]', self.cpu.D[0]),
            ('D[1]', self.cpu.D[1]),
            ('D[2]', self.cpu.D[2]),
            ('D[3]', self.cpu.D[3]),
            ('D[4]', self.cpu.D[4]),
            ('D[5]', self.cpu.D[5]),
            ('D[6]', self.cpu.D[6]),
            ('D[7]', self.cpu.D[7]),
            ('A[0]', self.cpu.A[0]),
            ('A[1]', self.cpu.A[1]),
            ('A[2]', self.cpu.A[2]),
            ('A[3]', self.cpu.A[3]),
            ('A[4]', self.cpu.A[4]),
            ('A[5]', self.cpu.A[5]),
            ('A[6]', self.cpu.A[6]),
            ('A[7]', self.cpu.A[7]),
            ('A[8]', self.cpu.A[8]),
            ('A[9]', self.cpu.A[9]),
            ('A[10]', self.cpu.A[10]),
            ('A[11]', self.cpu.A[11]),
            ('A[12]', self.cpu.A[12]),
            ('A[13]', self.cpu.A[13]),
            ('A[14]', self.cpu.A[14]),
            ('A[15]', self.cpu.A[15]),
            ('A[16]', self.cpu.A[16]),
            ('A[17]', self.cpu.A[17]),
            ('A[18]', self.cpu.A[18]),
            ('DCLK', self.cpu.DCLK),
            ('OUT', self.cpu.OUT),
            ('CE[7]', self.cpu.CE[7]),
            ('CE[6]', self.cpu.CE[6]),
            ('CE[5]', self.cpu.CE[5]),
            ('CE[4]', self.cpu.CE[4]),
            ('CE[3]', self.cpu.CE[3]),
            ('CE[2]', self.cpu.CE[2]),
            ('CE[1]', self.cpu.CE[1]),
            ('CE[0]', self.cpu.CE[0]),
            ('ACLK', self.cpu.ACLK),
            ('DIS', self.cpu.DIS),
            ('RD', self.cpu.RD),
            ('RXD', self.cpu.RXD),
            ('TXD', self.cpu.TXD),
            ('RESET', self.cpu.RESET),
            ('TEST', self.cpu.TEST),
            ('ON', self.cpu.ON),
            ('WR', self.cpu.WR),
            ('MRQ', self.cpu.MRQ),
            ('GND', self.cpu.GND),
        ]

        for index, (name, port) in enumerate(data_entries):
            self.nets.append(Net(name=f'{name}-DATA{index}') + port + self.ffc.data[index])

        self.place(self.ffc, Placement((0.0, 19.0), on=Side.Top))
        self.place(self.cpu, Placement((-4.5, -12.5), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.tp_gnd, Placement((-17.0, 16.0), on=Side.Top))
        self.place(self.tp_vcc, Placement((17.0, 16.0), on=Side.Top))

        self += Silkscreen(Text('GND', 1.5).at(-17.0, 13.5), side=FeatureSide.Top)
        self += Silkscreen(Text('VCC', 1.5).at(17.0, 13.5), side=FeatureSide.Top)
        self += Silkscreen(Text(f'SC62015 v1 (c) mblsha {BOARD_DATE}', 1.5).at(0.0, 5.0), side=FeatureSide.Top)


class SharpSc62015InterposerBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SharpSc62015InterposerDesign(Design):
    substrate = SharpSc62015InterposerSubstrate()
    board = SharpSc62015InterposerBoard()
    circuit = SharpSc62015InterposerCircuit()
