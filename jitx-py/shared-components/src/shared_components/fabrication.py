"""JLCPCB rigid-FR4 stackups and fabrication constraints.

The values here intentionally replace :mod:`jitx.sample` in production board
projects. JITX documents its sample stackups and constraints as experimental
test fixtures that do not represent a real fabrication process.

Capability source:
https://jlcpcb.com/capabilities/Capabilities?type=1

Four-layer stackup source (JLC04161H-7628, 1.6 mm):
https://jlcpcb.com/impedance
"""

from __future__ import annotations

from typing import Final

from jitx.shapes.primitive import Text
from jitx.stackup import Conductor, Dielectric, Stackup
from jitx.substrate import FabricationConstraints

JLCPCB_CAPABILITIES_URL: Final = "https://jlcpcb.com/capabilities/Capabilities?type=1"
JLCPCB_STACKUP_URL: Final = "https://jlcpcb.com/impedance"
JLCPCB_STACKUP_NAME: Final = "JLC04161H-7628"
SUPPORTED_JLCPCB_LAYER_COUNTS: Final = (2, 4)
MIN_SILKSCREEN_TEXT_HEIGHT_MM: Final = 1.0


class JlcpcbSoldermask(Dielectric):
    """JLCPCB LPI soldermask at its published minimum 10 µm thickness."""

    material_name = "JLCPCB LPI soldermask"
    thickness = 0.010
    dielectric_coefficient = 3.8


class JlcpcbFr4(Dielectric):
    """Generic JLCPCB rigid FR-4."""

    material_name = "JLCPCB FR-4"


class JlcpcbTwoLayerCore(JlcpcbFr4):
    """Inferred dielectric thickness for a nominal 1.6 mm, 1 oz two-layer PCB."""

    thickness = 1.530
    dielectric_coefficient = 4.5


class JlcpcbTwoLayer08Core(JlcpcbFr4):
    """Inferred dielectric thickness for a nominal 0.8 mm, 1 oz PCB."""

    thickness = 0.730
    dielectric_coefficient = 4.5


class Jlcpcb7628Prepreg(JlcpcbFr4):
    """7628 prepreg from the JLC04161H-7628 controlled stackup."""

    material_name = "JLCPCB 7628 prepreg"
    thickness = 0.2104
    dielectric_coefficient = 4.4


class JlcpcbFourLayerCore(JlcpcbFr4):
    """FR-4 core from the JLC04161H-7628 controlled stackup."""

    material_name = "JLCPCB 1.065 mm FR-4 core"
    thickness = 1.065
    dielectric_coefficient = 4.6


class JlcpcbOuterCopper1Oz(Conductor):
    """Finished 1 oz outer copper."""

    material_name = "JLCPCB 1 oz outer copper"
    thickness = 0.035


class JlcpcbInnerCopperHalfOz(Conductor):
    """Finished 0.5 oz inner copper used by JLCPCB's standard four-layer stackup."""

    material_name = "JLCPCB 0.5 oz inner copper"
    thickness = 0.0152


class JlcpcbTwoLayerStackup(Stackup):
    """Nominal 1.6 mm two-layer FR-4 with finished 1 oz copper."""

    name = "JLCPCB 2-layer 1.6 mm, 1 oz"
    top_surface = JlcpcbSoldermask(name="F.Mask")
    layers = [
        JlcpcbOuterCopper1Oz(name="Top"),
        JlcpcbTwoLayerCore(name="Core"),
        JlcpcbOuterCopper1Oz(name="Bottom"),
    ]
    bottom_surface = JlcpcbSoldermask(name="B.Mask")


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


class JlcpcbFourLayerStackup(Stackup):
    """JLCPCB JLC04161H-7628 1.6 mm four-layer controlled stackup."""

    name = JLCPCB_STACKUP_NAME
    top_surface = JlcpcbSoldermask(name="F.Mask")
    layers = [
        JlcpcbOuterCopper1Oz(name="Top"),
        Jlcpcb7628Prepreg(name="7628 prepreg (top)"),
        JlcpcbInnerCopperHalfOz(name="Inner 1"),
        JlcpcbFourLayerCore(name="Core"),
        JlcpcbInnerCopperHalfOz(name="Inner 2"),
        Jlcpcb7628Prepreg(name="7628 prepreg (bottom)"),
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


class JlcpcbFourLayerFabConstraints(JlcpcbRigidFabConstraints):
    """JLCPCB multilayer, 1 oz outer / 0.5 oz inner process limits."""

    min_copper_width = 0.09
    min_copper_copper_space = 0.09
    min_th_pad_expand_outer = 0.15
    max_board_width = 663.0
    max_board_height = 593.0


def jlcpcb_stackup(layer_count: int) -> Stackup:
    """Return the repository default JLCPCB stackup for 2 or 4 layers."""

    if layer_count == 2:
        return JlcpcbTwoLayerStackup()
    if layer_count == 4:
        return JlcpcbFourLayerStackup()
    raise ValueError(f"Unsupported JLCPCB layer count {layer_count}; expected 2 or 4")


def jlcpcb_fab_constraints(layer_count: int) -> FabricationConstraints:
    """Return matching JLCPCB fabrication constraints for 2 or 4 layers."""

    if layer_count == 2:
        return JlcpcbTwoLayerFabConstraints()
    if layer_count == 4:
        return JlcpcbFourLayerFabConstraints()
    raise ValueError(f"Unsupported JLCPCB layer count {layer_count}; expected 2 or 4")


def silkscreen_text(value: str, size: float = MIN_SILKSCREEN_TEXT_HEIGHT_MM) -> Text:
    """Build text that satisfies the shared rigid-PCB legibility limit."""

    if size < MIN_SILKSCREEN_TEXT_HEIGHT_MM:
        raise ValueError(
            f"silkscreen text height {size} mm is below the "
            f"{MIN_SILKSCREEN_TEXT_HEIGHT_MM} mm minimum legible cap height"
        )
    return Text(value, size)
