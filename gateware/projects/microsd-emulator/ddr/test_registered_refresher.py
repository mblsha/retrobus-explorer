import unittest
from types import SimpleNamespace as NS
from migen.sim import run_simulation
from litedram.core.refresher import Refresher
from registered_refresher import make_refresher


class RefresherTests(unittest.TestCase):
    def exercise(self, cls, calibration):
        settings = NS(
            geom=NS(addressbits=14, bankbits=3),
            phy=NS(nranks=1),
            timing=NS(tREFI=120, tRP=2, tRFC=8, tZQCS=8 if calibration else None),
            with_refresh=True,
        )
        dut = cls(settings, 12000, zqcs_freq=1000)
        commands = []

        def process():
            ready_count = 0
            completions = 0
            last_precharge = -100
            last_refresh = -100
            for cycle in range(1600):
                if (yield dut.cmd.valid):
                    ready_count += 1
                else:
                    ready_count = 0
                yield dut.cmd.ready.eq(ready_count >= 3)
                yield
                if (yield dut.cmd.valid) and (yield dut.cmd.ready):
                    ras, cas, we = (
                        (yield dut.cmd.ras),
                        (yield dut.cmd.cas),
                        (yield dut.cmd.we),
                    )
                    if ras or cas or we:
                        commands.append((ras, cas, we, (yield dut.cmd.a)))
                        if ras and we and not cas:
                            last_precharge = cycle
                        if ras and cas and not we:
                            self.assertGreaterEqual(cycle - last_precharge, 2)
                            last_refresh = cycle
                if (yield dut.cmd.last):
                    self.assertGreaterEqual(cycle - last_refresh, 8)
                    completions += 1
                    if completions == 8:
                        return
            self.fail("refresh stream did not complete")

        run_simulation(dut, process())
        return commands

    def test_command_sequence_with_and_without_calibration(self):
        for calibration in (False, True):
            with self.subTest(calibration=calibration):
                self.assertEqual(
                    self.exercise(Refresher, calibration),
                    self.exercise(make_refresher(), calibration),
                )


if __name__ == "__main__":
    unittest.main()
