from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from shared_components.metadata import git_revision_date


class GitRevisionDateTests(unittest.TestCase):
    def test_uses_the_repository_commit_date(self) -> None:
        repository = Path("/source/checkout")
        with patch(
            "shared_components.metadata.subprocess.check_output",
            return_value="2026-09-02\n",
        ) as call:
            self.assertEqual(git_revision_date(repository), "2026-09-02")

        call.assert_called_once_with(
            ["git", "log", "-1", "--format=%cs"],
            cwd=repository,
            stderr=subprocess.DEVNULL,
            text=True,
        )

    def test_is_stable_outside_a_checkout(self) -> None:
        with patch(
            "shared_components.metadata.subprocess.check_output",
            side_effect=subprocess.CalledProcessError(128, "git"),
        ):
            self.assertEqual(git_revision_date("/source/archive"), "UNRELEASED")


if __name__ == "__main__":
    unittest.main()
