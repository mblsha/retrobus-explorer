"""A single-outstanding registered bridge for the BIOS CPU's Wishbone buses.

Each accepted beat becomes a classic downstream transaction. This deliberately
trades BIOS throughput for bounded combinational paths in both directions.
A canceled upstream read is drained without returning a stale acknowledgement.
"""

from migen import Module, Signal, FSM, If, NextValue, NextState
from litex.soc.interconnect import wishbone


class WishbonePipeline(Module):
    def __init__(self, source):
        self.target = target = wishbone.Interface(
            data_width=source.data_width,
            adr_width=len(source.adr),
            addressing=source.addressing,
        )
        response = Signal(source.data_width)
        error = Signal()
        canceled = Signal()
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act(
            "IDLE",
            If(
                source.cyc & source.stb,
                NextValue(canceled, 0),
                NextValue(target.adr, source.adr),
                NextValue(target.dat_w, source.dat_w),
                NextValue(target.sel, source.sel),
                NextValue(target.we, source.we),
                NextState("BUS"),
            ),
        )
        fsm.act(
            "BUS",
            target.cyc.eq(1),
            target.stb.eq(1),
            If(~source.cyc, NextValue(canceled, 1)),
            If(
                target.ack | target.err,
                NextValue(response, target.dat_r),
                NextValue(error, target.err),
                NextState("RESPONSE"),
            ),
        )
        fsm.act(
            "RESPONSE",
            source.dat_r.eq(response),
            source.ack.eq(source.cyc & ~error & ~canceled),
            source.err.eq(source.cyc & error & ~canceled),
            NextState("IDLE"),
        )
        self.comb += [target.cti.eq(0), target.bte.eq(0)]


def install():
    from litex.soc.integration.soc import SoCBusHandler

    original = SoCBusHandler.add_master

    def add_master(self, name=None, master=None, region=None):
        if name and name.startswith("cpu_bus"):
            assert isinstance(master, wishbone.Interface)
            pipeline = WishbonePipeline(master)
            setattr(self.submodules, name + "_pipeline", pipeline)
            master = pipeline.target
        return original(self, name=name, master=master, region=region)

    SoCBusHandler.add_master = add_master
