"""Exercise native data through the controller and upstream DFI memory model."""

import random
import unittest
from unittest.mock import patch
from migen import Module, Signal
from migen.fhdl.specials import Memory
from migen.sim import run_simulation, passive
from litedram.modules import MT41K128M16
from litedram.phy.model import SDRAMPHYModel
from litedram.core import controller
from litedram.core.crossbar import LiteDRAMCrossbar


class SmallMemory(MT41K128M16):
    # Eight rows cover all exercised addresses while keeping simulation bounded.
    nrows = 8


class ControllerDataTests(unittest.TestCase):
    def exercise(
        self,
        short_buffered=False,
        registered_bank=False,
        continuous=False,
        depth=None,
    ):
        from registered_bankmachine import make_bankmachine

        dut = Module()
        module = SmallMemory(83_333_333, "1:4")
        module.geom_settings.addressbits = max(11, module.geom_settings.addressbits)
        dut.submodules.phy = phy = SDRAMPHYModel(
            module, data_width=16, clk_freq=83_333_333
        )
        settings = controller.ControllerSettings(
            cmd_buffer_depth=depth
            if depth is not None
            else (4 if short_buffered else 16),
            cmd_buffer_buffered=short_buffered,
            with_auto_precharge=True,
        )
        cls = make_bankmachine() if registered_bank else controller.BankMachine
        with patch.object(controller, "BankMachine", cls):
            dut.submodules.control = control = controller.LiteDRAMController(
                phy.settings,
                module.geom_settings,
                module.timing_settings,
                83_333_333,
                controller_settings=settings,
            )
        dut.comb += control.dfi.connect(phy.dfi)
        dut.submodules.crossbar = crossbar = LiteDRAMCrossbar(control.interface)
        port = crossbar.get_port()

        submitted_commands = []
        accepted_commands = []

        def command(address, write):
            submitted_commands.append((address, write))
            yield port.cmd.addr.eq(address)
            yield port.cmd.we.eq(write)
            yield port.cmd.valid.eq(1)
            yield
            for _ in range(2000):
                if (yield port.cmd.ready):
                    break
                yield
            else:
                self.fail("command timeout")
            yield port.cmd.valid.eq(0)
            yield

        trace = []

        @passive
        def monitor():
            cycle = 0
            while True:
                yield
                cycle += 1
                if (yield port.cmd.valid) and (yield port.cmd.ready):
                    accepted_commands.append(
                        ((yield port.cmd.addr), (yield port.cmd.we))
                    )
                if len(trace) < 48:
                    if (yield port.cmd.valid) and (yield port.cmd.ready):
                        trace.append(
                            (
                                cycle,
                                "native-command",
                                (yield port.cmd.addr),
                                (yield port.cmd.we),
                            )
                        )
                    for n, phase in enumerate(control.dfi.phases):
                        if (yield phase.cas_n) == 0 and (yield phase.ras_n) == 1:
                            trace.append(
                                (
                                    cycle,
                                    "dfi",
                                    n,
                                    (yield phase.we_n),
                                    (yield phase.bank),
                                    (yield phase.address),
                                )
                            )
                    if (yield port.wdata.ready):
                        trace.append(
                            (
                                cycle,
                                "write-data",
                                (yield port.wdata.data),
                                (yield port.wdata.we),
                            )
                        )

        def test():
            rng = random.Random(1245)
            expected = {}
            for address in (
                list(range(64)) + [511, 512, 1023, 1024, 2048, 4096]
                if continuous
                else [0, 1, 127, 128, 1023, 1024, 2048, 4096] * 3
            ):
                data = rng.getrandbits(128)
                mask = rng.randrange(1, 65536)
                old = expected.get(address, 0)
                for lane in range(16):
                    if mask >> lane & 1:
                        old = (old & ~(255 << (lane * 8))) | (
                            data & (255 << (lane * 8))
                        )
                expected[address] = old
                yield port.wdata.data.eq(data)
                yield port.wdata.we.eq(mask)
                yield port.wdata.valid.eq(1)
                yield from command(address, 1)
                for _ in range(2000):
                    if (yield port.wdata.ready):
                        break
                    yield
                else:
                    self.fail("write timeout")
                yield
                yield port.wdata.valid.eq(0)
                for _ in range(0 if continuous else 40):
                    yield
            for address, value in expected.items():
                yield from command(address, 0)
                yield port.rdata.ready.eq(1)
                yield
                for _ in range(2000):
                    if (yield port.rdata.valid):
                        self.assertEqual(
                            (yield port.rdata.data),
                            value,
                            (registered_bank, address, trace),
                        )
                        break
                    yield
                else:
                    self.fail("read timeout")
                yield
                yield port.rdata.ready.eq(0)
            self.assertEqual(
                accepted_commands,
                submitted_commands,
                "Each request must be accepted exactly once",
            )

        fragment = dut.get_fragment()
        for special in list(fragment.specials):
            if isinstance(special, Memory):
                for port_ in special.ports:
                    if port_.dat_r is None:
                        port_.dat_r = Signal(special.width)
        run_simulation(fragment, [test(), monitor()])

    def test_continuous_depth2_buffered_registered_bank_data(self):
        self.exercise(
            short_buffered=True, registered_bank=True, continuous=True, depth=2
        )

    def test_continuous_depth1_registered_bank_data(self):
        self.exercise(registered_bank=True, continuous=True, depth=1)

    def test_continuous_unbuffered_upstream_data(self):
        self.exercise(continuous=True)

    def test_continuous_unbuffered_registered_bank_data(self):
        self.exercise(registered_bank=True, continuous=True)

    def test_upstream_data(self):
        self.exercise()

    def test_short_buffered_upstream_data(self):
        self.exercise(short_buffered=True)

    def test_short_buffered_registered_bank_data(self):
        self.exercise(short_buffered=True, registered_bank=True)
