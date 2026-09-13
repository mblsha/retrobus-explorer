from __future__ import annotations

from shared_components.testpads import (
    DEFAULT_PTH_SOLDERMASK_EXPANSION,
    GroundedPthPad,
    gnd_testpads_class,
)


def test_grounded_pth_defaults_to_exposed_annuli_on_both_faces() -> None:
    from jitx._instantiation import instantiation
    from jitx.layerindex import Side
    from pytest import approx

    with instantiation.activate():
        pad = GroundedPthPad(diameter=3.6, hole_diameter=2.2)
    assert DEFAULT_PTH_SOLDERMASK_EXPANSION == 0.05
    assert pad.shape.radius == approx(1.8)
    assert pad.cutout.shape.radius == approx(1.1)
    assert {pad.soldermask_top.side, pad.soldermask_bottom.side} == {Side.Top, Side.Bottom}
    assert pad.soldermask_top.shape.radius == approx(1.85)
    assert pad.soldermask_bottom.shape.radius == approx(1.85)


def test_grounded_corner_component_is_identified_as_ground() -> None:
    component_class = gnd_testpads_class(diameter=3.6, hole_diameter=2.2, width=87.2, height=69.2)
    metadata = vars(component_class)

    assert metadata["value"] == "GND MOUNT"
    assert "two-sided GND markings" in metadata["description"]
