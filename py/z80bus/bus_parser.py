from __future__ import annotations

import datetime
import multiprocessing as mp
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from types import TracebackType


# http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
class IOPort(Enum):
    LCD_COMMAND = 0x40
    LCD_OUT = 0x41

    ROM_EX_BANK = 0x19
    RAM_BANK = 0x1B
    ROM_BANK = 0x69

    # seems to be used both for Shift key and CE0/CE1 rom banks?
    SHIFT_KEY_INPUT = 0x13  # Read-only

    KEY_INPUT = 0x10  # Read-only
    SET_KEY_STROBE_LO = 0x11  # Write-only
    SET_KEY_STROBE_HI = 0x12  # Write-only

    SET_1S_TIMER_PERIOD = 0x68
    TIMER = 0x14

    XIN_ENABLED = 0x15
    INTERRUPT_FLAGS = 0x16
    INTERRUPT_MASK = 0x17

    ON_CONTROL_BY_CD_SIGNAL = 0x64
    WAIT_AFTER_M1 = 0x65
    WAIT_AFTER_IO = 0x66
    CPU_CLOCK_MODE = 0x67

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
    RAM_CE_MODE = 0x1B  # 0: CERAM1 (internal RAM), 1: CERAM2 (external RAM on system bus)
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
    addr: int | None = None  # uint16
    pc: int | None = None  # uint32
    bank: int | None = None
    port: IOPort | None = None
    instr: InstructionType | None = None

    # convert to string, printing values in hex
    def stubname(self):
        # print the creation function for unittest
        if self.type == Type.FETCH:
            return f"fetch(0x{self.val:02X}, 0x{self.addr:04X})"
        if self.type == Type.READ:
            return f"read(0x{self.val:02X}, 0x{self.addr:04X})"
        if self.type == Type.WRITE:
            return f"write(0x{self.val:02X}, 0x{self.addr:04X})"
        if self.type == Type.IN_PORT:
            return f"in_port(0x{self.val:02X}, IOPort.{self.port.name})"
        if self.type == Type.OUT_PORT:
            return f"out_port(0x{self.val:02X}, IOPort.{self.port.name})"
        if self.type == Type.READ_STACK:
            return f"read_stack(0x{self.val:02X}, 0x{self.addr:04X})"
        if self.type == Type.WRITE_STACK:
            return f"write_stack(0x{self.val:02X}, 0x{self.addr:04X})"
        return f"{self.type.value} v:{self.val:02X} a:{self.addr:04X}"


@dataclass
class InstructionState:
    """Track contextual information for event interpretation."""

    prefix_event: Event | None = None
    last_call_conditional: Event | None = None
    last_ret_conditional: Event | None = None

    def reset_all(self) -> None:
        self.prefix_event = None
        self.reset_conditionals()

    def reset_conditionals(self) -> None:
        self.last_call_conditional = None
        self.last_ret_conditional = None


# for some opcodes the processor will set M1 low twice, if unhandled we can misclassify the second M1 as CALL/RET
OPCODE_MULTI_PREFIX = {0xCB, 0xDD, 0xED, 0xFD}
# https://clrhome.org/table/#call
OPCODE_CALL_PREFIX = {0xCD}
OPCODE_CONDITIONAL_CALL_PREFIX = {0xC4, 0xCC, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC}
# https://clrhome.org/table/#ret
OPCODE_RET_PREFIX = {0xC9}
OPCODE_CONDITIONAL_RET_PREFIX = {0xC0, 0xC8, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8}

ROM_ADDR_START = 0x8000
BANK_ADDR_START = 0xC000
BANK_SIZE = 0x4000
# not sure how big the stack is, this area is also used for variable storage
STACK_SIZE = 0x400


# if instruction_addr >= BANK_ADDR_START then try to determine bank number
def bank_number_for_address(instruction_addr):
    if instruction_addr < BANK_ADDR_START:
        if instruction_addr >= ROM_ADDR_START:
            return 0
        return None

    return 1 + (instruction_addr - BANK_ADDR_START) // BANK_SIZE


def extend_address(instruction_addr, addr):
    if addr < BANK_ADDR_START:
        return addr
    bank = bank_number_for_address(instruction_addr)
    if bank is None or bank == 0:
        return addr
    return addr + BANK_SIZE * (bank - 1)


