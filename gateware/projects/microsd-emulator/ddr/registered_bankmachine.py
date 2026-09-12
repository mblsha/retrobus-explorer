"""Apply a narrow, checked transformation to pinned LiteDRAM bank control.

A new command waits one cycle for its registered row-hit result. After a
command is consumed, the guard falls for one cycle before the next can issue.
This removes the row comparator from the command-acceptance critical path.
"""

import inspect
from litedram.core import bankmachine


def make_bankmachine():
    source = inspect.getsource(bankmachine)
    original = (
        "        self.comb += row_hit.eq(row == slicer.row(cmd_buffer.source.addr))"
    )
    replacement = """        self.sync += row_hit.eq(row == slicer.row(cmd_buffer.source.addr))
        command_stable = Signal()
        self.sync += command_stable.eq(cmd_buffer.source.valid & ~cmd_buffer.source.ready)"""
    guard = ").Elif(cmd_buffer.source.valid,"
    assert source.count(original) == 1
    assert source.count(guard) == 1
    source = source.replace(original, replacement).replace(
        guard, ").Elif(cmd_buffer.source.valid & command_stable,"
    )
    scope = {"__name__": "registered_bankmachine_generated"}
    exec(compile(source, bankmachine.__file__, "exec"), scope)
    return scope["BankMachine"]


def install():
    from litedram.core import controller

    controller.BankMachine = make_bankmachine()
