from __future__ import annotations

from jitx.component import Component
from jitx.feature import Courtyard, Cutout, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitx.toleranced import Toleranced
from jitxlib.landpatterns.generators.header import Header
from jitxlib.landpatterns.leads import THLead
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SmallRectSmdPad(Pad):
    shape = rectangle(0.3, 1.25)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(0.4, 1.35))
        self.paste = Paste(rectangle(0.4, 1.35))


class LargeRectSmdPad(Pad):
    shape = rectangle(2.0, 2.5)

    def __init__(self):
        self.soldermask = Soldermask(rectangle(2.1, 2.6))
        self.paste = Paste(rectangle(2.1, 2.6))


class SmdRoundPad1mm(Pad):
    shape = Circle(diameter=1.0)

    def __init__(self):
        self.soldermask = Soldermask(Circle(diameter=1.1))


class ProbePthPad3mm(Pad):
    shape = Circle(diameter=3.0)

    def __init__(self):
        self.cutout = Cutout(Circle(diameter=1.5))
        self.soldermask = Soldermask(Circle(diameter=2.9))


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


class GndTestpads(Component):
    # Direct port of `components/GndTestpads.stanza`: one centered component
    # that exposes four large corner probe holes tied to a shared GND port.
    GND = Port()
    reference_designator_prefix = "TP"
    value = "~"

    def __init__(self, *, diameter: float, width: float, height: float):
        class _Landpattern(Landpattern):
            p1 = ProbePthPad3mm().at(width / 2.0 - diameter, height / 2.0 - diameter)
            p2 = ProbePthPad3mm().at(width / 2.0 - diameter, -height / 2.0 + diameter)
            p3 = ProbePthPad3mm().at(-width / 2.0 + diameter, height / 2.0 - diameter)
            p4 = ProbePthPad3mm().at(-width / 2.0 + diameter, -height / 2.0 + diameter)

        self.landpattern = _Landpattern()
        self.symbol = BoxSymbol(rows=[Row(left=PinGroup([self.GND]))], config=BoxConfig())
        self.pad_mapping = PadMapping({
            self.GND: [
                self.landpattern.p1,
                self.landpattern.p2,
                self.landpattern.p3,
                self.landpattern.p4,
            ]
        })


class HDGC60PinFfcLandpattern(Landpattern):
    # Footprint-level port of `components/_0_5K-1_2X-60PWB.stanza`.
    def __init__(self):
        self.signal_pads = [SmallRectSmdPad().at(14.75 - 0.5 * index, -2.096, rotate=180) for index in range(60)]
        self.mount_pad_left = LargeRectSmdPad().at(-16.43, 0.527, rotate=180)
        self.mount_pad_right = LargeRectSmdPad().at(16.43, 0.527, rotate=180)

        self.ref_text = Silkscreen(Text(">REF", 0.5).at(-0.75, 4.477))
        self.top_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (18.041, 2.644), (18.041, 1.247)]))
        self.left_outline = Silkscreen(Polyline(0.254, [(-18.041, 2.644), (-18.041, 1.247), (-17.661, 1.247)]))
        self.right_outline = Silkscreen(Polyline(0.254, [(17.661, 1.247), (18.041, 1.247)]))
        self.lower_left = Silkscreen(Polyline(0.254, [(-17.406, -0.954), (-17.406, -1.547), (-15.131, -1.547)]))
        self.lower_right = Silkscreen(Polyline(0.254, [(15.131, -1.547), (17.406, -1.547), (17.406, -0.954)]))
        self.courtyard = Courtyard(rectangle(36.336, 5.543))


class HDGC60PinFfc(Component):
    # Raw connector component port of `components/_0_5K-1_2X-60PWB.stanza`.
    p = [Port() for _ in range(62)]

    manufacturer = "HDGC"
    mpn = "0.5K-1.2X-60PWB"
    datasheet = "https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/2111151930_HDGC-0-5K-1-2X-60PWB_C2919552.pdf"
    description = "60-pin 0.5 mm bottom-contact FFC/FPC connector"
    reference_designator_prefix = "J"
    value = "0.5K-1.2X-60PWB"

    def __init__(self):
        self.landpattern = HDGC60PinFfcLandpattern()
        rows = [Row(left=PinGroup([port])) for port in self.p[:60]]
        rows.append(Row(left=PinGroup([self.p[60]]), right=PinGroup([self.p[61]])))
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))

        mapping = {self.p[i]: self.landpattern.signal_pads[i] for i in range(60)}
        mapping[self.p[60]] = self.landpattern.mount_pad_left
        mapping[self.p[61]] = self.landpattern.mount_pad_right
        self.pad_mapping = PadMapping(mapping)
