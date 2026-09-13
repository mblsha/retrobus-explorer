"""Deduplication must retain standalone protocol tests under fast parameters."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_microsd_suite as suite


class SuiteSelectionTests(unittest.TestCase):
    def test_extra_only_retains_different_configuration(self):
        for fast in (False, True):
            with self.subTest(fast=fast), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                modules = []

                def run(command, **kwargs):
                    if "--project" in command:
                        project = command[command.index("--project") + 1]
                        modules.append(command[command.index("--test-module") + 1])
                        result = root / project / "test/results.xml"
                        result.parent.mkdir(parents=True, exist_ok=True)
                        result.write_text(
                            '<testsuite><testcase name="stub"/></testsuite>'
                        )

                argv = ["suite", "--extra-only"] + (["--fast-sd"] if fast else [])
                with (
                    patch.object(suite, "GATEWARE", root),
                    patch.object(suite.subprocess, "run", side_effect=run),
                    patch("sys.argv", argv),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    suite.main()
                self.assertNotIn("test_probe", modules)
                self.assertEqual("test_sd" in modules, fast)
                if fast:
                    parameters = json.loads(
                        (
                            root
                            / "build/microsd-tests/sd_frontend-test_sd-parameters.json"
                        ).read_text()
                    )
                    self.assertEqual(parameters["MICROSD_FAST_MODE"], "1")
                    self.assertEqual(parameters["MICROSD_HALF_NS"], "19.9")
