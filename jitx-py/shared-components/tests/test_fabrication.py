from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


class FakeLayer:
    def __init__(self, **attributes: object) -> None:
        for name, value in attributes.items():
            setattr(self, name, value)


class FakeConductor(FakeLayer):
    pass


class FakeDielectric(FakeLayer):
    pass


class FakeStackup:
    name = ""
    layers: list[FakeLayer] = []

    def __init__(self) -> None:
        self.name = type(self).name
        self.layers = list(type(self).layers)

    @property
    def conductors(self) -> list[FakeConductor]:
        return [layer for layer in self.layers if isinstance(layer, FakeConductor)]


class FakeFabricationConstraints:
    pass


class FakeText:
    def __init__(self, value: str, size: float) -> None:
        self.value = value
        self.size = size


def load_fabrication_with_mocked_jitx(filename: str) -> ModuleType:
    """Load the production module without importing proprietary JITX behavior."""

    jitx = ModuleType("jitx")
    jitx.__path__ = []  # type: ignore[attr-defined]
    shapes = ModuleType("jitx.shapes")
    shapes.__path__ = []  # type: ignore[attr-defined]
    primitive = ModuleType("jitx.shapes.primitive")
    stackup = ModuleType("jitx.stackup")
    substrate = ModuleType("jitx.substrate")
    module_attributes = (
        (primitive, {"Text": FakeText}),
        (stackup, {"Conductor": FakeConductor, "Dielectric": FakeDielectric, "Stackup": FakeStackup}),
        (substrate, {"FabricationConstraints": FakeFabricationConstraints}),
        (jitx, {"shapes": shapes, "stackup": stackup, "substrate": substrate}),
        (shapes, {"primitive": primitive}),
    )
    for module, attributes in module_attributes:
        for name, value in attributes.items():
            setattr(module, name, value)

    source = Path(__file__).resolve().parents[1] / f"src/shared_components/{filename}.py"
    spec = importlib.util.spec_from_file_location(f"{filename}_under_test", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "jitx": jitx,
            "jitx.shapes": shapes,
            "jitx.shapes.primitive": primitive,
            "jitx.stackup": stackup,
            "jitx.substrate": substrate,
        },
    ):
        spec.loader.exec_module(module)
    return module


fabrication = load_fabrication_with_mocked_jitx("fabrication")
flex_fabrication = load_fabrication_with_mocked_jitx("flex_fabrication")


class JlcpcbFabricationTests(unittest.TestCase):
    def test_two_layer_trace_rules_match_regular_one_ounce_capability(self) -> None:
        constraints = fabrication.JlcpcbTwoLayerFabConstraints()

        self.assertEqual(constraints.min_copper_width, 0.10)
        self.assertEqual(constraints.min_copper_copper_space, 0.10)
        self.assertEqual(constraints.min_th_pad_expand_outer, 0.18)

    def test_four_layer_trace_rules_match_multilayer_capability(self) -> None:
        constraints = fabrication.JlcpcbFourLayerFabConstraints()

        self.assertEqual(constraints.min_copper_width, 0.09)
        self.assertEqual(constraints.min_copper_copper_space, 0.09)
        self.assertEqual(constraints.min_th_pad_expand_outer, 0.15)

    def test_two_layer_stackup_is_nominally_1_6_mm_before_soldermask(self) -> None:
        stackup = fabrication.JlcpcbTwoLayerStackup()

        self.assertEqual([layer.name for layer in stackup.layers], ["Top", "Core", "Bottom"])
        self.assertAlmostEqual(sum(layer.thickness for layer in stackup.layers), 1.6)
        self.assertEqual([layer.thickness for layer in stackup.conductors], [0.035, 0.035])

    def test_four_layer_stackup_matches_jlc04161h_7628(self) -> None:
        stackup = fabrication.JlcpcbFourLayerStackup()

        self.assertEqual(stackup.name, fabrication.JLCPCB_STACKUP_NAME)
        self.assertEqual([layer.thickness for layer in stackup.conductors], [0.035, 0.0152, 0.0152, 0.035])
        self.assertEqual(
            [layer.thickness for layer in stackup.layers],
            [0.035, 0.2104, 0.0152, 1.065, 0.0152, 0.2104, 0.035],
        )

    def test_factories_pair_supported_stackups_and_constraints(self) -> None:
        self.assertIsInstance(fabrication.jlcpcb_stackup(2), fabrication.JlcpcbTwoLayerStackup)
        self.assertIsInstance(fabrication.jlcpcb_stackup(4), fabrication.JlcpcbFourLayerStackup)
        self.assertIsInstance(fabrication.jlcpcb_fab_constraints(2), fabrication.JlcpcbTwoLayerFabConstraints)
        self.assertIsInstance(fabrication.jlcpcb_fab_constraints(4), fabrication.JlcpcbFourLayerFabConstraints)

        with self.assertRaisesRegex(ValueError, "expected 2 or 4"):
            fabrication.jlcpcb_stackup(6)
        with self.assertRaisesRegex(ValueError, "expected 2 or 4"):
            fabrication.jlcpcb_fab_constraints(6)

    def test_silkscreen_text_enforces_legibility_limit(self) -> None:
        label = fabrication.silkscreen_text("READY")

        self.assertEqual(label.value, "READY")
        self.assertEqual(label.size, fabrication.MIN_SILKSCREEN_TEXT_HEIGHT_MM)
        with self.assertRaisesRegex(ValueError, "below the 1.0 mm minimum"):
            fabrication.silkscreen_text("tiny", size=0.9)

    def test_thin_two_layer_stackup_is_nominally_0_8_mm_before_soldermask(self) -> None:
        stackup = fabrication.JlcpcbTwoLayer08Stackup()

        self.assertEqual(stackup.name, "JLCPCB 2-layer 0.8 mm, 1 oz")
        self.assertEqual([layer.name for layer in stackup.layers], ["Top", "Core", "Bottom"])
        self.assertAlmostEqual(sum(layer.thickness for layer in stackup.layers), 0.8)
        self.assertEqual([layer.thickness for layer in stackup.conductors], [0.035, 0.035])


