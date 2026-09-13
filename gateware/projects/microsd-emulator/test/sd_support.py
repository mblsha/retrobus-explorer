"""Independent SD wire host and data-packet helpers for protocol tests."""

import binascii
import os
import sys
from pathlib import Path
import cocotb
from cocotb.triggers import Timer, Edge
from cocotb_helpers import start_clock, tick


def crc7(data):
    crc = 0
    for byte in data:
        for bit in range(7, -1, -1):
            crc = ((crc << 1) ^ (9 if ((crc >> 6) ^ (byte >> bit)) & 1 else 0)) & 127
    return crc


class Host:
    def __init__(self, dut):
        self.d = dut
        self.cycles = 0
        self.half_ns = float(os.environ.get("MICROSD_HALF_NS", "500"))
        self.clock_jitter = int(os.environ.get("MICROSD_CLOCK_JITTER", "1"))
        self.sample_advance_ns = float(os.environ.get("MICROSD_SAMPLE_ADVANCE_NS", "0"))
        assert 0 <= self.sample_advance_ns < self.half_ns
        self.sector = bytes((i * 37 + (i >> 8)) & 255 for i in range(512))
        if hasattr(dut, "sector_byte"):

            async def serve_sector():
                while True:
                    dut.sector_byte.value = self.sector[int(dut.byte_index.value)]
                    await Edge(dut.byte_index)

            cocotb.start_soon(serve_sector())

    async def cycle(self, bit=1, pause=0):
        d = self.d
        d.cmd_in.value = bit
        d.sd_clk.value = 0
        self.cycles += 1
        await Timer(
            self.half_ns
            + pause
            + self.clock_jitter * (self.cycles % 7)
            - self.sample_advance_ns,
            units="ns",
            round_mode="round",
        )
        sample = tuple(int(s.value) for s in (d.cmd_oe, d.cmd_out, d.dat_oe, d.dat_out))
        if self.sample_advance_ns:
            await Timer(self.sample_advance_ns, units="ns", round_mode="round")
        d.sd_clk.value = 1
        await Timer(
            self.half_ns + self.clock_jitter * ((self.cycles * 13) % 9),
            units="ns",
            round_mode="round",
        )
        return sample

    async def command(self, index, arg=0, length=48, corrupt=False):
        raw = bytes([0x40 | index]) + arg.to_bytes(4, "big")
        raw += bytes([(crc7(raw) << 1) | 1])
        if corrupt:
            raw = raw[:-1] + bytes([raw[-1] ^ 2])
        for byte in raw:
            for bit in range(7, -1, -1):
                assert not (await self.cycle((byte >> bit) & 1))[0], "CMD contention"
        if not length:
            return None
        bits = []
        for _ in range(length + 16):
            oe, value, _, _ = await self.cycle()
            if oe:
                bits.append(value)
                if len(bits) == length:
                    break
        assert len(bits) == length, (
            index,
            len(bits),
            int(self.d.state.value) if hasattr(self.d, "state") else -1,
        )
        value = 0
        for bit in bits:
            value = (value << 1) | bit
        raw = value.to_bytes(length // 8, "big")
        assert raw[-1] & 1
        if index != 41:
            assert raw[-1] >> 1 == crc7(raw[1:-1] if length == 136 else raw[:-1]), (
                raw.hex()
            )
        await self.cycle()
        return raw

    async def init(self, writable=False):
        await self.command(0, length=0)
        assert (await self.command(8, 0x1AA))[1:5] == bytes.fromhex("000001aa")
        await self.command(55)
        assert (await self.command(41, 0x00FF8000))[1:5] == bytes.fromhex("80ff8000")
        assert b"SPADE" in await self.command(2, length=136)
        assert (await self.command(3))[1:3] == bytes.fromhex("0001")
        csd = int.from_bytes((await self.command(9, 0x10000, length=136))[1:], "big")
        if writable and int(os.environ.get("MICROSD_FAST_MODE", "0")):
            sys.path.insert(
                0,
                str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos"),
            )
            from build_ddr import SD_CSD

            assert csd == SD_CSD, "CMD9 response differs from supported build metadata"
        capacity = (
            (((csd >> 62) & 4095) + 1)
            * (1 << (((csd >> 47) & 7) + 2))
            * (1 << ((csd >> 80) & 15))
        )
        assert (csd >> 96) & 255 == (
            (0x1A if int(os.environ.get("MICROSD_FAST_MODE", "0")) else 0x12)
            if writable
            else 0x09
        )
        assert capacity == (268435456 if writable else 8388608)
        assert bool(csd & (1 << 13)) == (not writable)
        assert bool(csd & (0x10 << 84)) == writable
        await self.command(7, 0x10000)
        await self.command(16, 512)

    async def supply(self):
        d = self.d
        assert int(d.request_valid.value)
        d.sector_generation.value = int(d.generation.value)
        d.sector_ready.value = 1
        await tick(d.clk, 2)
        d.sector_ready.value = 0

    async def data(self, size=512, wide=False):
        lanes = 4 if wide else 1
        # Backend latency is measured in memory cycles, independent of SD clock.
        for _ in range(1000):
            _, _, oe, value = await self.cycle()
            if oe:
                assert oe == (15 if wide else 1)
                assert value & oe == 0
                break
        else:
            assert False, "missing data start"
        bits = []
        lane_bits = [[] for _ in range(lanes)]
        for i in range(size * 8 // lanes):
            _, _, oe, value = await self.cycle(pause=10000 if i == 12 else 0)
            assert oe == (15 if wide else 1)
            for lane in range(lanes):
                lane_bits[lane].append((value >> lane) & 1)
            bits.extend((value >> b) & 1 for b in range(lanes - 1, -1, -1))
        received = bytes(
            sum(bits[i + b] << (7 - b) for b in range(8))
            for i in range(0, len(bits), 8)
        )
        crcs = [0] * lanes
        for _ in range(16):
            _, _, oe, value = await self.cycle()
            assert oe
            for lane in range(lanes):
                crcs[lane] = (crcs[lane] << 1) | ((value >> lane) & 1)
        for lane in range(lanes):
            stream = lane_bits[lane]
            packed = bytes(
                sum(stream[i + b] << (7 - b) for b in range(8))
                for i in range(0, len(stream), 8)
            )
            assert crcs[lane] == binascii.crc_hqx(packed, 0), (lane, crcs[lane])
        _, _, oe, value = await self.cycle()
        assert value & oe == oe
        assert not (await self.cycle())[2]
        return received


async def setup(d):
    start_clock(d.clk, period_ns=float(os.environ.get("MICROSD_SYS_PERIOD_NS", "12.5")))
    d.rst.value = 1
    d.armed.value = 0
    d.writable.value = 0
    d.fast_mode.value = int(os.environ.get("MICROSD_FAST_MODE", "0"))
    d.dat_in.value = 15
    d.write_cmd_ready.value = 0
    d.write_data_ready.value = 0
    d.sd_clk.value = 1
    d.cmd_in.value = 1
    d.sector_ready.value = 0
    d.sector_generation.value = 0
    d.sector_byte.value = 0
    await tick(d.clk, 10)
    d.rst.value = 0
    d.armed.value = 1
    await tick(d.clk, 10)
    return Host(d)


def crc_bit(crc, bit):
    return ((crc << 1) ^ (0x1021 if ((crc >> 15) ^ bit) & 1 else 0)) & 65535


async def send_packet(
    h, wide, seed, corrupt=False, wait_complete=True, expect_response=True
):
    d = h.d
    data = bytes((i * 37 + seed) & 255 for i in range(512))
    d.dat_in.value = 0 if wide else 14
    assert not (await h.cycle())[2]
    crcs = [0] * (4 if wide else 1)
    for byte in data:
        for shift in range(4, -1, -4) if wide else range(7, -1, -1):
            val = (byte >> shift) & (15 if wide else 1)
            for lane in range(len(crcs)):
                crcs[lane] = crc_bit(crcs[lane], (val >> lane) & 1)
            d.dat_in.value = val if wide else val | 14
            assert not (await h.cycle())[2], "DAT contention during host packet"
    for shift in range(15, -1, -1):
        val = sum(((crc >> shift) & 1) << lane for lane, crc in enumerate(crcs))
        if corrupt and shift == 5:
            val ^= 1
        d.dat_in.value = val if wide else val | 14
        assert not (await h.cycle())[2]
    d.dat_in.value = 15
    await h.cycle()
    if not expect_response:
        for _ in range(100):
            assert not (await h.cycle())[2], "unexpected response beyond card capacity"
        return data
    token = []
    # Keep a 100 us commit allowance as the SD clock changes; 100 clocks
    # at 10 MHz would expire before the ~14 us sector commit can finish.
    for _ in range(max(100, int(100_000 // (2 * h.half_ns)))):
        _, _, oe, val = await h.cycle()
        if oe:
            assert oe == 1
            token.append(val & 1)
        if len(token) >= 5 and not oe:
            break
        if len(token) == 5 and not wait_complete:
            break
    else:
        assert False, "CRC/busy response did not finish"
    assert token[:5] == ([0, 1, 0, 1, 1] if corrupt else [0, 0, 1, 0, 1])
    assert token[-1] == 1
    return data


