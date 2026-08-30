from __future__ import annotations

import unittest

from project_inventory import GATEWARE_ROOT
from project_inventory import ci_project_paths
from project_inventory import load_registry
from project_inventory import validate_project_inventory
from project_inventory import workspace_members
from web_wave_server import list_projects


EXPECTED_PATHS = (
    "projects/ft-uart-hex-bridge",
    "projects/pin-tester",
    "projects/sharp-organizer-card",
    "projects/sharp-pc-e500-card",
    "projects/sharp-pc-g850-bus",
    "projects/sharp-pc-g850-streaming-rom",
    "projects/test-minimal",
    "projects/uart-saleae-loopback",
    "projects/binary-counter",
    "projects/ws2812b",
)


class ProjectInventoryTest(unittest.TestCase):
    def test_registry_is_the_explicit_source_of_truth(self) -> None:
        projects = load_registry()

        self.assertEqual(tuple(project.path.as_posix() for project in projects), EXPECTED_PATHS)
        self.assertTrue(all(project.ci for project in projects))
        self.assertEqual(
            {project.kind for project in projects},
            {"application", "diagnostic", "example"},
        )
        self.assertTrue(all(not project.path.name.endswith("-spade") for project in projects))

    def test_uv_and_cocotb_entrypoints_cover_every_registered_project(self) -> None:
        self.assertEqual(workspace_members(), tuple(sorted(EXPECTED_PATHS)))
        self.assertEqual(
            tuple(path.relative_to(GATEWARE_ROOT).as_posix() for path in ci_project_paths()),
            EXPECTED_PATHS,
        )
        self.assertEqual(
            tuple(path.relative_to(GATEWARE_ROOT).as_posix() for path in validate_project_inventory()),
            EXPECTED_PATHS,
        )

    def test_wave_server_uses_the_same_registry(self) -> None:
        self.assertEqual(
            tuple(project.path.relative_to(GATEWARE_ROOT).as_posix() for project in list_projects()),
            EXPECTED_PATHS,
        )


if __name__ == "__main__":
    unittest.main()
