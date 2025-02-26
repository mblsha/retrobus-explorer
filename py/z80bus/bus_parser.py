from typing import NamedTuple, Optional, List
from enum import Enum
from dataclasses import dataclass
import struct

import threading
import queue


# http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
class IOPort(Enum):
    LCD_COMMAND = 0x40
    LCD_OUT = 0x41

    ROM_EX_BANK = 0x19
    RAM_BANK = 0x1B
    ROM_BANK = 0x69

    # FIXME: what does it do??
    SHIFT_KEY_INPUT = 0x13  # Read-only

    KEY_INPUT = 0x10  # Read-only
    SET_KEY_STROBE_LO = 0x11  # Write-only
    SET_KEY_STROBE_HI = 0x12  # Write-only

    TIMER = 0x14
    XIN_ENABLED = 0x15
    INTERRUPT_FLAGS = 0x16
    INTERRUPT_MASK = 0x17

    ON_CONTROL_BY_CD_SIGNAL = 0x64
    WAIT_AFTER_M1 = 0x65
    WAIT_AFTER_IO = 0x66
    CPU_CLOCK_MODE = 0x67

    SET_1S_TIMER_PERIOD = 0x68

    GPIO_IO_OUTPUT = 0x18  # 11-pin connector
    GET_GPIO_IO = 0x1F
    GPIO_IO_MODE = 0x60
    SET_PIO_DIRECTION = 0x61
    PIO_REGISTER = 0x62

    # According to https://ver0.sakura.ne.jp/doc/pcg850vuart.html the PC-G850V has different port
    # definitions compared to the PC-G850/PC-G850S.
    UART_FLOW_REGISTER = 0x63
    UART_INPUT_SELECTION = 0x6B
    SET_UART_MODE = 0x6C
    SET_UART_COMMAND = 0x6D
    GET_UART_STATUS = 0x6E
    UART_DATA = 0x6F

    SET_BOOTROM_OFF = 0x1A
    RAM_CE_MODE = (
        0x1B  # 0: CERAM1 (internal RAM), 1: CERAM2 (external RAM on system bus)
    )
    SET_IORESET = 0x1C

    UNKNOWN_1D = 0x1D
    UNKNOWN_1E = 0x1E  # battery check mode?


class Type(Enum):
    FETCH = "M"  # M1: Instruction Fetch
    READ = "R"  # Memory Read
    WRITE = "W"  # Memory Write
    IN_PORT = "r"  # IO Read
    OUT_PORT = "w"  # IO Write

    # synthetic types not transmitted by the device
    READ_STACK = "S"  # Read from stack
    WRITE_STACK = "s"  # Write to stack


class InstructionType(Enum):
    CALL = 1
    CALL_CONDITIONAL = 2
    RET = 3
    RET_CONDITIONAL = 4
    MULTI_PREFIX = 5


@dataclass
class Event:
    type: Type
    val: int  # uint8
    addr: int = None  # uint16
    pc: Optional[int] = None  # uint32
    bank: Optional[int] = None
    port: Optional[IOPort] = None
    instr: Optional[InstructionType] = None


# for some opcodes the processor will set M1 low twice, if unhandled we can misclassify the second M1 as CALL/RET
OPCODE_MULTI_PREFIX = set([0xCB, 0xDD, 0xED, 0xFD])
# https://clrhome.org/table/#call
OPCODE_CALL_PREFIX = set([0xCD])
OPCODE_CONDITIONAL_CALL_PREFIX = set([0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC])
# https://clrhome.org/table/#ret
OPCODE_RET_PREFIX = set([0xC9])
OPCODE_CONDITIONAL_RET_PREFIX = set([0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8])

ROM_ADDR_START = 0x8000
BANK_ADDR_START = 0xC000
BANK_SIZE = 0x4000
# not sure how big the stack is, this area is also used for variable storage
STACK_SIZE = 0x400


