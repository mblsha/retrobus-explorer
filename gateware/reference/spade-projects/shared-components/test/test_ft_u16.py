# top = tb_ft_u16

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer


def _bit(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 1


def _u2(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0x3


def _u16(signal) -> int:
    value = signal.value
    if not value.is_resolvable:
        raise AssertionError(f"unresolved signal: {signal._name}={value}")
    return int(value) & 0xFFFF


async def _init(dut) -> None:
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    cocotb.start_soon(Clock(dut.ft_clk, 8, units="ns").start())

    dut.rst.value = 1
    dut.ft_rxf.value = 1
    dut.ft_txe.value = 1
    dut.ft_data_in.value = 0
    dut.ft_be_in.value = 0

    dut.ui_din.value = 0
    dut.ui_din_be.value = 0
    dut.ui_din_valid.value = 0
    dut.ui_dout_get.value = 0

    for _ in range(8):
        await RisingEdge(dut.clk)
    for _ in range(8):
        await RisingEdge(dut.ft_clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")


async def _push_ui_word(dut, *, data: int, be: int, timeout_cycles: int = 400) -> None:
    for _ in range(timeout_cycles):
        await FallingEdge(dut.clk)
        if _bit(dut.ui_din_full) == 0:
            dut.ui_din.value = data & 0xFFFF
            dut.ui_din_be.value = be & 0x3
            dut.ui_din_valid.value = 1
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
            await FallingEdge(dut.clk)
            dut.ui_din_valid.value = 0
            return
    raise AssertionError("timed out waiting for ui_din_full=0")


async def _collect_ft_writes(dut, count: int, timeout_cycles: int = 2000) -> list[tuple[int, int]]:
    observed: list[tuple[int, int]] = []
    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_write = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        sampled_word = (_u16(dut.ft_data_out), _u2(dut.ft_be_out))
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_write:
            observed.append(sampled_word)
            if len(observed) == count:
                return observed
    raise AssertionError(f"timed out waiting for {count} FT writes")


async def _feed_ft_words(dut, words: list[tuple[int, int]], timeout_cycles: int = 4000) -> list[tuple[int, int]]:
    accepted: list[tuple[int, int]] = []
    idx = 0

    if words:
        dut.ft_rxf.value = 0
        dut.ft_data_in.value = words[0][0]
        dut.ft_be_in.value = words[0][1]
    else:
        dut.ft_rxf.value = 1

    for _ in range(timeout_cycles):
        await FallingEdge(dut.ft_clk)
        will_read = _bit(dut.ft_oe) == 0 and _bit(dut.ft_rd) == 0 and _bit(dut.ft_rxf) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if will_read:
            accepted.append(words[idx])
            idx += 1
            if idx == len(words):
                dut.ft_rxf.value = 1
                return accepted
            dut.ft_data_in.value = words[idx][0]
            dut.ft_be_in.value = words[idx][1]

    raise AssertionError(f"timed out waiting for FT to accept {len(words)} words")


async def _pop_ui_word(dut, timeout_cycles: int = 2000) -> tuple[int, int]:
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        if _bit(dut.ui_dout_empty) == 0:
            word = (_u16(dut.ui_dout), _u2(dut.ui_dout_be))
            await FallingEdge(dut.clk)
            dut.ui_dout_get.value = 1
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
            await FallingEdge(dut.clk)
            dut.ui_dout_get.value = 0
            return word
    raise AssertionError("timed out waiting for ui_dout_empty=0")


@cocotb.test()
async def ft_u16_tx_rx_paths_preserve_order_and_be(dut):
    await _init(dut)

    tx_words = [
        (0x1234, 0b11),
        (0xABCD, 0b01),
        (0x00FE, 0b10),
        (0x55AA, 0b11),
    ]
    for data, be in tx_words:
        await _push_ui_word(dut, data=data, be=be)

    dut.ft_txe.value = 0
    observed_tx = await _collect_ft_writes(dut, len(tx_words))
    assert observed_tx == tx_words

    rx_words = [
        (0x0102, 0b11),
        (0xF0F1, 0b10),
        (0x00A5, 0b01),
        (0x5A5A, 0b11),
    ]
    accepted_rx = await _feed_ft_words(dut, rx_words)
    assert accepted_rx == rx_words

    observed_rx = []
    for _ in rx_words:
        observed_rx.append(await _pop_ui_word(dut))
    assert observed_rx == rx_words


@cocotb.test()
async def ft_u16_prefers_read_over_write_when_both_ready(dut):
    await _init(dut)

    await _push_ui_word(dut, data=0xDEAD, be=0b11)
    dut.ft_txe.value = 0
    dut.ft_rxf.value = 0
    dut.ft_data_in.value = 0xBEEF
    dut.ft_be_in.value = 0b11

    first_event = None
    for _ in range(300):
        await FallingEdge(dut.ft_clk)
        read_event = _bit(dut.ft_oe) == 0 and _bit(dut.ft_rd) == 0 and _bit(dut.ft_rxf) == 0
        write_event = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")

        if read_event:
            first_event = "read"
            dut.ft_rxf.value = 1
            break
        if write_event:
            first_event = "write"
            break

    assert first_event == "read", f"expected read to win priority, got {first_event}"

    saw_write_after = False
    for _ in range(300):
        await FallingEdge(dut.ft_clk)
        write_event = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")
        if write_event:
            saw_write_after = True
            break

    assert saw_write_after, "write path did not proceed after read-priority transfer"


@cocotb.test()
async def ft_u16_write_is_not_preempted_by_new_read_request(dut):
    await _init(dut)

    tx_words = [
        (0x1001, 0b11),
        (0x1002, 0b11),
        (0x1003, 0b11),
    ]
    for data, be in tx_words:
        await _push_ui_word(dut, data=data, be=be)

    # Allow all writes to cross into the ft_clk domain before starting tx.
    for _ in range(24):
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")

    dut.ft_txe.value = 0
    dut.ft_rxf.value = 1

    rx_word = (0xCAFE, 0b11)

    observed_write_words: list[tuple[int, int]] = []
    events: list[str] = []
    armed_read_request = False

    for _ in range(800):
        await FallingEdge(dut.ft_clk)
        write_event = _bit(dut.ft_oe) == 1 and _bit(dut.ft_wr) == 0 and _bit(dut.ft_txe) == 0
        write_word = (_u16(dut.ft_data_out), _u2(dut.ft_be_out))
        read_event = _bit(dut.ft_oe) == 0 and _bit(dut.ft_rd) == 0 and _bit(dut.ft_rxf) == 0
        await RisingEdge(dut.ft_clk)
        await Timer(1, units="ps")

        if write_event:
            events.append("write")
            observed_write_words.append(write_word)
            if not armed_read_request:
                armed_read_request = True
                dut.ft_rxf.value = 0
                dut.ft_data_in.value = rx_word[0]
                dut.ft_be_in.value = rx_word[1]

        if read_event:
            events.append("read")
            dut.ft_rxf.value = 1
            break

    assert len(observed_write_words) >= 3
    assert events[:4] == ["write", "write", "write", "read"], (
        f"unexpected event order with PREEMPT=0: {events[:4]}"
    )

    got_rx = await _pop_ui_word(dut)
    assert got_rx == rx_word


@cocotb.test()
async def ft_u16_multi_burst_integrity(dut):
    await _init(dut)

    for round_idx in range(10):
        tx_words = [
            ((round_idx << 12) | (i << 4) | (i ^ 0xA), (i % 3) + 1)
            for i in range(1, 6)
        ]

        dut.ft_txe.value = 1
        for data, be in tx_words:
            await _push_ui_word(dut, data=data, be=be)

        for _ in range(24):
            await RisingEdge(dut.ft_clk)
            await Timer(1, units="ps")

        dut.ft_txe.value = 0
        observed_tx = await _collect_ft_writes(dut, len(tx_words))
        assert observed_tx == tx_words

        rx_words = [
            (((round_idx + 1) << 11) | (i << 3) | 0x5, ((i + 1) % 3) + 1)
            for i in range(1, 6)
        ]

        accepted_rx = await _feed_ft_words(dut, rx_words)
        assert accepted_rx == rx_words

        observed_rx = []
        for _ in rx_words:
            observed_rx.append(await _pop_ui_word(dut))
        assert observed_rx == rx_words