def _decode_event_fields(raw: memoryview) -> tuple[Type, int, int]:
    """Decode the type, value and address from a 4-byte event payload.

    Each event generated by the hardware is transmitted as four bytes:
    the type (encoded as an ASCII character), a single byte value and a
    little-endian address.  Error packets are an exception — the last
    three bytes form a 24-bit counter and there is no address payload.
    """

    if len(raw) < 4:
        raise ValueError("Event payload must be 4 bytes long")

    try:
        event_type = Type(chr(raw[0]))
    except ValueError as exc:
        raise ValueError from exc

    if event_type == Type.ERROR:
        value = raw[1] | (raw[2] << 8) | (raw[3] << 16)
        addr = 0
    else:
        value = raw[1]
        addr = int.from_bytes(raw[2:4], "little")

    return event_type, value, addr


class BaseBusParser:
    rom_bank: int | None
    pc: int | None

    def __init__(self) -> None:
        self.rom_bank = None
        self.pc = None
        self._instruction_state = InstructionState()

    def is_stack_addr(self, addr: int) -> bool:
        return addr < ROM_ADDR_START and addr > ROM_ADDR_START - STACK_SIZE

    def full_addr(self, addr: int) -> tuple[int, int | None]:
        if addr < BANK_ADDR_START:
            if addr >= ROM_ADDR_START:
                return addr, 0
            return addr, None

        if self.rom_bank is None:
            # This shouldn't happen in normal operation, but we need to handle it for type safety
            raise ValueError("rom_bank is None when trying to calculate full address for banked memory")

        return addr + BANK_SIZE * (self.rom_bank - 1), self.rom_bank

    def _create_event(
        self,
        event_type: Type,
        value: int,
        addr: int,
        *,
        on_invalid_port: Callable[[int], None],
    ) -> Event:
        state = self._instruction_state

        if state.prefix_event is not None and event_type == Type.FETCH:
            event_type = Type.READ
            state.prefix_event = None

        instr = None
        port = None
        bank = None

        if event_type == Type.FETCH:
            state.reset_all()
            self.pc, bank = self.full_addr(addr)
            addr = self.pc
            if value in OPCODE_MULTI_PREFIX:
                instr = InstructionType.MULTI_PREFIX
            elif value in OPCODE_CALL_PREFIX:
                instr = InstructionType.CALL
            elif value in OPCODE_CONDITIONAL_CALL_PREFIX:
                instr = InstructionType.CALL_CONDITIONAL
            elif value in OPCODE_RET_PREFIX:
                instr = InstructionType.RET
            elif value in OPCODE_CONDITIONAL_RET_PREFIX:
                instr = InstructionType.RET_CONDITIONAL
        elif event_type in (Type.READ, Type.WRITE):
            addr, bank = self.full_addr(addr)

            if self.is_stack_addr(addr):
                if event_type == Type.READ:
                    event_type = Type.READ_STACK
                    if state.last_ret_conditional is not None:
                        state.last_ret_conditional.instr = InstructionType.RET
                else:
                    event_type = Type.WRITE_STACK
                    if state.last_call_conditional is not None:
                        state.last_call_conditional.instr = InstructionType.CALL

        elif event_type in (Type.IN_PORT, Type.OUT_PORT):
            addr &= 0xFF
            try:
                port = IOPort(addr)

                if port == IOPort.ROM_BANK:
                    self.rom_bank = value
                elif port == IOPort.ROM_EX_BANK:
                    self.rom_bank = value & 0x0F
            except ValueError:
                on_invalid_port(addr)

        event = Event(
            type=event_type,
            val=value,
            addr=addr,
            pc=self.pc,
            port=port,
            instr=instr,
            bank=bank,
        )

        self._record_instruction_event(event)

        return event

    def _record_instruction_event(self, event: Event) -> None:
        instr = event.instr
        if instr == InstructionType.MULTI_PREFIX:
            self._instruction_state.prefix_event = event
        elif instr == InstructionType.CALL_CONDITIONAL:
            self._instruction_state.last_call_conditional = event
        elif instr == InstructionType.RET_CONDITIONAL:
            self._instruction_state.last_ret_conditional = event


