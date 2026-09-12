import random
import unittest
from types import SimpleNamespace as NS
from migen import Signal
from migen.fhdl.specials import Memory
from migen.sim import run_simulation
from litedram.core.bankmachine import BankMachine
from registered_bankmachine import make_bankmachine


class BankTests(unittest.TestCase):
    def exercise(self, cls, auto_precharge=False, buffered=True):
        settings = NS(
            geom=NS(addressbits=14, bankbits=3, rowbits=14, colbits=10),
            phy=NS(cwl=5, nphases=4),
            timing=NS(tWR=3, tCCD=1, tRC=6, tRAS=4, tRP=2, tRCD=2),
            cmd_buffer_depth=4,
            cmd_buffer_buffered=buffered,
            with_auto_precharge=auto_precharge,
        )
        dut = cls(0, 21, 3, 1, settings)
        requests = [
            ((r << 7) | ((i * 9) & 127), i & 1)
            for i, r in enumerate([0, 0, 1, 1, 0, 3, 3, 0, 0, 7, 4, 4, 7, 0] * 5)
        ]
        commands = []

        def process():
            rng = random.Random(159)
            sent = issued = 0
            active = None
            last_activate = last_precharge = last_write = -100
            refresh_phase = 0
            for cycle in range(6000):
                if issued >= 3 and refresh_phase == 0:
                    refresh_phase = 1
                refresh = refresh_phase in range(1, 6)
                yield dut.refresh_req.eq(refresh)
                yield dut.cmd.ready.eq(rng.randrange(4) != 0)
                yield dut.req.valid.eq(sent < len(requests))
                if sent < len(requests):
                    yield dut.req.addr.eq(requests[sent][0])
                    yield dut.req.we.eq(requests[sent][1])
                yield
                if (yield dut.req.valid) and (yield dut.req.ready):
                    sent += 1
                if refresh_phase and refresh_phase < 6 and (yield dut.refresh_gnt):
                    active = None
                    refresh_phase += 1
                if (yield dut.cmd.valid) and (yield dut.cmd.ready):
                    ras, cas, we = (
                        (yield dut.cmd.ras),
                        (yield dut.cmd.cas),
                        (yield dut.cmd.we),
                    )
                    addr = yield dut.cmd.a
                    commands.append((ras, cas, we, addr))
                    if ras and not cas and not we:
                        self.assertGreaterEqual(cycle - last_precharge, 2)
                        active = addr
                        last_activate = cycle
                    elif ras and not cas and we:
                        self.assertGreaterEqual(cycle - last_activate, 4)
                        self.assertGreaterEqual(cycle - last_write, 6)
                        active = None
                        last_precharge = cycle
                    elif cas:
                        expected, write = requests[issued]
                        self.assertEqual(active, expected >> 7)
                        self.assertEqual(addr & ~(1 << 10), (expected & 127) << 3)
                        self.assertEqual(we, write)
                        self.assertGreaterEqual(cycle - last_activate, 2)
                        self.assertEqual((yield dut.req.wdata_ready), write)
                        self.assertEqual((yield dut.req.rdata_valid), not write)
                        if write:
                            last_write = cycle
                        if addr & (1 << 10):
                            self.assertTrue(auto_precharge)
                            active = None
                            last_precharge = cycle
                        issued += 1
                if issued == len(requests):
                    return
            self.fail("bank command stream did not finish")

        fragment = dut.get_fragment()
        for special in fragment.specials:
            if isinstance(special, Memory):
                for port in special.ports:
                    if port.dat_r is None:
                        port.dat_r = Signal(special.width)
        run_simulation(fragment, process())
        return commands

    def test_actual_unbuffered_auto_precharge_configuration(self):
        self.assertEqual(
            self.exercise(BankMachine, auto_precharge=True, buffered=False),
            self.exercise(make_bankmachine(), auto_precharge=True, buffered=False),
        )

    def test_command_sequence_and_minimum_timings(self):
        self.assertEqual(self.exercise(BankMachine), self.exercise(make_bankmachine()))


if __name__ == "__main__":
    unittest.main()
