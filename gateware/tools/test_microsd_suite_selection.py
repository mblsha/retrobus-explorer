"""Deduplication must retain standalone protocol tests under fast parameters.

`--fast-sd` replaces the profile instead of adding one, so the suites that
cover the native write path must also be run without it; that gap is what let
a default-profile write regression live through twenty commits.
"""

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

    def test_fast_sd_still_covers_the_default_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = []

            def run(command, **kwargs):
                if "--project" in command:
                    project = command[command.index("--project") + 1]
                    modules.append(command[command.index("--test-module") + 1])
                    result = root / project / "test/results.xml"
                    result.parent.mkdir(parents=True, exist_ok=True)
                    result.write_text('<testsuite><testcase name="stub"/></testsuite>')

            with (
                patch.object(suite, "GATEWARE", root),
                patch.object(suite.subprocess, "run", side_effect=run),
                patch("sys.argv", ["suite", "--extra-only", "--fast-sd"]),
                patch.dict("os.environ", {"MICROSD_HALF_NS": "83"}),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                suite.main()
            parameters = root / "build/microsd-tests"
            # The registry already runs sd_frontend/test_sd in the default
            # profile, so --extra-only adds only its fast profile.
            self.assertEqual(modules.count("test_sd"), 1)
            self.assertFalse((parameters / "sd_frontend-test_sd-default-parameters.json").exists())
            for top, module in sorted(suite.BOTH_PROFILES - {("sd_frontend", "test_sd")}):
                self.assertEqual(modules.count(module), 2, module)
                # The second run is the default profile, which is the absence
                # of every knob, not the caller's exported overrides.
                self.assertEqual(
                    json.loads(
                        (parameters / f"{top}-{module}-default-parameters.json")
                        .read_text()
                    ),
                    {},
                )

    def test_full_fast_run_keeps_both_profiles_of_both_cases(self):
        names = [name for name, *_ in suite.planned_runs(fast_sd=True)]
        for top, module in suite.BOTH_PROFILES:
            self.assertIn(f"{top}-{module}", names)
            self.assertIn(f"{top}-{module}-default", names)

    def test_case_selection_runs_only_named_cases_without_host_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = []

            def run(command, **kwargs):
                commands.append(command)
                if "--project" in command:
                    project = command[command.index("--project") + 1]
                    result = root / project / "test/results.xml"
                    result.parent.mkdir(parents=True, exist_ok=True)
                    result.write_text('<testsuite><testcase name="stub"/></testsuite>')

            argv = ["suite", "--extra-only", "--fast-sd", "--case", "sd_frontend-test_sd_write-default"]
            with (
                patch.object(suite, "GATEWARE", root),
                patch.object(suite.subprocess, "run", side_effect=run),
                patch("sys.argv", argv),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                suite.main()
            self.assertEqual(len(commands), 1)
            self.assertIn("test_sd_write", commands[0])
            self.assertTrue((root / "build/microsd-tests/sd_frontend-test_sd_write-default.xml").exists())

    def test_unknown_case_is_rejected(self):
        argv = ["suite", "--extra-only", "--fast-sd", "--case", "sd_frontend-test_sd-default"]
        with (
            patch.object(suite.subprocess, "run") as run,
            patch("sys.argv", argv),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            suite.main()
        run.assert_not_called()