# like BusParser, but only parses type, val, addr
class SimpleBusParser:
    def parse(self, data):
        r = []
        offset = 0
        view = memoryview(data)
        while offset + 4 <= len(view):
            chunk = view[offset : offset + 4]
            try:
                type, val, addr = _decode_event_fields(chunk)
            except ValueError:
                offset += 1
                continue

            offset += 4

            r.append(Event(type=type, val=val, addr=addr))
        return r


class BusParser(BaseBusParser):
    def __init__(self) -> None:
        super().__init__()

    def parse(self, data):
        errors = []
        events = []

        self._instruction_state.reset_all()

        offset = 0
        view = memoryview(data)
        while offset + 4 <= len(view):
            chunk = view[offset : offset + 4]
            try:
                event_type, value, addr = _decode_event_fields(chunk)
            except ValueError:
                errors.append(f"Invalid type at offset {offset}: {data[offset]}")
                offset += 1
                continue

            current_offset = offset
            offset += 4

            event = self._create_event(
                event_type,
                value,
                addr,
                on_invalid_port=lambda port, off=current_offset: errors.append(
                    f"Invalid port at offset {off}: {hex(port)}"
                ),
            )
            events.append(event)

        if offset != len(data):
            errors.append("Trailing data")
        return events, errors


class PipelineBusParser(BaseBusParser):
    def __init__(self, errors_queue, out_ports_queue, save_all_events=False):
        super().__init__()
        self.save_all_events = save_all_events
        self.status_num_errors = 0
        self.errors_queue = errors_queue
        self.status_num_out_ports = 0
        self.out_ports_queue = out_ports_queue

        # if we start recording before the calculator is turned on then it'll
        # fetch the rom_bank number before trying to jump there. Otherwise
        # we'll likely crash in the full_addr function.
        self.rom_bank = 0
        self.pc = None
        self.errors = []

        self.all_events = []
        # buffer for the current instruction
        self.buf = []

    def stats(self):
        return {
            "len_all_events": len(self.all_events),
            "num_out_ports": self.status_num_out_ports,
            "num_errors": self.status_num_errors,
        }

    def flush(self):
        for e in self.buf:
            if self.save_all_events:
                self.all_events.append(e)

            if e.type in [Type.IN_PORT, Type.OUT_PORT]:
                self.status_num_out_ports += 1
                if self.out_ports_queue is not None:
                    self.out_ports_queue.put(e)
        self.buf = []

        for e in self.errors:
            self.status_num_errors += 1
            self.errors_queue.put(e)
        self.errors = []

        self._instruction_state.reset_conditionals()


    def event(self, event_type, value, addr):
        return self._create_event(
            event_type,
            value,
            addr,
            on_invalid_port=lambda port: self.errors.append(f"Invalid port at {hex(port)}"),
        )

    def parse(self, full_data):
        data = memoryview(full_data)
        while len(data) >= 4:
            chunk = data[:4]
            try:
                event_type, value, addr = _decode_event_fields(chunk)
            except ValueError:
                self.errors.append(f"Invalid type at offset {0}: {data[0]}")
                data = data[1:]
                continue
            data = data[4:]

            event = self.event(event_type, value, addr)

            if event.type == Type.FETCH:
                self.flush()

            self.buf.append(event)
            self._record_instruction_event(event)

        # return unprocessed data, it should be concatenated with the next batch
        return bytes(data)


def parse_data_thread(
    input_queue, all_events_output, errors_output, ports_output, status_queue
):
    parser = PipelineBusParser(errors_queue=errors_output, out_ports_queue=ports_output)

    status_num_input_data = 0
    status_num_empty_queue = 0

    buf = bytearray()
    while True:
        data = input_queue.get()
        if data is None:
            break

        status_num_input_data += 1
        buf.extend(data)
        buf = bytearray(parser.parse(buf))

    buf = bytearray(parser.parse(buf))
    parser.flush()

    # all_events_output.put(parser.all_events)
    status = parser.stats()
    status.update(
        {
            "num_input_data": status_num_input_data,
            "num_empty_queue": status_num_empty_queue,
        }
    )
    status_queue.put(status)


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
        print(f"ParseContext pid: {self.process.pid}")
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.input_queue.put(None)

        print(f"ParseContext: exit1 {datetime.datetime.now()}")
        self.process.join()
        print(f"ParseContext: exit2 {datetime.datetime.now()}")
        print(self.status_queue.get())

        self.all_events_output.put(None)
        self.errors_output.put(None)
        self.ports_output.put(None)
