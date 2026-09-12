#!/usr/bin/env python3
"""Run LiteDRAM generation with an equivalent registered refresh-timer flag.

The original combinational zero decode sits on the measured critical path from
the 27-bit ZQCS counter through refresh arbitration to bank command acceptance.
Registering the predicted zero flag preserves every cycle of the original timer.
"""

from migen import Module, Signal, If, ClockSignal, ClockDomain
from litex.build.generic_platform import Pins
from migen.fhdl.bitcontainer import bits_for


class RegisteredRefreshTimer(Module):
    def __init__(self, trefi):
        assert trefi >= 1
        self.wait = Signal()
        self.done = Signal(reset=int(trefi == 1))
        self.count = Signal(bits_for(trefi))
        count = Signal(bits_for(trefi), reset=trefi - 1)
        self.sync += If(
            self.wait & ~self.done, count.eq(count - 1), self.done.eq(count == 1)
        ).Else(count.eq(trefi - 1), self.done.eq(int(trefi == 1)))
        self.comb += self.count.eq(count)


if __name__ == "__main__":
    from litedram.core import refresher

    refresher.RefreshTimer = RegisteredRefreshTimer
    from litedram import gen
    import os

    if (
        os.environ.get("MICROSD_MEMTEST_DEBUG") == "1"
        or os.environ.get("MICROSD_NATIVE_BIST") == "1"
    ):
        original_init = gen.LiteDRAMCore.__init__

        def diagnostic_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            if os.environ.get("MICROSD_FAST_SD") == "1":
                self.crg.cd_sd_io = ClockDomain("sd_io", reset_less=True)
                self.crg.pll.create_clkout(self.crg.cd_sd_io, 100_000_000)
                self.platform.add_extension([("sd_io_clk", 0, Pins(1))])
                self.comb += self.platform.request("sd_io_clk").eq(ClockSignal("sd_io"))
            if os.environ.get("MICROSD_MEMTEST_DEBUG") == "1":
                for category in ("BUS", "ADDR", "DATA"):
                    self.add_constant("MEMTEST_" + category + "_DEBUG", 1)
                self.add_constant("MEMTEST_DEBUG_MAX_ERRORS", 8)
            if os.environ.get("MICROSD_NATIVE_BIST") == "1":
                # PHY training remains in BIOS. Full-region qualification and
                # exclusive port ownership are enforced by Spade afterwards.
                self.add_constant("SDRAM_TEST_DISABLE", 1)
                # Keep CPU execution/data/stack in on-chip ROM/SRAM and stop
                # after training: the native client owns all physical DDR.
                self.add_constant("CONFIG_BIOS_NO_BOOT", 1)
                self.add_constant("CONFIG_BIOS_NO_BUILD_TIME", 1)
                self.add_constant("BIOS_CONSOLE_DISABLE", 1)

        gen.LiteDRAMCore.__init__ = diagnostic_init
    if os.environ.get("MICROSD_CPU_MAILBOX") == "1":
        from cpu_clock_domain import install as install_cpu_clock

        install_cpu_clock(gen)
    if os.environ.get("MICROSD_REGISTERED_BANK") == "1":
        from registered_bankmachine import install as install_bank

        install_bank()
    if (
        os.environ.get("MICROSD_FAST_SD") == "1"
        and os.environ.get("MICROSD_CPU_MAILBOX") != "1"
    ):
        # Keep the initialization CPU's long Wishbone return path from limiting
        # DDR placement when the separate SD domain is present.
        from wishbone_pipeline import install as install_cpu_pipeline

        install_cpu_pipeline()
    gen.main()
