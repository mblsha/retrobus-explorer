import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer


async def pulse(dut, name):
    getattr(dut, name).value = 1
    await Timer(10, units="ns")
    getattr(dut, name).value = 0
    await Timer(10, units="ns")


async def snapshot(dut):
    words = []
    for index in range(11):
        dut.word_index.value = index
        await Timer(20, units="ns")
        words.append(int(dut.word.value))
    return words


@cocotb.test()
async def records_clock_commands_and_backend_activity(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    dut.armed.value = 0
    dut.initialized.value = 1
    dut.clock_tick.value = 0
    dut.command_frame.value = 0
    dut.command_valid.value = 0
    dut.command_index.value = 0
    dut.command_argument.value = 0
    dut.read_request.value = 0
    dut.read_lba.value = 0
    dut.write_busy.value = 0
    dut.word_index.value = 0
    await Timer(40, units="ns")
    dut.rst.value = 0
    dut.armed.value = 1

    for _ in range(100):
        await pulse(dut, "clock_tick")
    dut.command_index.value = 17
    dut.command_argument.value = 0x01020304
    dut.command_valid.value = 1
    dut.command_frame.value = 1
    await Timer(10, units="ns")
    dut.command_valid.value = 0
    dut.command_frame.value = 0
    await Timer(10, units="ns")
    await pulse(dut, "command_frame")
    dut.read_lba.value = 33
    dut.read_request.value = 1
    await Timer(20, units="ns")
    dut.read_request.value = 0
    dut.write_busy.value = 1
    await Timer(20, units="ns")
    dut.write_busy.value = 0
    await Timer(30, units="ns")

    words = await snapshot(dut)
    assert words[0] == 0x31544453
    assert words[1] & 3 == 3
    assert words[2] == 100
    assert words[3:6] == [2, 1, 1]
    assert words[6] == 17
    assert words[7] == 0x01020304
    assert words[8:11] == [1, 33, 1]
