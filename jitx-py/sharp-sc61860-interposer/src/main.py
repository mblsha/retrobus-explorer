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
from shared_components.ffc import HDGC60PinFfc
from shared_components.testpads import SignalTestPad

from src.components import Sc61860Interposer

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ['git', 'log', '-1', '--format=%cs'],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(40.0, 50.0, radius=0.0)
SIGNAL_AREA = rectangle(39.0, 49.0, radius=0.0)


class SharpSc61860InterposerSubstrate(Substrate):
    # Python replacement for the Stanza flex setup used for the first rigid-board pass.
    stackup = SampleStackup(4)
    constraints = SampleFabConstraints()


class FFCConnector(Circuit):
    # Board-local port of `components/FFCConnector.stanza`.
    # This interposer uses the second-to-last FFC pin as an extra GND and keeps
    # the last pin as the dangling `DATA47` lane present in the archived KiCad.
    VCC5V = Port()
    GND = Port()
    data = [Port() for _ in range(46)]
    data47 = Port()

    def __init__(self, *, flip_pins: bool = False):
        super().__init__()
        self.connector = HDGC60PinFfc()
        self.place(self.connector, Placement((0.0, 2.8), on=Side.Top))

        vcc_pin = 60 if flip_pins else 1
        gnd_pins = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 59]

        self.nets = [self.VCC5V + self.connector.p[vcc_pin - 1]]
        for pin in gnd_pins:
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(self.GND + self.connector.p[mapped_pin - 1])

        data_index = 0
        for pin in range(2, 61):
            if pin in gnd_pins:
                continue
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            if pin == 60:
                self.nets.append(self.data47 + self.connector.p[mapped_pin - 1])
            else:
                self.nets.append(self.data[data_index] + self.connector.p[mapped_pin - 1])
                data_index += 1

        marker_x = (-18.0 + 1.5) if flip_pins else (18.0 - 1.5)
        self += Silkscreen(Circle(diameter=1.0).at(marker_x, 0.0), side=FeatureSide.Top)


class SharpSc61860InterposerCircuit(Circuit):
    # Direct port of `jitx/sharp-sc61860-interposer.stanza`.
    gnd = Port()
    vcc = Port()

    def __init__(self):
        super().__init__()
        self.ffc = FFCConnector(flip_pins=False)
        self.cpu = Sc61860Interposer()
        self.tp_gnd = SignalTestPad()
        self.tp_vcc = SignalTestPad()

        self.nets = [
            Net(name='GND') + self.gnd + self.ffc.GND + self.cpu.GND + self.tp_gnd.p,
            Net(name='VCC') + self.vcc + self.ffc.VCC5V + self.tp_vcc.p,
        ]

        data_entries = [
            ('IA[7]', self.cpu.IA[7]),
            ('IA[6]', self.cpu.IA[6]),
            ('IA[5]', self.cpu.IA[5]),
            ('IA[4]', self.cpu.IA[4]),
            ('IA[3]', self.cpu.IA[3]),
            ('IA[2]', self.cpu.IA[2]),
            ('IA[1]', self.cpu.IA[1]),
            ('IA[0]', self.cpu.IA[0]),
            ('D[7]', self.cpu.D[7]),
            ('D[6]', self.cpu.D[6]),
            ('D[5]', self.cpu.D[5]),
            ('D[4]', self.cpu.D[4]),
            ('D[3]', self.cpu.D[3]),
            ('D[2]', self.cpu.D[2]),
            ('D[1]', self.cpu.D[1]),
            ('D[0]', self.cpu.D[0]),
            ('FO[4]', self.cpu.FO[4]),
            ('FO[3]', self.cpu.FO[3]),
            ('FO[2]', self.cpu.FO[2]),
            ('FO[1]', self.cpu.FO[1]),
            ('FO[0]', self.cpu.FO[0]),
            ('A[15]', self.cpu.A[15]),
            ('A[14]', self.cpu.A[14]),
            ('A[13]', self.cpu.A[13]),
            ('A[12]', self.cpu.A[12]),
            ('A[11]', self.cpu.A[11]),
            ('A[10]', self.cpu.A[10]),
            ('A[9]', self.cpu.A[9]),
            ('A[8]', self.cpu.A[8]),
            ('A[7]', self.cpu.A[7]),
            ('A[6]', self.cpu.A[6]),
            ('A[5]', self.cpu.A[5]),
            ('A[4]', self.cpu.A[4]),
            ('A[3]', self.cpu.A[3]),
            ('A[2]', self.cpu.A[2]),
            ('A[1]', self.cpu.A[1]),
            ('A[0]', self.cpu.A[0]),
            ('RW', self.cpu.RW),
            ('AL', self.cpu.AL),
            ('TEST', self.cpu.TEST),
            ('OSC_O', self.cpu.OSC_O),
            ('RESET', self.cpu.RESET),
            ('XIN', self.cpu.XIN),
            ('KON', self.cpu.KON),
            ('XOUT', self.cpu.XOUT),
            ('DIS', self.cpu.DIS),
        ]

        for index, (name, port) in enumerate(data_entries):
            self.nets.append(Net(name=f'{name}-DATA{index}') + port + self.ffc.data[index])
        self.nets.append(Net(name='DATA47') + self.ffc.data47)

        self.place(self.ffc, Placement((0.0, 19.0), on=Side.Top))
        self.place(self.cpu, Placement((4.0, -12.0), 90, on=Side.Top))  # ty: ignore[no-matching-overload]
        self.place(self.tp_gnd, Placement((-17.0, 16.0), on=Side.Top))
        self.place(self.tp_vcc, Placement((17.0, 16.0), on=Side.Top))

        self += Silkscreen(Text('GND', 1.5).at(-17.0, 13.5), side=FeatureSide.Top)
        self += Silkscreen(Text('VCC', 1.5).at(17.0, 13.5), side=FeatureSide.Top)
        self += Silkscreen(Text(f'SC61860 v1 (c) mblsha {BOARD_DATE}', 1.5).at(0.0, 5.0), side=FeatureSide.Top)


class SharpSc61860InterposerBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class SharpSc61860InterposerDesign(Design):
    substrate = SharpSc61860InterposerSubstrate()
    board = SharpSc61860InterposerBoard()
    circuit = SharpSc61860InterposerCircuit()
