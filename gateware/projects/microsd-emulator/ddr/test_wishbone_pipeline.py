import random
import unittest
from migen.sim import run_simulation
from litex.soc.interconnect import wishbone
from wishbone_pipeline import WishbonePipeline


class PipelineTests(unittest.TestCase):
    def test_stalls_errors_and_canceled_read(self):
        source = wishbone.Interface()
        dut = WishbonePipeline(source)
        target = dut.target

        def process():
            rng = random.Random(991)
            for i in range(150):
                address = rng.getrandbits(30)
                data = rng.getrandbits(32)
                mask = rng.getrandbits(4)
                write = i & 1
                canceled = i % 11 == 0 and not write
                error = i % 13 == 0
                yield source.adr.eq(address)
                yield source.dat_w.eq(data)
                yield source.sel.eq(mask)
                yield source.we.eq(write)
                yield source.cti.eq(2)
                yield source.cyc.eq(1)
                yield source.stb.eq(1)
                yield
                for _ in range(5):
                    if (yield target.stb):
                        break
                    yield
                else:
                    self.fail("request not forwarded")
                for _ in range(rng.randrange(1, 10)):
                    self.assertEqual((yield target.adr), address)
                    self.assertEqual((yield target.dat_w), data)
                    self.assertEqual((yield target.sel), mask)
                    self.assertEqual((yield target.we), write)
                    self.assertEqual((yield target.cti), 0)
                    self.assertFalse((yield source.ack) or (yield source.err))
                    yield
                if canceled:
                    yield source.cyc.eq(0)
                    yield source.stb.eq(0)
                    yield
                    yield
                    yield source.cyc.eq(1)
                    yield source.stb.eq(1)
                    yield source.adr.eq(address ^ 123)
                result = rng.getrandbits(32)
                yield target.dat_r.eq(result)
                yield target.ack.eq(not error)
                yield target.err.eq(error)
                yield
                yield
                self.assertEqual((yield source.ack), int(not error and not canceled))
                self.assertEqual((yield source.err), int(error and not canceled))
                self.assertEqual((yield source.dat_r), result)
                self.assertFalse((yield target.cyc))
                yield target.ack.eq(0)
                yield target.err.eq(0)
                yield source.cyc.eq(0)
                yield source.stb.eq(0)
                yield
                yield
                self.assertFalse((yield source.ack) or (yield source.err))

        run_simulation(dut, process())


if __name__ == "__main__":
    unittest.main()