class JlcpcbFlexFabricationTests(unittest.TestCase):
    def test_trace_and_drill_rules_use_regular_flex_capabilities(self) -> None:
        constraints = flex_fabrication.JlcpcbTwoLayerFlexFabConstraints()

        self.assertEqual(constraints.min_copper_width, 0.0762)
        self.assertEqual(constraints.min_copper_copper_space, 0.0762)
        self.assertEqual(constraints.min_copper_edge_space, 0.30)
        self.assertEqual(constraints.min_drill_diameter, 0.30)
        self.assertEqual(constraints.min_annular_ring, 0.125)
        self.assertEqual(constraints.min_th_pad_expand_outer, 0.25)

    def test_coverlay_rules_are_not_rigid_soldermask_rules(self) -> None:
        constraints = flex_fabrication.JlcpcbTwoLayerFlexFabConstraints()

        self.assertEqual(constraints.solder_mask_registration, 0.10)
        self.assertEqual(constraints.min_soldermask_bridge, 0.50)
        self.assertEqual(constraints.min_pth_pin_solder_clearance, 0.10)

    def test_stackup_matches_standard_0_11_mm_two_layer_fpc(self) -> None:
        stackup = flex_fabrication.JlcpcbTwoLayerFlexStackup()

        self.assertEqual(stackup.name, flex_fabrication.JLCPCB_FLEX_STACKUP_NAME)
        self.assertEqual([layer.name for layer in stackup.layers], ["Top", "Core", "Bottom"])
        self.assertEqual([layer.thickness for layer in stackup.conductors], [0.012, 0.012])
        total_thickness = (
            stackup.top_surface.thickness
            + sum(layer.thickness for layer in stackup.layers)
            + stackup.bottom_surface.thickness
        )
        self.assertAlmostEqual(total_thickness, 0.104)
        self.assertEqual(stackup.top_surface.dielectric_coefficient, 2.9)
        self.assertEqual(stackup.layers[1].dielectric_coefficient, 3.3)

    def test_flex_factories_reject_rigid_layer_counts(self) -> None:
        self.assertIsInstance(
            flex_fabrication.jlcpcb_flex_stackup(2),
            flex_fabrication.JlcpcbTwoLayerFlexStackup,
        )
        self.assertIsInstance(
            flex_fabrication.jlcpcb_flex_fab_constraints(2),
            flex_fabrication.JlcpcbTwoLayerFlexFabConstraints,
        )

        with self.assertRaisesRegex(ValueError, "expected 2"):
            flex_fabrication.jlcpcb_flex_stackup(4)
        with self.assertRaisesRegex(ValueError, "expected 2"):
            flex_fabrication.jlcpcb_flex_fab_constraints(4)


if __name__ == "__main__":
    unittest.main()
