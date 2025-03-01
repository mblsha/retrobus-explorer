from typing import NamedTuple, Optional, List
from enum import Enum
from dataclasses import dataclass
import struct
import multiprocessing as mp
import threading
import queue
import time
import datetime
import debugpy


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


class ErrorType(Enum):
    BUFFER_FULL = 0


class Type(Enum):
    FETCH = "M"  # M1: Instruction Fetch
    READ = "R"  # Memory Read
    WRITE = "W"  # Memory Write
    IN_PORT = "r"  # IO Read
    OUT_PORT = "w"  # IO Write

    # skipped data
    ERROR = "E"

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

    # convert to string, printing values in hex
    def stubname(self):
        # print the creation function for unittest
        if self.type == Type.FETCH:
            return f"fetch(0x{self.val:02X}, 0x{self.addr:04X})"
        elif self.type == Type.READ:
            return f"read(0x{self.val:02X}, 0x{self.addr:04X})"
        elif self.type == Type.WRITE:
            return f"write(0x{self.val:02X}, 0x{self.addr:04X})"
        elif self.type == Type.IN_PORT:
            return f"in_port(0x{self.val:02X}, IOPort.{self.port.name})"
        elif self.type == Type.OUT_PORT:
            return f"out_port(0x{self.val:02X}, IOPort.{self.port.name})"
        elif self.type == Type.READ_STACK:
            return f"read_stack(0x{self.val:02X}, 0x{self.addr:04X})"
        elif self.type == Type.WRITE_STACK:
            return f"write_stack(0x{self.val:02X}, 0x{self.addr:04X})"
        else:
            return f"{self.type.value} v:{self.val:02X} a:{self.addr:04X}"


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


# like BusParser, but only parses type, val, addr
class SimpleBusParser:
    def parse(self, data):
        r = []
        offset = 0
        while offset < len(data) and len(data) - offset >= 4:
            try:
                type = Type(chr(data[offset]))
            except ValueError:
                offset += 1
                continue

            val = struct.unpack("B", data[offset + 1 : offset + 2])[0]
            addr = struct.unpack("<H", data[offset + 2 : offset + 4])[0]

            if type == Type.ERROR:
                addr = 0
                b1 = data[offset + 1]  # LSB of fifo_full_counter.q
                b2 = data[offset + 2]  # Middle byte
                b3 = data[offset + 3]  # MSB of fifo_full_counter.q
                val = b1 | (b2 << 8) | (b3 << 16)

            offset += 4

            r.append(Event(type=type, val=val, addr=addr))
        return r


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
            if type == Type.ERROR:
                addr = 0
                b1 = data[offset + 1]  # LSB of fifo_full_counter.q
                b2 = data[offset + 2]  # Middle byte
                b3 = data[offset + 3]  # MSB of fifo_full_counter.q
                val = b1 | (b2 << 8) | (b3 << 16)
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
            errors.append(f"Trailing data")
        return r, errors


