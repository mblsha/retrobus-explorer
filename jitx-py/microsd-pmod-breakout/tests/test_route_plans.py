import json
from pathlib import Path

import pytest


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
    assert {pair["segment_id"] for pair in pairs} == {
        "sd-dat2",
        "sd-dat3",
        "sd-cmd",
        "sd-clk",
        "sd-dat0",
        "sd-dat1",
    }


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


def test_power_is_never_routed_to_pmod() -> None:
    for name in (
        "microsd-pmod-emulator-signals.route-plan.json",
        "microsd-pmod-emulator-top-header-signals.route-plan.json",
    ):
        text = json.dumps(load_plan(name))
        assert "card.VDD" not in text
        assert "sd-vdd" not in text
        assert "pmod-vcc" not in text
