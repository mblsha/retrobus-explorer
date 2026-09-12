"""Cycle equivalence against pinned LiteDRAM, including early reloads."""

import random
import unittest
from migen import Module
from migen.sim import run_simulation
from litedram.core.refresher import RefreshTimer
from generate_bios import RegisteredRefreshTimer


class TimerTests(unittest.TestCase):
    def test_cycle_equivalence(self):
        for period in (1, 2, 3, 7, 16, 31, 512, 1024):
            with self.subTest(period=period):
                dut = Module()
                dut.submodules.old = old = RefreshTimer(period)
                dut.submodules.new = new = RegisteredRefreshTimer(period)

                def check():
                    rng = random.Random(period)
                    for cycle in range(period * 4 + 500):
                        self.assertEqual((yield old.done), (yield new.done), cycle)
                        self.assertEqual((yield old.count), (yield new.count), cycle)
                        wait = 1 if cycle < period * 3 else int(rng.random() > 0.08)
                        yield old.wait.eq(wait)
                        yield new.wait.eq(wait)
                        yield

                run_simulation(dut, check())


if __name__ == "__main__":
    unittest.main()
