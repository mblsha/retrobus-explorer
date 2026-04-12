from __future__ import annotations

from jitx.component import Component
from jitx.landpattern import PadMapping
from jitx.net import Port
from jitx.toleranced import Toleranced
from jitxlib.landpatterns.generators.header import Header
from jitxlib.landpatterns.leads import THLead
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class PinHeader1x20(Component):
    # Python analogue of the generic `pin-header(20, 1)` used by
    # `components/RPiPico/module` in `jitx/components/RPiPico.stanza`.
    p = [Port() for _ in range(20)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-20x1-2.54mm-th"
    value = "20X1-pin-header"

    def __init__(self):
        self.landpattern = Header(
            num_leads=20,
            num_rows=1,
            lead=THLead(
                length=Toleranced.exact(3.0),
                width=Toleranced.exact(0.64),
            ),
            pitch=2.54,
        )
        self.symbol = BoxSymbol(
            rows=[Row(left=PinGroup([self.p[index]])) for index in range(20)],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping({self.p[index]: self.landpattern.p[index + 1] for index in range(20)})


class PinHeader2x20(Component):
    # Python analogue of the Raspberry Pi GPIO `2x20` pin header used by
    # `ocdb/components/raspberry-pi/gpio-header/module`.
    p = [Port() for _ in range(40)]
    reference_designator_prefix = "J"
    manufacturer = "Generic"
    mpn = "generic-40x2-2.54mm-th"
    value = "40X2-pin-header"

    def __init__(self):
        self.landpattern = Header(
            num_leads=40,
            num_rows=2,
            lead=THLead(
                length=Toleranced.exact(3.0),
                width=Toleranced.exact(0.64),
            ),
            pitch=2.54,
        )
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.p[2 * index]]), right=PinGroup([self.p[2 * index + 1]]))
                for index in range(20)
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping({
            self.p[2 * row]: self.landpattern.p[2 * row + 2]
            for row in range(20)
        } | {
            self.p[2 * row + 1]: self.landpattern.p[2 * row + 1]
            for row in range(20)
        })
