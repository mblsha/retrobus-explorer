"""Run the initialization CPU at 50 MHz while DDR stays at 83.333 MHz."""

from migen import ClockDomain, ClockDomainsRenamer, Signal, ResetSignal
from migen.genlib.cdc import MultiReg
from litex.soc.interconnect import wishbone
from cpu_mailbox import CPUMailbox


def install(generator):
    crg_class = generator.LiteDRAMS7DDRPHYCRG
    original_crg = crg_class.__init__

    def crg_init(self, platform, config):
        original_crg(self, platform, config)
        self.cd_bios = ClockDomain("bios")
        self.pll.create_clkout(self.cd_bios, 50e6)

    crg_class.__init__ = crg_init

    from litex.soc.cores.cpu.vexriscv.core import VexRiscv

    original_cpu = VexRiscv.__init__

    def cpu_init(self, *args, **kwargs):
        original_cpu(self, *args, **kwargs)
        interrupts = Signal(32)
        reset = Signal()
        self.specials += MultiReg(self.interrupt, interrupts)
        self.specials += MultiReg(self.reset, reset)
        self.cpu_params["i_externalInterruptArray"] = interrupts
        self.cpu_params["i_reset"] = ResetSignal() | reset
        ClockDomainsRenamer("bios")(self)

    VexRiscv.__init__ = cpu_init

    from litex.soc.integration.soc import SoCBusHandler

    original_master = SoCBusHandler.add_master

    def add_master(self, name=None, master=None, region=None):
        if name and name.startswith("cpu_bus"):
            assert isinstance(master, wishbone.Interface)
            target = wishbone.Interface(
                data_width=master.data_width,
                adr_width=len(master.adr),
                addressing=master.addressing,
            )
            bridge = CPUMailbox(
                master, target, cd_from="bios", cd_to="sys"
            )
            setattr(self.submodules, name + "_cdc", bridge)
            master = target
        return original_master(self, name=name, master=master, region=region)

    SoCBusHandler.add_master = add_master
