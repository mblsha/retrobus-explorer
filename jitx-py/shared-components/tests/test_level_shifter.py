from jitx._instantiation import instantiation
from jitx.layerindex import Side
from pytest import approx

from shared_components.level_shifter import Cap0402Pad, HeaderPthPad, Txb0108PwrPad


def test_constructed_header_has_copper_drill_and_two_mask_openings():
    with instantiation.activate():
        pad = HeaderPthPad()
    assert pad.shape.radius == approx(0.7)
    assert pad.cutout.shape.radius == approx(0.5)
    assert {pad.soldermask_top.side, pad.soldermask_bottom.side} == {Side.Top, Side.Bottom}
    assert pad.soldermask_top.shape.radius == approx(0.75)
    assert pad.soldermask_bottom.shape.radius == approx(0.75)


def test_constructed_smd_pads_preserve_archived_dimensions():
    for kind, width, height in ((Cap0402Pad, 0.6, 0.280277563773199), (Txb0108PwrPad, 0.364, 1.742)):
        with instantiation.activate():
            pad = kind()
        xs, ys = zip(*pad.shape.elements, strict=False)
        assert max(xs) - min(xs) == approx(width)
        assert max(ys) - min(ys) == approx(height)
        assert pad.soldermask.shape is not None
        assert pad.paste.shape is not None
