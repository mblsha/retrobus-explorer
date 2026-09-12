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


class JlcpcbFabricationTests(unittest.TestCase):
    def test_two_layer_trace_rules_match_regular_one_ounce_capability(self) -> None:
        constraints = fabrication.JlcpcbTwoLayerFabConstraints()

        self.assertEqual(constraints.min_copper_width, 0.10)
        self.assertEqual(constraints.min_copper_copper_space, 0.10)
        self.assertEqual(constraints.min_th_pad_expand_outer, 0.18)

    def test_thin_two_layer_stackup_is_nominally_0_8_mm_before_soldermask(self) -> None:
        stackup = fabrication.JlcpcbTwoLayer08Stackup()

        self.assertEqual(stackup.name, "JLCPCB 2-layer 0.8 mm, 1 oz")
        self.assertEqual([layer.name for layer in stackup.layers], ["Top", "Core", "Bottom"])
        self.assertAlmostEqual(sum(layer.thickness for layer in stackup.layers), 0.8)
        self.assertEqual([layer.thickness for layer in stackup.conductors], [0.035, 0.035])


if __name__ == "__main__":
    unittest.main()