class PipelineBusParser:
    def __init__(self, errors_queue, out_ports_queue):
        self.status_num_errors = 0
        self.status_num_errors_full_buffer = 0
        self.errors_queue = errors_queue
        self.status_num_out_ports = 0
        self.status_num_out_ports_full_buffer = 0
        self.out_ports_queue = out_ports_queue

        self.rom_bank = None
        self.pc = None
        self.errors = []

        self.all_events = []
        # buffer for the current instruction
        self.buf = []

        # these are events that are not yet complete
        self.last_call_conditional = None
        self.last_ret_conditional = None
        self.prefix_opcode = None

    def flush(self):
        for e in self.buf:
            self.all_events.append(e)
            if e.type in [Type.IN_PORT, Type.OUT_PORT]:
                # print(f">> putting {e}\n")
                # if self.out_ports_queue.full():
                #     self.status_num_out_ports_full_buffer += 1
                # else:
                #     self.status_num_out_ports += 1
                self.out_ports_queue.put(e)
        self.buf = []

        for e in self.errors:
            # if self.errors_queue.full():
            #     self.status_num_errors_full_buffer += 1
            # else:
            #     self.status_num_errors += 1
            self.errors_queue.put(e)
        self.errors = []

        self.prefix_opcode = None
        self.last_call_conditional = None
        self.last_ret_conditional = None

    def is_stack_addr(self, addr):
        return addr < ROM_ADDR_START and addr > ROM_ADDR_START - STACK_SIZE

    def full_addr(self, addr):
        # bank 1 is at BANK_ADDR_START, bank 2 is at BANK_ADDR_START + 0x4000
        if addr < BANK_ADDR_START:
            if addr >= ROM_ADDR_START:
                return addr, 0
            return addr, None

        return addr + BANK_SIZE * (self.rom_bank - 1), self.rom_bank

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

            # we don't have visibility of the current flag status, so in order
            # to determine whether a conditional CALL/RET did actually CALL/RET
            # we need to look whether the stack was written/read
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
            if type == Type.ERROR:
                addr = 0
                b1 = data[1]  # LSB of fifo_full_counter.q
                b2 = data[2]  # Middle byte
                b3 = data[3]  # MSB of fifo_full_counter.q
                val = b1 | (b2 << 8) | (b3 << 16)
            data = data[4:]

            e = self.event(type, val, addr)

            if e.type == Type.FETCH:
                self.flush()

            self.buf.append(e)

            if e.instr == InstructionType.MULTI_PREFIX:
                self.prefix_opcode = e
            elif e.instr == InstructionType.CALL_CONDITIONAL:
                self.last_call_conditional = e
            elif e.instr == InstructionType.RET_CONDITIONAL:
                self.last_ret_conditional = e

        # return unprocessed data, it should be concatenated with the next batch
        return data


def parse_data_thread(
    input_queue, all_events_output, errors_output, ports_output, status_queue
):
    debugpy.listen(("localhost", 5679))  # Different port for child
    parser = PipelineBusParser(errors_queue=errors_output, out_ports_queue=ports_output)

    status_num_input_data = 0
    status_num_empty_queue = 0

    buf = b""
    while True:
        data = input_queue.get()
        if data is None:
            break

        status_num_input_data += 1
        buf += data
        buf = parser.parse(buf)

    buf = parser.parse(buf)
    parser.flush()

    # all_events_output.put(parser.all_events)
    status_queue.put(
        {
            "len_all_events": len(parser.all_events),
            "num_input_data": status_num_input_data,
            "num_errors": parser.status_num_errors,
            "num_out_ports": parser.status_num_out_ports,
            "num_empty_queue": status_num_empty_queue,
            "num_errors_full_buffer": parser.status_num_errors_full_buffer,
            "num_out_ports_full_buffer": parser.status_num_out_ports_full_buffer,
        }
    )


class ParseContext:
    def __init__(self, input_queue, all_events_output, errors_output, ports_output):
        self.input_queue = input_queue
        self.all_events_output = all_events_output
        self.errors_output = errors_output
        self.ports_output = ports_output
        self.status_queue = mp.Queue()
        self.process = mp.Process(
            target=parse_data_thread,
            args=(
                input_queue,
                all_events_output,
                errors_output,
                ports_output,
                self.status_queue,
            ),
        )
        # self.process = threading.Thread(
        #     target=parse_data_thread, args=(input_queue, all_events_output, errors_output, ports_output)
        # )

    def __enter__(self):
        self.process.start()
        print(f'ParseContext pid: {self.process.pid}')
        return self

    def __exit__(self, type, value, traceback):
        self.input_queue.put(None)

        print(f"ParseContext: exit1 {datetime.datetime.now()}")
        self.process.join()
        print(f"ParseContext: exit2 {datetime.datetime.now()}")
        print(self.status_queue.get())

        self.all_events_output.put(None)
        self.errors_output.put(None)
        self.ports_output.put(None)
