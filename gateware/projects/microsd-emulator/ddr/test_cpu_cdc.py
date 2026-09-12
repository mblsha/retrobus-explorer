import random
import unittest
from migen import Module, Signal
from migen.fhdl.specials import Memory
from migen.sim import run_simulation, passive
from litex.soc.interconnect import wishbone
from cpu_mailbox import CPUMailbox


class CPUCrossingTests(unittest.TestCase):
    def test_instruction_and_data_mailboxes_share_real_wishbone_rom(self):
        # Exercise the actual synchronous ROM and arbiter, rather than an
        # artificial delayed-response slave, with concurrent I/D bus traffic.
        dut = Module()
        sources = [wishbone.Interface(), wishbone.Interface()]
        targets = [wishbone.Interface(), wishbone.Interface()]
        for source, target in zip(sources, targets):
            dut.submodules += CPUMailbox(source, target, "bios", "sys")
        rng = random.Random(614)
        image = [rng.getrandbits(32) for _ in range(1024)]
        dut.submodules.rom = rom = wishbone.SRAM(
            4096, read_only=True, init=image, name="boot_rom"
        )
        dut.submodules.bus = wishbone.InterconnectShared(
            targets,
            [(lambda address: address < 1024, rom.bus)],
            register=True,
            timeout_cycles=100,
        )
        done = [False, False]

        def master(index):
            source = sources[index]
            rng = random.Random(311 + index)
            for n in range(512):
                address = n if index == 0 else rng.randrange(1024)
                actual = yield from source.read(address)
                self.assertEqual(actual, image[address], (index, n, address))
                for _ in range(rng.randrange(3)):
                    yield
            done[index] = True

        def watchdog():
            for _ in range(60000):
                if all(done):
                    return
                yield
            self.fail("concurrent CPU ROM reads timed out")

        run_simulation(
            dut,
            {"bios": [master(0), master(1)], "sys": watchdog()},
            clocks={"bios": 20, "sys": 12},
        )

    def test_canceled_reply_and_error(self):
        source, target = wishbone.Interface(), wishbone.Interface()
        dut = CPUMailbox(source, target)

        def process():
            yield source.adr.eq(1)
            yield source.cyc.eq(1)
            yield source.stb.eq(1)
            while not (yield target.cyc):
                yield
            yield source.cyc.eq(0)
            yield source.stb.eq(0)
            for _ in range(3):
                yield
            yield source.adr.eq(2)
            yield source.cyc.eq(1)
            yield source.stb.eq(1)
            yield target.dat_r.eq(123)
            yield target.ack.eq(1)
            for _ in range(2):
                yield
            yield target.ack.eq(0)
            for _ in range(30):
                self.assertFalse((yield source.ack) or (yield source.err))
                if (yield target.cyc) and (yield target.adr) == 2:
                    break
                yield
            else:
                self.fail("new request was not forwarded")
            yield target.err.eq(1)
            for _ in range(2):
                yield
            yield target.err.eq(0)
            for _ in range(30):
                self.assertFalse((yield source.ack))
                if (yield source.err):
                    break
                yield
            else:
                self.fail("error response missing")
            yield source.cyc.eq(0)
            yield source.stb.eq(0)
            yield

        run_simulation(dut, {"bios": process()}, clocks={"bios": 20, "sys": 12})

    def test_masked_writes_and_reads_at_50_and_83_mhz(self):
        dut = Module()
        source, target = wishbone.Interface(), wishbone.Interface()
        dut.submodules.bridge = CPUMailbox(source, target, "bios", "sys")
        memory = {}
        done = [False]

        def master():
            yield source.cti.eq(2)
            rng = random.Random(712)
            expected = {}
            for i in range(100):
                address = i % 17
                value = rng.getrandbits(32)
                mask = rng.randrange(1, 16)
                old = expected.get(address, 0)
                for lane in range(4):
                    if mask & (1 << lane):
                        old = (old & ~(255 << (lane * 8))) | (
                            value & (255 << (lane * 8))
                        )
                expected[address] = old
                yield from source.write(address, value, sel=mask)
                actual = yield from source.read(address)
                self.assertEqual(actual, old)
            self.assertEqual(memory, expected)
            done[0] = True

        @passive
        def slave():
            rng = random.Random(997)
            while True:
                while not ((yield target.cyc) and (yield target.stb)):
                    yield
                self.assertEqual((yield target.cti), 0)
                address = yield target.adr
                value = yield target.dat_w
                mask = yield target.sel
                write = yield target.we
                for _ in range(rng.randrange(1, 15)):
                    self.assertEqual((yield target.adr), address)
                    yield target.dat_r.eq(rng.getrandbits(32))
                    yield
                if write:
                    old = memory.get(address, 0)
                    for lane in range(4):
                        if mask & (1 << lane):
                            old = (old & ~(255 << (lane * 8))) | (
                                value & (255 << (lane * 8))
                            )
                    memory[address] = old
                yield target.dat_r.eq(memory.get(address, 0))
                yield target.ack.eq(1)
                yield
                yield target.ack.eq(0)
                yield target.dat_r.eq(0xDEADBEEF)
                while (yield target.cyc):
                    yield

        def watchdog():
            for _ in range(15000):
                if done[0]:
                    return
                yield
            self.fail("CPU clock crossing timed out")

        # Migen's simulator does not lower write-only RAM ports correctly.
        # Give unused read results a dummy sink in the simulation fragment only.
        fragment = dut.get_fragment()
        for special in fragment.specials:
            if isinstance(special, Memory):
                for port in special.ports:
                    if port.dat_r is None:
                        port.dat_r = Signal(special.width)
        run_simulation(
            fragment,
            {"bios": master(), "sys": [slave(), watchdog()]},
            clocks={"bios": 20, "sys": 12},
        )


if __name__ == "__main__":
    unittest.main()
