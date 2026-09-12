"""Single-outstanding Wishbone mailbox across the initialization CPU clocks.

Payload registers stay stable until a synchronized toggle acknowledgement.
Only toggles cross synchronizers; there is no dual-clock FIFO RAM.
Each destination access is a classic cycle, regardless of source burst hints.
"""

from migen import (
    Module,
    Signal,
    Record,
    If,
    ClockDomainsRenamer,
    FSM,
    NextState,
    NextValue,
)
from migen.genlib.cdc import MultiReg


class CPUMailbox(Module):
    def __init__(self, source, target, cd_from="bios", cd_to="sys"):
        request = Record(
            [
                (n, len(getattr(source, n)))
                for n in ("adr", "dat_w", "sel", "we", "cti", "bte")
            ]
        )
        response = Record([("dat_r", len(source.dat_r)), ("err", 1)])
        sent, completed = Signal(), Signal()
        sent_sync, completed_sync = Signal(), Signal()
        self.specials += MultiReg(sent, sent_sync, odomain=cd_to)
        self.specials += MultiReg(completed, completed_sync, odomain=cd_from)
        master = ClockDomainsRenamer(cd_from)(FSM(reset_state="IDLE"))
        slave = ClockDomainsRenamer(cd_to)(FSM(reset_state="IDLE"))
        self.submodules += master, slave
        active = source.cyc & source.stb
        master.act(
            "IDLE",
            If(
                active,
                *[
                    NextValue(getattr(request, n), getattr(source, n))
                    for n in ("adr", "dat_w", "sel", "we", "cti", "bte")
                ],
                NextValue(sent, ~sent),
                NextState("WAIT"),
            ),
        )
        master.act(
            "WAIT",
            If(
                completed_sync == sent,
                source.dat_r.eq(response.dat_r),
                source.ack.eq(active & ~response.err),
                source.err.eq(active & response.err),
                NextState("IDLE"),
            ).Elif(~active, NextState("DISCARD")),
        )
        master.act("DISCARD", If(completed_sync == sent, NextState("IDLE")))
        self.comb += [
            getattr(target, n).eq(getattr(request, n))
            for n in ("adr", "dat_w", "sel", "we")
        ]
        self.comb += [target.cti.eq(0), target.bte.eq(0)]
        slave.act("IDLE", If(sent_sync != completed, NextState("ACCESS")))
        slave.act(
            "ACCESS",
            target.cyc.eq(1),
            target.stb.eq(1),
            # Sample throughout ACCESS so the bus acknowledgement does not
            # drive a wide response-register enable network. The final sample
            # is the acknowledged beat and remains stable through RESPOND.
            NextValue(response.dat_r, target.dat_r),
            NextValue(response.err, target.err),
            If(
                target.ack | target.err,
                NextState("RESPOND"),
            ),
        )
        slave.act(
            "RESPOND",
            NextValue(completed, sent_sync),
            NextState("IDLE"),
        )
