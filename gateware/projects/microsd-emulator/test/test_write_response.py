import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer


@cocotb.test()
async def native_tokens_busy_and_cancel(d):
    cocotb.start_soon(Clock(d.clk, 10, units="ns").start())

    async def tick(**values):
        await FallingEdge(d.clk)
        for name, value in values.items():
            getattr(d, name).value = value
        await RisingEdge(d.clk)
        await Timer(1, units="ns")

    await tick(rst=1, prepared_mode=0, cancel=0, start=0, accepted=0, fall=0, busy=0)
    await tick(rst=0)
    for accepted in (True, False):
        await tick(start=1, accepted=accepted, busy=1)
        await tick(start=0)
        values = []
        for _ in range(6):
            await tick(fall=1)
            values.append(None if not int(d.dat_oe.value) else int(d.dat_out.value) & 1)
            assert int(d.dat_oe.value) in (0, 1)
            await tick(fall=0)
        assert values == [
            None,
            0,
            int(not accepted),
            int(accepted),
            int(not accepted),
            1,
        ]
        await tick(fall=1)
        assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) == 14
        await tick(fall=0)
        if accepted:
            for _ in range(8):
                await tick(fall=1)
                assert int(d.dat_out.value) == 14
                await tick(fall=0)
        await tick(busy=0, fall=1)
        assert int(d.dat_oe.value) == 1 and int(d.dat_out.value) == 15
        await tick(fall=0)
        await tick(fall=1)
        assert not int(d.dat_oe.value) and int(d.complete.value)
        await tick(fall=0)
        assert not int(d.complete.value)
    await tick(start=1, accepted=1, busy=1)
    await tick(start=0, fall=1)
    await tick(fall=1)
    await tick(fall=1)
    assert int(d.dat_oe.value) == 1
    await tick(cancel=1, fall=0)
    assert not int(d.dat_oe.value) and not int(d.active.value)
