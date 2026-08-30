from __future__ import annotations

import re
import unittest
from pathlib import Path

from project_inventory import GATEWARE_ROOT


REPO_ROOT = GATEWARE_ROOT.parent
ACTIVE_ROOTS = (
    GATEWARE_ROOT / "projects",
    GATEWARE_ROOT / "lib",
    GATEWARE_ROOT / "tools",
    GATEWARE_ROOT / "constraints",
    GATEWARE_ROOT / "rtl",
)
LEGACY_ROOTS = (
    GATEWARE_ROOT / "reference",
    GATEWARE_ROOT / "pin-tester",
    GATEWARE_ROOT / ("shared-" + "constraints"),
    GATEWARE_ROOT / "shared-lib",
    GATEWARE_ROOT / "sharp-organizer-card",
    GATEWARE_ROOT / "sharp-pc-g850-bus",
    GATEWARE_ROOT / "sharp-pc-g850-streaming-rom",
    GATEWARE_ROOT / "test-minimal",
)
RETIRED_REPO_PATHS = (
    REPO_ROOT / ".env.example",
    REPO_ROOT / ".github" / "container",
    REPO_ROOT / ".github" / "install-alchitry-labs.sh",
    REPO_ROOT / ".github" / "scripts" / "run-alchitry-tests.sh",
    REPO_ROOT / ".github" / "workflows" / "alchitry-ci.yml",
)
RETIRED_PROJECT_FILES = (
    GATEWARE_ROOT / "projects" / "binary-counter" / "constraints" / "allow_unconstrained.xdc",
    GATEWARE_ROOT / "projects" / "binary-counter" / "cu.pcf",
    GATEWARE_ROOT / "projects" / "sharp-pc-e500-card" / "uv.lock",
)
IGNORED_PARTS = {
    ".cpp-build",
    ".git",
    ".pytest_cache",
    ".venv",
    ".venv-host",
    "__pycache__",
    "build",
}
TEXT_SUFFIXES = {
    "",
    ".acf",
    ".alp",
    ".gitignore",
    ".json",
    ".luc",
    ".md",
    ".py",
    ".sh",
    ".spade",
    ".toml",
    ".v",
    ".xdc",
    ".yaml",
    ".yml",
}


def source_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_PARTS for part in path.parts):
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in {"AGENTS.md", "CLAUDE.md"}:
            yield path


class NoLegacyGatewareTest(unittest.TestCase):
    def test_canonical_live_roots_exist(self) -> None:
        self.assertEqual(
            [root.relative_to(REPO_ROOT).as_posix() for root in ACTIVE_ROOTS if not root.is_dir()],
            [],
        )

    def test_legacy_gateware_and_ci_roots_are_removed(self) -> None:
        existing = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in (*LEGACY_ROOTS, *RETIRED_REPO_PATHS, *RETIRED_PROJECT_FILES)
            if path.exists()
        )
        self.assertEqual(existing, [])

    def test_no_lucid_sources_or_projects_remain_in_gateware(self) -> None:
        legacy = sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in source_files(GATEWARE_ROOT)
            if path.suffix in {".luc", ".alp"}
        )
        self.assertEqual(legacy, [])

    def test_live_tree_does_not_reference_retired_workspace_paths(self) -> None:
        banned = (
            "gateware/" + "reference",
            "spade-" + "projects",
            "shared-" + "constraints",
        )
        offenders: list[str] = []
        for path in source_files(GATEWARE_ROOT):
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            if any(value in text for value in banned):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
        self.assertEqual(sorted(offenders), [])

    def test_no_gateware_submodules_remain(self) -> None:
        gitmodules = (REPO_ROOT / ".gitmodules").read_text()
        self.assertNotIn("gateware/", gitmodules)

    def test_spade_ci_uses_the_canonical_workspace_and_local_test_paths(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "spade-testbenches.yml").read_text()
        self.assertIn("working-directory: gateware", workflow)
        self.assertIn("uses: astral-sh/setup-uv@v10.0.1", workflow)
        self.assertIn('version: "0.12.7"', workflow)
        self.assertIn("uv sync --locked --all-packages", workflow)
        self.assertIn(
            "GATEWARE_PYTHON: ${{ github.workspace }}/gateware/.venv/bin/python",
            workflow,
        )
        self.assertIn('echo "$(dirname "${GATEWARE_PYTHON}")" >> "${GITHUB_PATH}"', workflow)
        self.assertIn('"${GATEWARE_PYTHON}" tools/project_inventory.py --check', workflow)
        self.assertIn("gateware/lib/shared-components/swim.lock", workflow)
        self.assertIn(
            '"${GATEWARE_PYTHON}" -m pytest projects/sharp-pc-e500-card/tests',
            workflow,
        )
        self.assertIn('[sys.executable, "tools/project_inventory.py"]', workflow)
        self.assertNotRegex(workflow, re.compile(r"(?m)^\s*python(?:3)?\s"))
        self.assertNotIn("$(python ", workflow)
        self.assertNotIn("&& python ", workflow)
        self.assertNotIn('["python",', workflow)
        self.assertNotIn("spade" + "forge", workflow.lower())
        self.assertNotIn("spade-" + "projects", workflow)


if __name__ == "__main__":
    unittest.main()
