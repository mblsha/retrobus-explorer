"""Register the refresher's bank request while preserving command timing."""

import inspect
from litedram.core import refresher
from generate_bios import RegisteredRefreshTimer


def make_refresher():
    source = inspect.getsource(refresher)
    marker = "        # Refresh FSM ------------------------------------------------------------------------------"
    assert source.count(marker) == 1
    before, fsm = source.split(marker)
    assert "cmd.valid.eq" in fsm
    source = (
        before
        + """        request_valid = Signal()
        self.sync += cmd.valid.eq(request_valid)
"""
        + marker
        + fsm.replace("cmd.valid.eq", "request_valid.eq")
    )
    scope = {"__name__": "registered_refresher_generated"}
    exec(compile(source, refresher.__file__, "exec"), scope)
    scope["RefreshTimer"] = RegisteredRefreshTimer
    return scope["Refresher"]


def install():
    from litedram.core.controller import ControllerSettings

    defaults = ControllerSettings.__init__.__defaults__
    assert sum(v is refresher.Refresher for v in defaults) == 1
    cls = make_refresher()
    ControllerSettings.__init__.__defaults__ = tuple(
        cls if v is refresher.Refresher else v for v in defaults
    )
