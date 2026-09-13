"""JLCPCB two-layer flexible-PCB stackup and fabrication constraints.

This module is deliberately separate from :mod:`shared_components.fabrication`:
FPC copper, polyimide, coverlay, outline, drill, and clearance requirements are
not interchangeable with the rigid-FR4 process.

Capability source:
https://jlcpcb.com/capabilities/flex-pcb-capabilities

Standard 0.11 mm two-layer stackup source:
https://jlcpcb.com/resources/flexible-pcb
"""

from __future__ import annotations

from typing import Final

from jitx.stackup import Conductor, Dielectric, Stackup
from jitx.substrate import FabricationConstraints

JLCPCB_FLEX_CAPABILITIES_URL: Final = "https://jlcpcb.com/capabilities/flex-pcb-capabilities"
JLCPCB_FLEX_STACKUP_URL: Final = "https://jlcpcb.com/resources/flexible-pcb"
JLCPCB_FLEX_STACKUP_NAME: Final = "JLCPCB 2-layer flex 0.11 mm, 1/3 oz"
SUPPORTED_JLCPCB_FLEX_LAYER_COUNTS: Final = (2,)


class JlcpcbFlexCoverlay(Dielectric):
    """12.5 µm PI plus 15 µm adhesive for 1/3 oz flex copper."""

    material_name = "JLCPCB polyimide coverlay and adhesive"
    thickness = 0.0275
    dielectric_coefficient = 2.9


class JlcpcbFlexPolyimideCore(Dielectric):
    """Standard 25 µm polyimide core for a two-layer FPC."""

    material_name = "JLCPCB polyimide flex core"
    thickness = 0.025
    dielectric_coefficient = 3.3


class JlcpcbFlexCopperThirdOz(Conductor):
    """12 µm (approximately 1/3 oz) copper."""

    material_name = "JLCPCB 12 µm flex copper"
    thickness = 0.012


class JlcpcbTwoLayerFlexStackup(Stackup):
    """JLCPCB's standard approximately 0.11 mm two-layer FPC stackup."""

    name = JLCPCB_FLEX_STACKUP_NAME
    top_surface = JlcpcbFlexCoverlay(name="F.Coverlay")
    layers = [
        JlcpcbFlexCopperThirdOz(name="Top"),
        JlcpcbFlexPolyimideCore(name="Core"),
        JlcpcbFlexCopperThirdOz(name="Bottom"),
    ]
    bottom_surface = JlcpcbFlexCoverlay(name="B.Coverlay")


class JlcpcbTwoLayerFlexFabConstraints(FabricationConstraints):
    """Regular JLCPCB limits for a 25 µm-core, 12 µm-copper FPC.

    The 3/3 mil trace rule is JLCPCB's regular capability for 12 µm copper,
    rather than its 2/2 mil extra-cost absolute limit. Via and PTH values also
    use the published regular or recommended limits rather than the extremes.
    ``min_copper_hole_space`` combines the 0.125 mm regular-via annular ring
    with the 0.10 mm minimum clearance from the via ring to another trace.
    JITX calls the physical FPC coverlay "soldermask" in these generic fields.
    """

    min_copper_width = 0.0762
    min_copper_copper_space = 0.0762
    min_copper_hole_space = 0.225
    min_copper_edge_space = 0.30

    min_annular_ring = 0.125
    min_drill_diameter = 0.30
    min_pitch_leaded = 0.35
    min_pitch_bga = 0.35

    max_board_width = 490.0
    max_board_height = 234.0

    min_silkscreen_width = 0.15
    min_silk_solder_mask_space = 0.15
    min_silkscreen_text_height = 1.0
    solder_mask_registration = 0.10
    min_soldermask_opening = 0.25
    min_soldermask_bridge = 0.50

    min_th_pad_expand_outer = 0.25
    min_hole_to_hole = 0.20
    min_pth_pin_solder_clearance = 0.10


def jlcpcb_flex_stackup(layer_count: int = 2) -> Stackup:
    """Return the repository's JLCPCB flexible stackup."""

    if layer_count == 2:
        return JlcpcbTwoLayerFlexStackup()
    raise ValueError(f"Unsupported JLCPCB flex layer count {layer_count}; expected 2")


def jlcpcb_flex_fab_constraints(layer_count: int = 2) -> FabricationConstraints:
    """Return matching JLCPCB flexible-PCB fabrication constraints."""

    if layer_count == 2:
        return JlcpcbTwoLayerFlexFabConstraints()
    raise ValueError(f"Unsupported JLCPCB flex layer count {layer_count}; expected 2")
