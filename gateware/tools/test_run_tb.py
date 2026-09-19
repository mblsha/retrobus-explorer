from __future__ import annotations

import fcntl
import tempfile
import unittest
from pathlib import Path

import run_tb
from project_meta import path_libraries
from run_tb import changed_inputs
from run_tb import cocotb_result_failures
from run_tb import failure_excerpts
from run_tb import fingerprint
from run_tb import preserve_failure
from run_tb import project_lock
from run_tb import testbench_environment
from run_tb import testbench_inputs


class CocotbResultFailuresTest(unittest.TestCase):
    def parse(self, body: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.xml"
            path.write_text(body)
            return cocotb_result_failures(path)

    def test_accepts_passing_and_skipped_cases(self) -> None:
        self.assertEqual(
            self.parse(
                """<testsuites><testsuite>
                <testcase classname="m" name="passes" />
                <testcase classname="m" name="skips"><skipped /></testcase>
                </testsuite></testsuites>"""
            ),
            [],
        )

    def test_reports_failures_and_errors(self) -> None:
        self.assertEqual(
            self.parse(
                """<testsuites><testsuite>
                <testcase classname="m" name="fails"><failure message="assertion" /></testcase>
                <testcase classname="m" name="errors"><error>traceback</error></testcase>
                </testsuite></testsuites>"""
            ),
            ["m.fails: assertion", "m.errors: traceback"],
        )

    def test_rejects_an_empty_result_set(self) -> None:
        self.assertEqual(
            self.parse("<testsuites><testsuite /></testsuites>"),
            ["Cocotb reported no test cases"],
        )


# Shaped like the record Cocotb 1.9 writes for a test that raised: the JUnit
# file says only "Test failed with RANDOM_SEED=...", the reason is here.
FAILED_RUN_LOG = """\
HEAD is now at 357c6130 Release v0.17.0
     0.00ns INFO     cocotb.regression                  running reads (1/3)
  1187.50ns INFO     cocotb.regression                  reads passed
  1187.50ns INFO     cocotb.regression                  running probes (2/3)
817925.51ns INFO     cocotb.regression                  probes failed
                                                        Traceback (most recent call last):
                                                          File "test/sd_support.py", line 127, in init
                                                            from build_ddr import SD_CSD, csd_crc7
                                                        ImportError: cannot import name 'SD_CSD' from 'build_ddr'
817925.51ns INFO     cocotb.regression                  running writes (3/3)
900000.00ns INFO     cocotb.regression                  writes passed
                                                        ** TESTS=3 PASS=2 FAIL=1 SKIP=0 **
- :0: Verilog $finish
"""


class FailureExcerptsTest(unittest.TestCase):
    def test_returns_the_failed_record_with_its_traceback(self) -> None:
        (excerpt,) = failure_excerpts(FAILED_RUN_LOG)
        lines = excerpt.splitlines()
        self.assertTrue(lines[0].endswith("probes failed"))
        self.assertEqual(
            lines[-1].strip(), "ImportError: cannot import name 'SD_CSD' from 'build_ddr'"
        )
        self.assertEqual(len(lines), 5)

    def test_a_passing_run_has_no_excerpts(self) -> None:
        passing = FAILED_RUN_LOG.replace("probes failed", "probes passed")
        self.assertEqual(failure_excerpts(passing), [])


class ProjectLockTest(unittest.TestCase):
    def contended(self, project: Path) -> bool:
        with (project / "build" / ".run_tb.lock").open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False

    def test_a_second_run_on_the_project_is_excluded_until_the_first_ends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            with project_lock(project):
                self.assertTrue(self.contended(project))
            self.assertFalse(self.contended(project))

    def test_other_projects_are_not_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp) / "first", Path(tmp) / "second"
            first.mkdir()
            second.mkdir()
            with project_lock(first), project_lock(second):
                self.assertTrue(self.contended(first))


