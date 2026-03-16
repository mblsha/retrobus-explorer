from jitx.component import Component
from jitx.landpattern import PadMapping
from jitx.net import Port
from jitx.toleranced import Toleranced
from jitxlib.landpatterns.generators.header import Header
from jitxlib.landpatterns.leads import THLead
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row


class SignalGroundHeader2x4(Component):
    GND = Port()
    p0 = Port()
    p1 = Port()
    p2 = Port()
    p3 = Port()

    reference_designator_prefix = "J"

    def __init__(
        self,
        *,
        pitch_mm: float,
        lead_length_mm: float,
        lead_width_mm: float,
        manufacturer: str,
        mpn: str,
        description: str,
    ):
        self.manufacturer = manufacturer
        self.mpn = mpn
        self.description = description
        self.landpattern = Header(
            num_leads=8,
            num_rows=2,
            lead=THLead(
                length=Toleranced.exact(lead_length_mm),
                width=Toleranced.exact(lead_width_mm),
            ),
            pitch=pitch_mm,
        )
        self.symbol = BoxSymbol(
            rows=[
                Row(left=PinGroup([self.GND]), right=PinGroup([self.p3])),
                Row(right=PinGroup([self.p2])),
                Row(right=PinGroup([self.p1])),
                Row(right=PinGroup([self.p0])),
            ],
            config=BoxConfig(group_spacing=2),
        )
        self.pad_mapping = PadMapping(
            {
                self.GND: (
                    self.landpattern.p[1],
                    self.landpattern.p[3],
                    self.landpattern.p[5],
                    self.landpattern.p[7],
                ),
                self.p0: self.landpattern.p[8],
                self.p1: self.landpattern.p[6],
                self.p2: self.landpattern.p[4],
                self.p3: self.landpattern.p[2],
            }
        )


class SaleaeProbeHeader2x4(SignalGroundHeader2x4):
    def __init__(self):
        super().__init__(
            pitch_mm=2.54,
            lead_length_mm=3.0,
            lead_width_mm=0.64,
            manufacturer="Generic",
            mpn="generic-2x4-2.54mm-th",
            description="Generic 2x4 2.54 mm Saleae-compatible probe header",
        )


class DSLabFemaleHeader2x4(SignalGroundHeader2x4):
    def __init__(self):
        super().__init__(
            pitch_mm=1.27,
            lead_length_mm=3.4,
            lead_width_mm=0.7,
            manufacturer="DEALON",
            mpn="DW127R-22-08-34",
            description=(
                "1.27 mm 2x4 female header used by the legacy DSLab adapter "
                "design; migrated with generic header geometry"
            ),
        )
