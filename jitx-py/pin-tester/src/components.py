from __future__ import annotations

from jitx.component import Component
from jitx.feature import Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.primitive import Circle
from jitx.toleranced import Toleranced
from jitxlib.landpatterns.generators.header import Header
from jitxlib.landpatterns.leads import THLead
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SmdRoundPad1mm(Pad):
    shape = Circle(diameter=1.0)

    def __init__(self):
        self.soldermask = Soldermask(Circle(diameter=1.1))


class PinHeader2x4(Component):
    # Python analogue of the generic `pin-header(4, 2)` used by
    # `pcb-module power-pins` in `jitx/pin-tester.stanza`.
    p = [Port() for _ in range(4)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-2x2-2.54mm-th"
    value = "4X2-pin-header"

    def __init__(self):
        self.landpattern = Header(
            num_leads=4,
            num_rows=2,
            lead=THLead(
                length=Toleranced.exact(3.0),
                width=Toleranced.exact(0.64),
            ),
            pitch=2.54,
        )
        rows = [
            Row(left=PinGroup([self.p[0]]), right=PinGroup([self.p[1]])),
            Row(left=PinGroup([self.p[2]]), right=PinGroup([self.p[3]])),
        ]
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=2))
        self.pad_mapping = PadMapping({
            self.p[0]: self.landpattern.p[1],
            self.p[1]: self.landpattern.p[3],
            self.p[2]: self.landpattern.p[2],
            self.p[3]: self.landpattern.p[4],
        })


class PinHeader2x8(Component):
    # Python analogue of the generic `pin-header(8, 2)` used by
    # `pcb-module test-pins(start-index:Int)` in `jitx/pin-tester.stanza`.
    p = [Port() for _ in range(8)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-4x2-2.54mm-th"
    value = "8X2-pin-header"

    def __init__(self):
        self.landpattern = Header(
            num_leads=8,
            num_rows=2,
            lead=THLead(
                length=Toleranced.exact(3.0),
                width=Toleranced.exact(0.64),
            ),
            pitch=2.54,
        )
        rows = [
            Row(left=PinGroup([self.p[row]]), right=PinGroup([self.p[4 + row]]))
            for row in range(4)
        ]
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=2))
        self.pad_mapping = PadMapping({
            self.p[0]: self.landpattern.p[8],
            self.p[1]: self.landpattern.p[6],
            self.p[2]: self.landpattern.p[4],
            self.p[3]: self.landpattern.p[2],
            self.p[4]: self.landpattern.p[7],
            self.p[5]: self.landpattern.p[5],
            self.p[6]: self.landpattern.p[3],
            self.p[7]: self.landpattern.p[1],
        })


class SignalTestPad(Component):
    # Closest Stanza equivalent: `gen-testpad(1.0)` as used for `tp0` in
    # `jitx/pin-tester.stanza`.
    tp = Port()
    reference_designator_prefix = "TP"
    value = "~"

    def __init__(self):
        class _Landpattern(Landpattern):
            pad = SmdRoundPad1mm().at(0.0, 0.0)

        self.landpattern = _Landpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.tp]))], config=BoxConfig())


