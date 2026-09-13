import json
from pathlib import Path

import pytest

from src.main import BOTTOM_HEADER_SD_TO_PMOD_PIN, TOP_HEADER_SD_TO_PMOD_PIN


def load_plan(name: str) -> dict:
    return json.loads((Path(__file__).parents[1] / "routing" / name).read_text())


@pytest.mark.parametrize(
    ("name", "design"),
    [
        ("microsd-pmod-emulator-signals.route-plan.json", "src.main.MicroSdPmodEmulatorDesign"),
        (
            "microsd-pmod-emulator-top-header-signals.route-plan.json",
            "src.main.MicroSdPmodEmulatorTopHeaderDesign",
        ),
    ],
)
def test_route_plans_target_emulators_and_cover_every_data_signal_once(name: str, design: str) -> None:
    plan = load_plan(name)
    assert plan["design"] == design
    pairs = [
        pair
        for phase in plan["phases"]
        for operation in phase["operations"]
        if operation["type"] == "connect"
        for pair in operation["pairs"]
    ]
    mapping = TOP_HEADER_SD_TO_PMOD_PIN if "top-header" in name else BOTTOM_HEADER_SD_TO_PMOD_PIN
    endpoints = [(pair["from"], pair["to"]) for pair in pairs]
    assert len(endpoints) == 6
    assert len(set(endpoints)) == 6
    assert set(endpoints) == {(f"card.{signal}", f"pmod.p[{pin - 1}]") for signal, pin in mapping.items()}


def test_bottom_plan_routes_directly_on_the_contact_side() -> None:
    plan = load_plan("microsd-pmod-emulator-signals.route-plan.json")
    operations = [operation for phase in plan["phases"] for operation in phase["operations"]]
    assert not any(operation["type"] == "drop-vias" for operation in operations)
    assert all(operation.get("side") == "bottom" for operation in operations if operation["type"] == "connect")


def test_top_plan_routes_directly_to_the_plated_through_hole_pmod_pads() -> None:
    plan = load_plan("microsd-pmod-emulator-top-header-signals.route-plan.json")
    operations = [operation for phase in plan["phases"] for operation in phase["operations"]]
    assert not any(operation["type"] == "drop-vias" for operation in operations)
    assert all(operation.get("side") == "bottom" for operation in operations if operation["type"] == "connect")
