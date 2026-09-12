import binascii
import os
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


@cocotb.test()
async def enumerate_read_single_and_scr_in_one_and_four_bit_modes(d):
    h = await setup(d)
    await h.init()
    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        await h.command(55, 0x10000)
        await h.command(51)
        assert await h.data(8, wide) == bytes.fromhex("0105000000000000")
        response = await h.command(17, 512 * 127)
        assert not int.from_bytes(response[1:5], "big") & 0xFFF80000
        assert int(d.request_lba.value) == 127
        for _ in range(20):
            assert not (await h.cycle())[2]
        await h.supply()
        assert await h.data(wide=wide) == h.sector


@cocotb.test()
async def bad_crc_ranges_write_protection_and_cancelled_backend(d):
    h = await setup(d)
    await h.init()
    await h.command(17, 0, length=0, corrupt=True)
    for _ in range(12):
        assert not (await h.cycle())[0]
        assert not int(d.request_valid.value)
    for command, arg, error in [
        (17, 1, 1 << 30),
        (17, 8388608, 1 << 31),
        (24, 0, 1 << 26),
        (25, 0, 1 << 26),
        (16, 1024, 1 << 22),
    ]:
        result = await h.command(command, arg)
        assert int.from_bytes(result[1:5], "big") & error
        assert not int(d.request_valid.value)
    await h.command(18, 0)
    old = int(d.generation.value)
    await h.command(12)
    assert not int(d.request_valid.value)
    d.sector_generation.value = old
    d.sector_ready.value = 1
    for _ in range(20):
        assert not (await h.cycle())[2]
    d.sector_ready.value = 0
    await h.command(17, 1024)
    assert int(d.generation.value) != old
    await h.supply()
    assert await h.data() == h.sector
    d.armed.value = 0
    await tick(d.clk, 4)
    assert not int(d.cmd_oe.value) and not int(d.dat_oe.value)


@cocotb.test()
async def multiblock_progress_and_stop_during_data(d):
    h = await setup(d)
    await h.init()
    await h.command(55, 0x10000)
    await h.command(6, 2)
    await h.command(18, 126 * 512)
    for lba in (126, 127):
        assert int(d.request_lba.value) == lba
        await h.supply()
        assert await h.data(wide=True) == h.sector
        await h.cycle()
    assert int(d.request_lba.value) == 128
    await h.supply()
    # Let a third block begin, then interrupt it with native CMD12 on CMD.
    for _ in range(20):
        await h.cycle()
    assert int(d.dat_oe.value) == 15
    await h.command(12)
    assert not int(d.dat_oe.value) and not int(d.request_valid.value)
    await h.command(0, length=0)
    await h.init()


@cocotb.test()
async def sd_status_reports_current_bus_width(d):
    h = await setup(d)
    await h.init()
    for wide in (False, True):
        await h.command(55, 0x10000)
        await h.command(6, 2 if wide else 0)
        await h.command(55, 0x10000)
        response = await h.command(13, 0)
        assert not int.from_bytes(response[1:5], "big") & (1 << 22)
        assert await h.data(64, wide) == bytes([0x80 if wide else 0]) + bytes(63)
        assert not int(d.request_valid.value)
        response = await h.command(13, 0x10000)
        assert not int.from_bytes(response[1:5], "big") & (1 << 22)
        for _ in range(10):
            assert not (await h.cycle())[2]
