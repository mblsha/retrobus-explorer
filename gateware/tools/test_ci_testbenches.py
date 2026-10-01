"""The CI matrix must run every testbench exactly once, whatever the weights."""

import tempfile
import textwrap
import unittest
from collections import Counter
from pathlib import Path

import ci_testbenches as ci
import project_inventory
import test_microsd_suite


def write_module(directory, source):
    path = Path(directory) / "test_mod.py"
    path.write_text(textwrap.dedent(source))
    return path


class MatrixTests(unittest.TestCase):
    def test_every_unit_appears_in_exactly_one_job(self):
        scheduled = Counter(unit for job in ci.plan() for unit in job)
        self.assertEqual(set(scheduled.values()), {1})
        expected = {"characterization", "shared-components"}
        for path in project_inventory.ci_project_paths():
            project = Path(path).resolve().relative_to(ci.GATEWARE).as_posix()
            if project not in ci.PROJECT_SHARDS:
                expected.add(f"project:{project}")
        for name, *_ in test_microsd_suite.planned_runs(extra_only=True, fast_sd=True):
            expected.add(f"microsd:{name}")
        unsharded = {unit for unit in scheduled if "@" not in unit}
        self.assertEqual(unsharded, expected)

    def test_shards_cover_each_sharded_project_once(self):
        scheduled = [unit for job in ci.plan() for unit in job]
        for project, count in ci.PROJECT_SHARDS.items():
            shards = sorted(u for u in scheduled if u.startswith(f"project:{project}@"))
            self.assertEqual(len(shards), count, project)
            tests = Counter()
            for unit in shards:
                path, names = ci._project_shard(unit)
                self.assertEqual(path, project)
                tests.update(names)
            discovered = ci.discover_tests(ci.project_test_module(project))
            self.assertEqual(set(tests.values()), {1}, project)
            self.assertEqual(set(tests), set(discovered), project)

    def test_matrix_entries_are_unique_and_nonempty(self):
        include = ci.matrix()["include"]
        self.assertEqual(len({entry["id"] for entry in include}), len(include))
        for entry in include:
            self.assertTrue(entry["units"].split())
            self.assertTrue(entry["label"])


class DiscoveryTests(unittest.TestCase):
    def test_literal_skip_is_left_out_because_testcase_would_run_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = write_module(directory, """
                import cocotb

                @cocotb.test()
                async def first(dut):
                    pass

                @cocotb.test(skip=True)
                async def skipped(dut):
                    pass

                @cocotb.test(skip=False, timeout_time=5)
                async def kept(dut):
                    pass

                async def helper(dut):
                    pass
            """)
            self.assertEqual(ci.discover_tests(path), ["first", "kept"])

    def test_unsafe_modules_refuse_to_shard(self):
        cases = {
            "computed skip": """
                import cocotb
                FAST = True

                @cocotb.test(skip=FAST)
                async def maybe(dut):
                    pass
            """,
            "generated": """
                import cocotb
                from cocotb.regression import TestFactory

                @cocotb.test()
                async def first(dut):
                    pass
            """,
            "undecorated registration": """
                import cocotb

                @cocotb.test()
                async def first(dut):
                    pass

                async def second(dut):
                    pass

                second_test = cocotb.test()(second)
            """,
        }
        for name, source in cases.items():
            with (
                self.subTest(name),
                tempfile.TemporaryDirectory() as directory,
                self.assertRaises(ValueError),
            ):
                ci.discover_tests(write_module(directory, source))

    def test_sharding_balances_by_weight_and_keeps_file_order(self):
        names = ["a", "slow", "b", "c"]
        weights = {"slow": 300}
        original = dict(ci.TEST_SECONDS)
        try:
            ci.TEST_SECONDS.clear()
            ci.TEST_SECONDS.update(weights)
            self.assertEqual(ci.shard_tests(names, 2), [["slow"], ["a", "b", "c"]])
        finally:
            ci.TEST_SECONDS.clear()
            ci.TEST_SECONDS.update(original)


if __name__ == "__main__":
    unittest.main()
