# top = tb_uart_tx

import random

import cocotb
from cocotb_helpers import start_clock
from cocotb_helpers import tick


CLK_FREQ = 40
BAUD = 10
DATA_WIDTH = 20
CLK_PER_BIT = (CLK_FREQ + BAUD) // BAUD - 1
FRAME_CYCLES = (1 + DATA_WIDTH + 1) * CLK_PER_BIT


class MyUartTxModel:
    IDLE = 0
    START = 1
    DATA = 2
    STOP = 3

    def __init__(self, *, data_width: int):
        self.data_width = data_width
        self.data_mask = (1 << data_width) - 1
        self.ctr_last = CLK_PER_BIT - 1
        self.state = self.IDLE
        self.ctr = 0
        self.bit_ctr = 0
        self.saved_data = 0
        self.tx_reg = 0
        self.block_flag = 0

    def step(self, *, rst: int, block: int, new_data: int, data: int) -> tuple[int, int]:
        eff_state = self.IDLE if rst else self.state

        next_state = eff_state
        next_ctr = self.ctr
        next_bit_ctr = self.bit_ctr
        next_saved_data = self.saved_data
        next_tx_reg = self.tx_reg

        if eff_state == self.IDLE:
            next_tx_reg = 1
            if self.block_flag == 0:
                next_ctr = 0
                next_bit_ctr = 0
                if new_data:
                    next_saved_data = data & self.data_mask
                    next_state = self.START
        elif eff_state == self.START:
            next_tx_reg = 0
            next_ctr = self.ctr + 1
            if self.ctr == self.ctr_last:
                next_ctr = 0
                next_state = self.DATA
        elif eff_state == self.DATA:
            next_tx_reg = (self.saved_data >> self.bit_ctr) & 1
            next_ctr = self.ctr + 1
            if self.ctr == self.ctr_last:
                next_ctr = 0
                next_bit_ctr = (self.bit_ctr + 1) & 0xFFFF
                if self.bit_ctr == self.data_width - 1:
                    next_state = self.STOP
        elif eff_state == self.STOP:
            next_tx_reg = 1
            next_ctr = self.ctr + 1
            if self.ctr == self.ctr_last:
                next_state = self.IDLE

        if rst:
            next_state = self.IDLE

        self.state = next_state
        self.ctr = next_ctr
        self.bit_ctr = next_bit_ctr
        self.saved_data = next_saved_data
        self.tx_reg = next_tx_reg
        self.block_flag = 1 if block else 0

        busy = 1
        if self.state == self.IDLE and self.block_flag == 0:
            busy = 0

        return self.tx_reg, busy


async def _step_and_check(dut, model: MyUartTxModel, *, rst: int, block: int, new_data: int, data: int):
    dut.rst.value = rst
    dut.block.value = block
    dut.new_data.value = new_data
    dut.data_word.value = data
    await tick(dut.clk, 1)

    exp_tx, exp_busy = model.step(rst=rst, block=block, new_data=new_data, data=data)
    got_tx = int(dut.tx_line.value)
    got_busy = int(dut.tx_busy.value)

    assert got_tx == exp_tx, (
        f"tx mismatch rst={rst} block={block} new_data={new_data} data=0x{data:05x} "
        f"expected={exp_tx} got={got_tx}"
    )
    assert got_busy == exp_busy, (
        f"busy mismatch rst={rst} block={block} new_data={new_data} data=0x{data:05x} "
        f"expected={exp_busy} got={got_busy}"
    )


async def _init_test(dut, model: MyUartTxModel):
    start_clock(dut.clk)
    dut.rst.value = 1
    dut.block.value = 0
    dut.new_data.value = 0
    dut.data_word.value = 0

    # Do not score cycles while reset is asserted: in Lucid only `state` has
    # explicit reset, while tx_reg/ctr/bit_ctr are not reset.
    await tick(dut.clk, 3)
    dut.rst.value = 0
    for _ in range(4):
        await _step_and_check(dut, model, rst=0, block=0, new_data=0, data=0)

    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_busy.value) == 0


@cocotb.test()
async def directed_20bit_frame_matches_model(dut):
    model = MyUartTxModel(data_width=DATA_WIDTH)
    await _init_test(dut, model)

    payload = 0xABCDE
    await _step_and_check(dut, model, rst=0, block=0, new_data=1, data=payload)
    await _step_and_check(dut, model, rst=0, block=0, new_data=0, data=payload)

    for _ in range(FRAME_CYCLES + 8):
        await _step_and_check(dut, model, rst=0, block=0, new_data=0, data=payload)

    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_busy.value) == 0


@cocotb.test()
async def block_semantics_match_lucid_behavior(dut):
    model = MyUartTxModel(data_width=DATA_WIDTH)
    await _init_test(dut, model)

    blocked_payload = 0x13579
    accepted_payload = 0x2468A

    # Hold block high long enough for block_flag.q to become 1, then attempt send.
    await _step_and_check(dut, model, rst=0, block=1, new_data=0, data=0)
    await _step_and_check(dut, model, rst=0, block=1, new_data=1, data=blocked_payload)
    for _ in range(CLK_PER_BIT * 3):
        await _step_and_check(dut, model, rst=0, block=1, new_data=0, data=blocked_payload)

    # Assert block and new_data in the same cycle while currently unblocked:
    # Lucid block_flag is registered, so this send is still accepted.
    await _step_and_check(dut, model, rst=0, block=0, new_data=0, data=0)
    await _step_and_check(dut, model, rst=0, block=1, new_data=1, data=accepted_payload)
    for _ in range(FRAME_CYCLES + CLK_PER_BIT):
        await _step_and_check(dut, model, rst=0, block=1, new_data=0, data=accepted_payload)

    assert int(dut.tx_line.value) == 1
    assert int(dut.tx_busy.value) == 1  # still blocked in idle


@cocotb.test()
async def randomized_model_compat(dut):
    model = MyUartTxModel(data_width=DATA_WIDTH)
    await _init_test(dut, model)

    rng = random.Random(0x5A77C0DE)
    for _ in range(1200):
        block = rng.randrange(2)
        new_data = rng.randrange(2)
        data = rng.randrange(1 << DATA_WIDTH)
        await _step_and_check(dut, model, rst=0, block=block, new_data=new_data, data=data)
