from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from run_tb import cocotb_result_failures


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


if __name__ == "__main__":
    unittest.main()
