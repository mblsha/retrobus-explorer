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
        if trefi < 1:
            raise ValueError("Refresh interval must be positive")
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

    original_init = gen.LiteDRAMCore.__init__

    def card_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.crg.cd_sd_io = ClockDomain("sd_io", reset_less=True)
        self.crg.pll.create_clkout(self.crg.cd_sd_io, 100_000_000)
        self.platform.add_extension([("sd_io_clk", 0, Pins(1))])
        self.comb += self.platform.request("sd_io_clk").eq(ClockSignal("sd_io"))
        # BIOS performs PHY training, then Spade qualifies and zeroes all DDR.
        # The initialization CPU stays in ROM/SRAM and never owns card memory.
        self.add_constant("SDRAM_TEST_DISABLE", 1)
        self.add_constant("CONFIG_BIOS_NO_BOOT", 1)
        self.add_constant("CONFIG_BIOS_NO_BUILD_TIME", 1)
        self.add_constant("BIOS_CONSOLE_DISABLE", 1)

    gen.LiteDRAMCore.__init__ = card_init
    from registered_bankmachine import install as install_bank
    from wishbone_pipeline import install as install_cpu_pipeline

    install_bank()
    install_cpu_pipeline()
    gen.main()
