"""JLCPCB 0.8 mm two-layer stackup and fabrication constraints.

The values here intentionally replace :mod:`jitx.sample` in production board
projects. JITX documents its sample stackups and constraints as experimental
test fixtures that do not represent a real fabrication process.

Capability source:
https://jlcpcb.com/capabilities/Capabilities?type=1
"""

from __future__ import annotations

from typing import Final

from jitx.stackup import Conductor, Dielectric, Stackup
from jitx.substrate import FabricationConstraints

JLCPCB_CAPABILITIES_URL: Final = "https://jlcpcb.com/capabilities/Capabilities?type=1"
MIN_SILKSCREEN_TEXT_HEIGHT_MM: Final = 1.0


class JlcpcbSoldermask(Dielectric):
    """JLCPCB LPI soldermask at its published minimum 10 µm thickness."""

    material_name = "JLCPCB LPI soldermask"
    thickness = 0.010
    dielectric_coefficient = 3.8


class JlcpcbFr4(Dielectric):
    """Generic JLCPCB rigid FR-4."""

    material_name = "JLCPCB FR-4"


class JlcpcbTwoLayer08Core(JlcpcbFr4):
    """Inferred dielectric thickness for a nominal 0.8 mm, 1 oz PCB."""

    thickness = 0.730
    dielectric_coefficient = 4.5


class JlcpcbOuterCopper1Oz(Conductor):
    """Finished 1 oz outer copper."""

    material_name = "JLCPCB 1 oz outer copper"
    thickness = 0.035


class JlcpcbTwoLayer08Stackup(Stackup):
    """Nominal 0.8 mm two-layer FR-4 for thin card-emulator PCBs."""

    name = "JLCPCB 2-layer 0.8 mm, 1 oz"
    top_surface = JlcpcbSoldermask(name="F.Mask")
    layers = [
        JlcpcbOuterCopper1Oz(name="Top"),
        JlcpcbTwoLayer08Core(name="Core"),
        JlcpcbOuterCopper1Oz(name="Bottom"),
    ]
    bottom_surface = JlcpcbSoldermask(name="B.Mask")


class JlcpcbRigidFabConstraints(FabricationConstraints):
    """Shared current JLCPCB rigid-FR4 limits.

    JITX exposes one generic annular-ring limit for both vias and plated pads,
    while JLCPCB specifies them separately. ``min_annular_ring`` therefore
    represents the absolute 0.25/0.15 mm via capability; the layer-specific
    ``min_th_pad_expand_outer`` captures the stricter plated-pad annular ring.
    """

    min_copper_hole_space = 0.20
    min_copper_edge_space = 0.20
    min_annular_ring = 0.05
    min_drill_diameter = 0.15
    min_silkscreen_width = 0.15
    min_pitch_leaded = 0.35
    min_pitch_bga = 0.35
    min_silk_solder_mask_space = 0.15
    min_silkscreen_text_height = MIN_SILKSCREEN_TEXT_HEIGHT_MM
    solder_mask_registration = 0.0
    min_soldermask_opening = 0.25
    min_soldermask_bridge = 0.10
    min_hole_to_hole = 0.20
    min_pth_pin_solder_clearance = 0.0


class JlcpcbTwoLayerFabConstraints(JlcpcbRigidFabConstraints):
    """JLCPCB two-layer, 1 oz process limits."""

    min_copper_width = 0.10
    min_copper_copper_space = 0.10
    min_th_pad_expand_outer = 0.18
    max_board_width = 670.0
    max_board_height = 600.0