class TestbenchInputsTest(unittest.TestCase):
    def workspace(self, root: Path) -> tuple[Path, Path]:
        project = root / "projects" / "card"
        library = root / "lib" / "shared"
        nested = root / "lib" / "nested"
        tools = root / "tools"
        for directory in (project, library, nested):
            (directory / "src").mkdir(parents=True)
            (directory / "test").mkdir()
        tools.mkdir()
        (project / "swim.toml").write_text(
            'name = "card"\n[libraries]\n'
            'shared = {path = "../../lib/shared"}\n'
            'remote.git = "https://example.invalid/remote.git"\n'
        )
        (library / "swim.toml").write_text(
            'name = "shared"\n[libraries]\nnested = {path = "../nested"}\n'
        )
        (nested / "swim.toml").write_text('name = "nested"\n')
        (project / "src" / "main.spade").write_text("entity main() {}\n")
        (project / "test" / "test_card.py").write_text(
            'import os\nHALF = os.environ.get("CARD_HALF_NS", "500")\n'
        )
        (library / "test" / "support.py").write_text("HELPER = 1\n")
        (nested / "src" / "leaf.spade").write_text("fn leaf() {}\n")
        (tools / "helpers.py").write_text("CONSTANT = 1\n")
        return project, tools

    def test_path_libraries_are_followed_from_the_file_declaring_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project, _ = self.workspace(root)
            self.assertEqual(
                path_libraries(project), [root / "lib" / "shared", root / "lib" / "nested"]
            )

    def test_inputs_cover_the_project_its_libraries_and_the_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project, tools = self.workspace(root)
            names = {str(path.relative_to(root)) for path in testbench_inputs(project, tools)}
            self.assertLessEqual(
                {
                    "projects/card/swim.toml",
                    "projects/card/src/main.spade",
                    "projects/card/test/test_card.py",
                    "lib/shared/test/support.py",
                    "lib/nested/src/leaf.spade",
                    "tools/helpers.py",
                },
                names,
            )

    def test_an_edit_or_a_new_file_during_the_run_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            project, tools = self.workspace(root)
            before = fingerprint(testbench_inputs(project, tools))
            self.assertEqual(
                changed_inputs(before, fingerprint(testbench_inputs(project, tools))), []
            )
            (root / "lib" / "shared" / "test" / "support.py").write_text("HELPER = 2\n")
            (tools / "moved_here.py").write_text("CONSTANT = 1\n")
            self.assertEqual(
                changed_inputs(before, fingerprint(testbench_inputs(project, tools))),
                [root / "lib" / "shared" / "test" / "support.py", tools / "moved_here.py"],
            )

    def test_a_file_that_vanishes_is_a_change_rather_than_a_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, tools = self.workspace(Path(tmp).resolve())
            listed = testbench_inputs(project, tools)
            before = fingerprint(listed)
            (project / "test" / "test_card.py").unlink()
            self.assertEqual(
                changed_inputs(before, fingerprint(listed)),
                [project / "test" / "test_card.py"],
            )

    def test_environment_lists_what_the_testbench_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project, tools = self.workspace(Path(tmp).resolve())
            env = {"CARD_HALF_NS": "41", "TESTCASE": "reads", "HOME": "/nowhere"}
            self.assertEqual(
                testbench_environment(testbench_inputs(project, tools), env),
                {"CARD_HALF_NS": "41", "TESTCASE": "reads"},
            )


class PreserveFailureTest(unittest.TestCase):
    def test_keeps_the_evidence_and_only_the_most_recent_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            records = project / "build" / "run_tb_failures"
            for index in range(run_tb.FAILURE_RECORDS_KEPT + 2):
                (records / f"20000101-0000{index:02d}-old").mkdir(parents=True)
            log = project / "build" / "run_tb.log"
            log.write_text(FAILED_RUN_LOG)
            missing_results = project / "test" / "results.xml"

            record = preserve_failure(project, "test_sd", [log, missing_results], "why\n")

            self.assertEqual((record / "run_tb.log").read_text(), FAILED_RUN_LOG)
            self.assertEqual((record / "provenance.txt").read_text(), "why\n")
            kept = sorted(path.name for path in records.iterdir())
            self.assertEqual(len(kept), run_tb.FAILURE_RECORDS_KEPT)
            self.assertEqual(kept[-1], record.name)
            self.assertNotIn("20000101-000000-old", kept)


if __name__ == "__main__":
    unittest.main()
