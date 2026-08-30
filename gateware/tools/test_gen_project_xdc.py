from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from gen_project_xdc import project_constraint_sources
from gen_project_xdc import render_project_xdc
from gen_xdc_from_acf import PIN_LINE_RE
from gen_xdc_from_acf import parse_au_pin_map
from text_filters import strip_comments


TOOLS_DIR = Path(__file__).resolve().parent
GATEWARE_ROOT = TOOLS_DIR.parent
PROJECTS_ROOT = GATEWARE_ROOT / "projects"
GOLDEN_PATH = TOOLS_DIR / "testdata" / "constraint_semantics.json"


def project_path(name: str) -> Path:
    return PROJECTS_ROOT / name


def semantic_commands(xdc: str) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in xdc.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def semantic_digest(commands: tuple[str, ...]) -> str:
    payload = ("\n".join(commands) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


class ProjectXdcGoldenTest(unittest.TestCase):
    def test_every_generated_project_matches_pre_decoupling_semantics(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text())

        for name, expected in golden.items():
            with self.subTest(project=name):
                project = project_path(name)
                generated_commands = semantic_commands(render_project_xdc(project))
                checked_in_commands = semantic_commands(
                    (project / "constraints" / "pins.xdc").read_text()
                )
                self.assertEqual(generated_commands, checked_in_commands)
                self.assertEqual(len(generated_commands), expected["command_count"])
                self.assertEqual(semantic_digest(generated_commands), expected["sha256"])

    def test_generator_sources_do_not_depend_on_legacy_projects_or_submodules(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text())
        forbidden_roots = (
            GATEWARE_ROOT / "pin-tester",
            GATEWARE_ROOT / "sharp-organizer-card",
            GATEWARE_ROOT / "sharp-pc-g850-bus",
            GATEWARE_ROOT / "sharp-pc-g850-streaming-rom",
            GATEWARE_ROOT / "reference" / "Alchitry-Labs-V2",
        )

        for name in golden:
            with self.subTest(project=name):
                for source in project_constraint_sources(project_path(name)):
                    resolved = source.resolve()
                    self.assertTrue(resolved.is_file(), f"missing constraint source: {resolved}")
                    self.assertTrue(
                        resolved.is_relative_to(GATEWARE_ROOT),
                        f"constraint source escapes the repository gateware tree: {resolved}",
                    )
                    self.assertFalse(
                        any(resolved.is_relative_to(root) for root in forbidden_roots),
                        f"constraint source still depends on legacy/vendor checkout: {resolved}",
                    )

    def test_minimal_au_pin_map_exactly_covers_active_symbolic_pins(self) -> None:
        golden = json.loads(GOLDEN_PATH.read_text())
        pin_map_paths: set[Path] = set()
        acf_paths: set[Path] = set()
        for name in golden:
            pin_map, *project_acfs = project_constraint_sources(project_path(name))
            pin_map_paths.add(pin_map)
            acf_paths.update(project_acfs)

        self.assertEqual(
            pin_map_paths,
            {GATEWARE_ROOT / "constraints" / "boards" / "alchitry-au1" / "pins.toml"},
        )
        pin_map = parse_au_pin_map(pin_map_paths.pop())
        referenced_tokens: set[str] = set()
        for acf in acf_paths:
            for line in strip_comments(acf.read_text()).splitlines():
                match = PIN_LINE_RE.search(line)
                if match:
                    referenced_tokens.add(match.group(2))

        self.assertEqual(set(pin_map), referenced_tokens - {"R3", "T3", "T4"})


if __name__ == "__main__":
    unittest.main()