class BusParser:
    def __init__(self):
        self.rom_bank = None
        self.pc = None

    def is_stack_addr(self, addr):
        return addr < ROM_ADDR_START and addr > ROM_ADDR_START - STACK_SIZE

    def full_addr(self, addr):
        # bank 1 is at BANK_ADDR_START, bank 2 is at BANK_ADDR_START + 0x4000
        if addr < BANK_ADDR_START:
            if addr >= ROM_ADDR_START:
                return addr, 0
            return addr, None

        return addr + BANK_SIZE * (self.rom_bank - 1), self.rom_bank

    def parse(self, data):
        errors = []
        r = []

        # indexes
        last_call_conditional = None
        last_ret_conditional = None
        prefix_opcode = None

        offset = 0
        while offset < len(data) and len(data) - offset >= 4:
            try:
                type = Type(chr(data[offset]))
            except ValueError:
                errors.append(f"Invalid type at offset {offset}: {data[offset]}")
                offset += 1
                # raise ValueError(f"Invalid type at index {index}: {i}")
                continue

            val = struct.unpack("B", data[offset + 1 : offset + 2])[0]
            addr = struct.unpack("<H", data[offset + 2 : offset + 4])[0]
            offset += 4

            instr = None
            port = None
            bank = None

            # handle second byte of the instruction when M1 is low twice in a row
            if prefix_opcode is not None and type == Type.FETCH:
                type = Type.READ

            if type == Type.FETCH:
                last_call_conditional = None
                last_ret_conditional = None
                prefix_opcode = None

                self.pc, bank = self.full_addr(addr)
                addr = self.pc
                if val in OPCODE_MULTI_PREFIX:
                    instr = InstructionType.MULTI_PREFIX
                elif val in OPCODE_CALL_PREFIX:
                    instr = InstructionType.CALL
                elif val in OPCODE_CONDITIONAL_CALL_PREFIX:
                    instr = InstructionType.CALL_CONDITIONAL
                elif val in OPCODE_RET_PREFIX:
                    instr = InstructionType.RET
                elif val in OPCODE_CONDITIONAL_RET_PREFIX:
                    instr = InstructionType.RET_CONDITIONAL
            elif type in [Type.READ, Type.WRITE]:
                prefix_opcode = None

                addr, bank = self.full_addr(addr)

                # we don't have visibility of the current flag status, so in order to determine whether
                # a conditional CALL/RET did actually CALL/RET we need to look whether the stack was written/read
                if self.is_stack_addr(addr):
                    if type == Type.READ:
                        type = Type.READ_STACK
                        if last_ret_conditional is not None:
                            r[last_ret_conditional].instr = InstructionType.RET
                    else:
                        type = Type.WRITE_STACK
                        if last_call_conditional is not None:
                            r[last_call_conditional].instr = InstructionType.CALL

            elif type in [Type.IN_PORT, Type.OUT_PORT]:
                prefix_opcode = None

                addr &= 0xFF
                try:
                    port = IOPort(addr)

                    if port == IOPort.ROM_BANK:
                        self.rom_bank = val
                    elif port == IOPort.ROM_EX_BANK:
                        self.rom_bank = val & 0x0F
                except:
                    errors.append(f"Invalid port at offset {offset}: {hex(addr)}")

            r.append(
                Event(
                    type=type,
                    val=val,
                    addr=addr,
                    pc=self.pc,
                    port=port,
                    instr=instr,
                    bank=bank,
                )
            )
            last_index = len(r) - 1
            if instr == InstructionType.MULTI_PREFIX:
                prefix_opcode = last_index
            elif instr == InstructionType.CALL_CONDITIONAL:
                last_call_conditional = last_index
            elif instr == InstructionType.RET_CONDITIONAL:
                last_ret_conditional = last_index

        if offset != len(data):
            errors.append(f"Trailing data at offset {offset}")
        return r, errors


