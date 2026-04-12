from __future__ import annotations

from collections.abc import Sequence

from jitx.circuit import Circuit
from jitx.component import Component
from jitx.feature import Courtyard, Paste, Silkscreen, Soldermask
from jitx.landpattern import Landpattern, Pad, PadMapping
from jitx.layerindex import Side as FeatureSide
from jitx.net import Net, Port
from jitx.placement import Placement, Side
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Circle, Polyline, Text
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

DEFAULT_RETROBUS_GND_PINS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55)


def connect_ports(name: str | None, *ports: Port) -> Net:
    net = Net(name=name) if name is not None else Net()
    for port in ports:
        net = net + port
    return net


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


class HDGC60PinFfcLandpattern(Landpattern):
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


class RetroBus60FfcConnector(Circuit):
    VCC5V = Port()
    GND = Port()
    data = [Port() for _ in range(48)]

    def __init__(self, *, flip_pins: bool = False, gnd_pins: Sequence[int] = DEFAULT_RETROBUS_GND_PINS):
        super().__init__()
        self.connector = HDGC60PinFfc()
        self.place(self.connector, Placement((0.0, 2.8), on=Side.Top))

        vcc_pin = 60 if flip_pins else 1
        self.nets = [connect_ports(None, self.VCC5V, self.connector.p[vcc_pin - 1])]
        for pin in gnd_pins:
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(connect_ports(None, self.GND, self.connector.p[mapped_pin - 1]))

        data_index = 0
        for pin in range(2, 61):
            if pin in gnd_pins:
                continue
            mapped_pin = 60 - pin + 1 if flip_pins else pin
            self.nets.append(connect_ports(None, self.data[data_index], self.connector.p[mapped_pin - 1]))
            data_index += 1

        marker_x = (-18.0 + 1.5) if flip_pins else (18.0 - 1.5)
        self += Silkscreen(Circle(diameter=1.0).at(marker_x, 0.0), side=FeatureSide.Top)
