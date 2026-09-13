import struct
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer

from packet_support import MAC, HOST, IP, HOST_IP, checksum, ipv4, udp


@cocotb.test()
async def arp_ping_udp_and_rejections(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    for name in (
        "rx_available",
        "rx_length",
        "rx_data",
        "app_address",
        "app_write",
        "app_write_address",
        "app_write_data",
        "app_done",
        "app_length",
    ):
        getattr(dut, name).value = 0
    dut.tx_ready.value = 1
    await Timer(40, units="ns")
    dut.rst.value = 0
    response = b"validated UDP response"

    async def exchange(packet, app_expected=None):
        dut.rx_available.value = 1
        dut.rx_length.value = len(packet)
        output = bytearray()
        app_started = False
        app_index = 0
        submitted = False
        for cycle in range(10000):
            await FallingEdge(dut.clk)
            address = int(dut.rx_address.value)
            dut.rx_data.value = packet[address] if address < len(packet) else 0
            if int(dut.app_request.value) and not app_started:
                assert app_expected is not None, (
                    "Unvalidated packet reached application"
                )
                assert int(dut.app_request_length.value) == len(app_expected)
                app_started = True
            if app_started and int(dut.app_request.value):
                if app_index < len(response):
                    dut.app_write.value = 1
                    dut.app_write_address.value = app_index
                    dut.app_write_data.value = response[app_index]
                    app_index += 1
                else:
                    dut.app_write.value = 0
                    dut.app_done.value = 1
                    dut.app_length.value = len(response)
            if int(dut.tx_write.value):
                assert int(dut.tx_address.value) == len(output)
                output.append(int(dut.tx_data.value))
            if int(dut.tx_submit.value):
                assert int(dut.tx_length.value) == len(output)
                submitted = True
            if int(dut.rx_consume.value):
                dut.rx_available.value = 0
                await Timer(20, units="ns")
                break
        else:
            assert False, "Engine timeout"
        dut.app_done.value = 0
        dut.app_write.value = 0
        await Timer(30, units="ns")
        if app_expected is not None:
            assert app_started
        assert submitted == bool(output)
        return bytes(output)

    arp = (
        b"\xff" * 6
        + HOST
        + b"\x08\x06"
        + struct.pack("!HHBBH", 1, 0x800, 6, 4, 1)
        + HOST
        + HOST_IP
        + b"\0" * 6
        + IP
    )
    reply = await exchange(arp.ljust(60, b"\0"))
    assert (
        reply
        == HOST
        + MAC
        + b"\x08\x06"
        + struct.pack("!HHBBH", 1, 0x800, 6, 4, 2)
        + MAC
        + IP
        + HOST
        + HOST_IP
    )
    for payload in (b"hello", bytes(range(128))):
        icmp = b"\x08\0\0\0\x12\x34\0\1" + payload
        icmp = icmp[:2] + struct.pack("!H", checksum(icmp)) + icmp[4:]
        reply = await exchange(ipv4(1, icmp))
        assert reply[:14] == HOST + MAC + b"\x08\0"
        assert checksum(reply[14:34]) == 0
        assert reply[26:34] == IP + HOST_IP
        assert reply[34:36] == b"\0\0"
        assert checksum(reply[34:]) == 0
        assert reply[38:] == icmp[4:]
    for checked in (False, True):
        payload = b"odd payload"
        reply = await exchange(udp(payload, checked), payload)
        assert checksum(reply[14:34]) == 0
        assert reply[34:42] == struct.pack("!HHHH", 4000, 23456, 8 + len(response), 0)
        assert reply[42:] == response
    bad = bytearray(udp(b"bad checksum"))
    bad[42] ^= 1
    assert not await exchange(bytes(bad))
    bad = bytearray(udp(b"bad header"))
    bad[24] ^= 1
    assert not await exchange(bytes(bad))
    assert not await exchange(ipv4(17, b"\0" * 8, destination=HOST_IP))
    assert not await exchange(ipv4(17, b"\0" * 8, fragment=0x2000))
    assert not await exchange(udp(b"truncated payload")[:45])