class PipelineBusParser:
    def __init__(self, out_queue):
        self.out_queue = out_queue

        self.rom_bank = None
        self.pc = None
        self.errors = []

        # these are events that are not yet complete
        self.last_call_conditional = None
        self.last_ret_conditional = None
        self.prefix_opcode = None

    def is_stack_addr(self, addr):
        return addr < ROM_ADDR_START and addr > ROM_ADDR_START - STACK_SIZE

    def full_addr(self, addr):
        # bank 1 is at BANK_ADDR_START, bank 2 is at BANK_ADDR_START + 0x4000
        if addr < BANK_ADDR_START:
            if addr >= ROM_ADDR_START:
                return addr, 0
            return addr, None

        return addr + BANK_SIZE * (self.rom_bank - 1), self.rom_bank

    def flush_prefix_opcode(self):
        if self.prefix_opcode is not None:
            self.out_queue.put(self.prefix_opcode)
            self.prefix_opcode = None

    def flush_last_call_conditional(self):
        if self.last_call_conditional is not None:
            self.out_queue.put(self.last_call_conditional)
            self.last_call_conditional = None

    def flush_last_ret_conditional(self):
        if self.last_ret_conditional is not None:
            self.out_queue.put(self.last_ret_conditional)
            self.last_ret_conditional = None

    def event(self, type, val, addr):
        instr = None
        port = None
        bank = None

        # handle second byte of the instruction when M1 is low twice in a row
        if self.prefix_opcode is not None and type == Type.FETCH:
            type = Type.READ

        if type == Type.FETCH:
            self.pc, bank = self.full_addr(addr)
            addr = self.pc
            if val in OPCODE_MULTI_PREFIX:
                instr = InstructionType.MULTI_PREFIX
            elif val in OPCODE_CALL_PREFIX:
                instr = InstructionType.CALL
            elif val in OPCODE_CONDITIONAL_CALL_PREFIX:
                instr = InstructionType.CALL_CONDITIONAL
            elif val in OPCODE_RET_PREFIX:
                instr = InstructionType.RET
            elif val in OPCODE_CONDITIONAL_RET_PREFIX:
                instr = InstructionType.RET_CONDITIONAL
        elif type in [Type.READ, Type.WRITE]:
            addr, bank = self.full_addr(addr)

            # we don't have visibility of the current flag status, so in order to determine whether
            # a conditional CALL/RET did actually CALL/RET we need to look whether the stack was written/read
            if self.is_stack_addr(addr):
                if type == Type.READ:
                    type = Type.READ_STACK
                    if self.last_ret_conditional is not None:
                        self.last_ret_conditional.instr = InstructionType.RET
                else:
                    type = Type.WRITE_STACK
                    if self.last_call_conditional is not None:
                        self.last_call_conditional.instr = InstructionType.CALL

        elif type in [Type.IN_PORT, Type.OUT_PORT]:
            addr &= 0xFF
            try:
                port = IOPort(addr)

                if port == IOPort.ROM_BANK:
                    self.rom_bank = val
                elif port == IOPort.ROM_EX_BANK:
                    self.rom_bank = val & 0x0F
            except:
                self.errors.append(f"Invalid port at {hex(addr)}")

        return Event(
            type=type,
            val=val,
            addr=addr,
            pc=self.pc,
            port=port,
            instr=instr,
            bank=bank,
        )

    def parse(self, data):
        while len(data) >= 4:
            try:
                type = Type(chr(data[0]))
            except ValueError:
                self.errors.append(f"Invalid type at offset {0}: {data[0]}")
                data = data[1:]
                continue

            val = struct.unpack("B", data[1:2])[0]
            addr = struct.unpack("<H", data[2:4])[0]
            data = data[4:]

            e = self.event(type, val, addr)

            self.flush_last_call_conditional()
            self.flush_last_ret_conditional()
            self.flush_prefix_opcode()

            if e.instr == InstructionType.MULTI_PREFIX:
                self.prefix_opcode = e
            elif e.instr == InstructionType.CALL_CONDITIONAL:
                self.last_call_conditional = e
            elif e.instr == InstructionType.RET_CONDITIONAL:
                self.last_ret_conditional = e
            else:
                self.out_queue.put(e)

        # return unprocessed data, it should be concatenated with the next batch
        return data
