import marimo

__generated_with = "0.11.5"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import pandas
    return alt, mo, pandas


@app.cell
def _():
    import sys
    sys.path.append("d3xx")

    # NOTE: expect d3xx/libftd3xx.dylib to be present
    import ftd3xx
    import _ftd3xx_linux as mft
    return ftd3xx, mft, sys


@app.cell(hide_code=True)
def _(ftd3xx, mft):
    import ctypes

    class Ft600Device():
        def __init__(self):
            self.channel = 0

            self.D3XX = ftd3xx.create(0, mft.FT_OPEN_BY_INDEX)
            if self.D3XX is None:
                raise ValueError("ERROR: Please check if another D3XX application is open! Disconnecting both the FPGA + Ft element and then reconnecting them should help.")

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            self.D3XX.close()
            self.D3XX = 0

        def write(self, data: bytes):
            buf = ctypes.create_string_buffer(data)
            bytesWritten = self.D3XX.writePipe(self.channel, buf, len(data))
            return bytesWritten

        def read(self, datalen):
            bytesTransferred = mft.ULONG()
            data = ctypes.create_string_buffer(datalen)
            status = ftd3xx.call_ft(mft.FT_ReadPipeEx, self.D3XX.handle, mft.UCHAR(self.channel), data, mft.ULONG(datalen),
                                    ctypes.byref(bytesTransferred), 1)
            if bytesTransferred.value == 0:
                return None
            return data.raw[:bytesTransferred.value]
    return Ft600Device, ctypes


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""# Collect Data from SHARP PC-G850 System Bus""")
    return


@app.cell(hide_code=True)
def _(mo):
    collect_data_button = mo.ui.run_button(label='Collect Bus Data')
    collect_data_button
    return (collect_data_button,)


@app.cell(hide_code=True)
def _(Ft600Device, collect_data_button, mo):
    mo.stop(not collect_data_button.value)

    import datetime
    import time
    import humanize


    class TransferRateCalculator():
        def __init__(self, callback):
            self.start = datetime.datetime.now()
            self.status_update_time = self.start
            self.status_update_bytes = 0
            self.status_update_packets = 0
            self.callback = callback

        def update(self, data):
            now = datetime.datetime.now()
            if (now - self.status_update_time).total_seconds() > 1:
                rate = (
                    self.status_update_bytes
                    / (now - self.status_update_time).total_seconds()
                )

                msg = f"Received {humanize.naturalsize(rate, binary=True)}/sec {self.status_update_packets} packets/sec"
                self.callback(msg)
                self.status_update_time = now
                self.status_update_bytes = 0
                self.status_update_packets = 0

            if data is not None:
                self.status_update_packets += 1
                self.status_update_bytes += len(data)


    def GetBusData(num_seconds_before_timeout=5):
        # 32KB at a time; Sub-1KB buffers result in FPGA buffer overflow,
        # which results in some events being lost.
        read_size = 2**15

        with Ft600Device() as d:
            # clear input buffer
            for i in range(100):
                bytes = d.read(read_size)

            data = []

            with mo.status.spinner(subtitle="Collecting data ...") as _spinner:
                start = datetime.datetime.now()
                rate_calculator = TransferRateCalculator(
                    lambda rate: _spinner.update(
                        subtitle=f"Collecting data ... {rate}"
                    )
                )

                while True:
                    bytes = d.read(read_size)
                    rate_calculator.update(bytes)

                    now = datetime.datetime.now()
                    if bytes is None:
                        if (
                            now - start
                        ).total_seconds() > num_seconds_before_timeout:
                            break
                        continue
                    start = now
                    data.append(bytes)

            return data

            # print(d.write(b'--'))
            # print(d.write(b'++'))


    data_lines = GetBusData()
    data_concat = b"".join(data_lines)
    mo.md(f"Received {humanize.naturalsize(len(data_concat), binary=True)}, ({len(data_lines)} packets)")
    return (
        GetBusData,
        TransferRateCalculator,
        data_concat,
        data_lines,
        datetime,
        humanize,
        time,
    )


@app.cell
def _():
    # with open('g5500-bank-03.bin', 'wb') as f:
    #     f.write(data_concat)
    return


@app.cell
def _():
    from enum import Enum
    from dataclasses import dataclass
    import struct

    from typing import NamedTuple, Optional, List
    from PIL import Image, ImageDraw
    return (
        Enum,
        Image,
        ImageDraw,
        List,
        NamedTuple,
        Optional,
        dataclass,
        struct,
    )


@app.cell
def _(z80):
    z80.decode(b'\xCB\xE7', 0).status
    return


@app.cell
def _():
    # https://clrhome.org/table/#call
    OPCODE_CALL_PREFIX = set([0xC4, 0xCC, 0xCD, 0xD4, 0xDC, 0xE4, 0xEC, 0xF4, 0xFC])
    # https://clrhome.org/table/#ret
    OPCODE_RET_PREFIX = set([0xC0, 0xC8, 0xC9, 0xD0, 0xD8, 0xE0, 0xE8, 0xF0, 0xF8])
    return OPCODE_CALL_PREFIX, OPCODE_RET_PREFIX


@app.cell
def _(
    Enum,
    IOPort,
    OPCODE_CALL_PREFIX,
    OPCODE_RET_PREFIX,
    Optional,
    data_concat,
    dataclass,
    struct,
):
    class Type(Enum):
        FETCH = "M" # M1: Instruction Fetch
        READ  = "R" # Memory Read
        WRITE = "W" # Memory Write
        IN_PORT  = "r" # IO Read
        OUT_PORT = "w" # IO Write

    @dataclass
    class Event:
        type: Type
        val:  int # uint8
        addr: Optional[int] # uint16
        bank: Optional[int]
        pc: int # uint32
        port: Optional[IOPort]
        instr: Optional[InstructionType]

    class InstructionType(Enum):
        CALL = 1
        RET = 2

    class RawDataParser:
        BANK_ADDR_START = 0xC000
        BANK_SIZE = 0x4000

        def full_addr(self, addr):
            # bank 0 is at BANK_ADDR_START, bank 1 is at BANK_ADDR_START + 0x4000
            if addr < self.BANK_ADDR_START:
                return addr, None

            return addr + self.BANK_SIZE * (self.rom_bank - 1), self.rom_bank

        def parse(self, data):
            self.rom_bank = None

            pc = None
            errors = []
            r = []
        
            offset = 0
            while offset < len(data):
                try:
                    type = Type(chr(data[offset]))
                except ValueError:
                    errors.append(f"Invalid type at offset {offset}: {data[offset]}")
                    offset += 1
                    # raise ValueError(f"Invalid type at index {index}: {i}")
                    continue
        
                val  = struct.unpack("B", data[offset+1:offset+2])[0]
                addr = struct.unpack("<H", data[offset+2:offset+4])[0]
                offset += 4

                instr = None
                port = None
                bank = None
                if type == Type.FETCH:
                    pc, bank = self.full_addr(addr)
                    addr = pc
                    if val in OPCODE_CALL_PREFIX:
                        instr = InstructionType.CALL
                    elif val in OPCODE_RET_PREFIX:
                        instr = InstructionType.RET
                elif type in [Type.READ, Type.WRITE]:
                    addr, bank = self.full_addr(addr)
                elif type in [Type.IN_PORT, Type.OUT_PORT]:
                    addr &= 0xFF
                    try:
                        port = IOPort(addr)

                        if port == IOPort.ROM_BANK:
                            self.rom_bank = val
                        elif port == IOPort.ROM_EX_BANK:
                            self.rom_bank = val & 0x0F
                    except:
                        errors.append(f"Invalid port at offset {offset}: {hex(addr)}")
        
                r.append(Event(type=type, val=val, addr=addr, pc=pc, port=port, instr=instr, bank=bank))
            return r, errors

    parsed, errors = RawDataParser().parse(data_concat)
    len(parsed), errors
    return Event, InstructionType, RawDataParser, Type, errors, parsed


@app.cell
def _(pandas, parsed):
    df = pandas.DataFrame(parsed)
    return (df,)


@app.cell
def _(df):
    df['bank'].unique()
    # df.iloc[1370:]
    return


@app.cell
def _(InstructionType, PerfettoTraceBuilder, Type, parsed):
    def create_perfetto_trace(data):
        builder = PerfettoTraceBuilder()
        last_stack_event = None
        
        ts = 0
        pc = None
        for e in data:
            ts += 1
            if e.type == Type.FETCH:
                pc = e.addr

                if last_stack_event is not None:
                    if last_stack_event.instr == InstructionType.CALL:
                        with builder.add_slice_event(ts, 'begin', hex(pc)).annotation('call') as ann:
                            ann.pointer("pc", pc)
                            ann.pointer("caller", last_stack_event.addr)
                            if e.bank:
                                ann.int('bank', e.bank)
                            if last_stack_event.bank:
                                ann.int('last_bank', last_stack_event.bank)
                    else:
                        builder.add_slice_event(ts, 'end')
        
                    last_stack_event = None

            elif e.type in [Type.IN_PORT, Type.OUT_PORT]:
                name = f'{e.port.name} {hex(e.val)}'
                with builder.add_instant_event(ts, name).annotation('call') as ann:
                    ann.pointer("pc", pc)
                    ann.pointer("port", e.port.value)
                    ann.pointer("val", e.val)

            if e.instr in [InstructionType.CALL, InstructionType.RET]:
                last_stack_event = e

            # if ts > 10000:
            #     break

        return builder

    ppp = create_perfetto_trace(parsed)
    with open('perfetto-test2.pb', 'wb') as ff:
        ff.write(ppp.serialize())
    return create_perfetto_trace, ff, ppp


@app.cell
def _():
    import perfetto_pb2 as perfetto

    class DebugAnnotation:
        def __init__(self, ann):
            self.ann = ann

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            pass
        
        def entry(self, name):
            entry = self.ann.dict_entries.add()
            entry.name = name
            return entry
        
        def pointer(self, name, value):
            entry = self.entry(name)
            entry.pointer_value = value

        def string(self, name, value):
            entry = self.entry(name)
            entry.string_value = value

        def bool(self, name, value):
            entry = self.entry(name)
            entry.bool_value = value

        def int(self, name, value):
            entry = self.entry(name)
            entry.int_value = value

    class TrackEvent:
        def __init__(self, event):
            self.event = event

        def annotation(self, name):
            ann = self.event.debug_annotations.add()
            ann.name = name
            return DebugAnnotation(ann)

    class PerfettoTraceBuilder:
        def __init__(self):
            self.trace = perfetto.Trace()
            self.track_uuid = 0xCA1C
            self.trusted_packet_sequence_id = 0x123
            self.process_uuid = 0x456
            self.pid = 1234
            self.tid = 5678

            self.add_process_descriptor("SHARP PC-G850")
            self.add_thread_descriptor("main")

        def add_process_descriptor(self, process_name: str):
            packet = self.trace.packet.add()
            packet.track_descriptor.uuid = self.process_uuid
            packet.track_descriptor.process.pid = self.pid
            packet.track_descriptor.process.process_name = process_name

        def add_thread_descriptor(self, thread_name: str):
            packet = self.trace.packet.add()
            packet.track_descriptor.uuid = self.track_uuid
            packet.track_descriptor.parent_uuid = self.process_uuid
            packet.track_descriptor.thread.pid = self.pid
            packet.track_descriptor.thread.tid = self.tid
            packet.track_descriptor.thread.thread_name = thread_name

        def add_slice_event(self, timestamp: int, event_type: str, name: str = None):
            packet = self.trace.packet.add()
            packet.timestamp = timestamp

            if event_type == 'begin':
                packet.track_event.type = perfetto.TrackEvent.TYPE_SLICE_BEGIN
                packet.track_event.name = name
            elif event_type == 'end':
                packet.track_event.type = perfetto.TrackEvent.TYPE_SLICE_END
            else:
                raise ValueError("event_type must be either 'begin' or 'end'.")

            packet.track_event.track_uuid = self.track_uuid
            packet.trusted_packet_sequence_id = self.trusted_packet_sequence_id
            return TrackEvent(packet.track_event)

        def add_instant_event(self, timestamp: int, name: str):
            packet = self.trace.packet.add()
            packet.timestamp = timestamp
            packet.track_event.type = perfetto.TrackEvent.TYPE_INSTANT
            packet.track_event.track_uuid = self.track_uuid
            packet.track_event.name = name
            packet.trusted_packet_sequence_id = self.trusted_packet_sequence_id
            return TrackEvent(packet.track_event)

        def serialize(self) -> bytes:
            return self.trace.SerializeToString()
    return DebugAnnotation, PerfettoTraceBuilder, TrackEvent, perfetto


@app.cell
def _(Enum):
    # http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
    class IOPort(Enum):
        LCD_COMMAND = 0x40
        LCD_OUT = 0x41

        ROM_EX_BANK = 0x19
        RAM_BANK = 0x1b
        ROM_BANK = 0x69

        # FIXME: what does it do??
        SHIFT_KEY_INPUT = 0x13 # Read-only

        KEY_INPUT = 0x10 # Read-only
        SET_KEY_STROBE_LO = 0x11 # Write-only
        SET_KEY_STROBE_HI = 0x12 # Write-only

        TIMER = 0x14
        XIN_ENABLED = 0x15
        INTERRUPT_FLAGS = 0x16
        INTERRUPT_MASK = 0x17

        ON_CONTROL_BY_CD_SIGNAL = 0x64
        WAIT_AFTER_M1 = 0x65
        WAIT_AFTER_IO = 0x66
        CPU_CLOCK_MODE = 0x67

        SET_1S_TIMER_PERIOD = 0x68

        GPIO_IO_OUTPUT = 0x18 # 11-pin connector
        GET_GPIO_IO = 0x1f
        GPIO_IO_MODE = 0x60
        SET_PIO_DIRECTION = 0x61
        PIO_REGISTER = 0x62

        # According to https://ver0.sakura.ne.jp/doc/pcg850vuart.html the PC-G850V has different port
        # definitions compared to the PC-G850/PC-G850S.
        UART_FLOW_REGISTER = 0x63
        UART_INPUT_SELECTION = 0x6b
        SET_UART_MODE = 0x6c
        SET_UART_COMMAND = 0x6d
        GET_UART_STATUS = 0x6e
        UART_DATA = 0x6f

        SET_BOOTROM_OFF = 0x1a
        RAM_CE_MODE = 0x1b # 0: CERAM1 (internal RAM), 1: CERAM2 (external RAM on system bus)
        SET_IORESET = 0x1c

        UNKNOWN_1D = 0x1d
        UNKNOWN_1E = 0x1e # battery check mode?
    return (IOPort,)


@app.cell(hide_code=True)
def _():
    def read_rom_banks():
        import os
        import glob
        import re

        def parse_rom(filename):
            m = re.match(r'.*rom([0-9a-fA-F]+).bin', filename)
            bank = int(m.group(1), 16)

            with open(filename, 'rb') as f:
                return bank, f.read()

        banks = {}
        for f in glob.glob('g850-roms/rom*.bin'):
            bank, data = parse_rom(f)
            banks[bank] = data

        return banks

    rom_banks = read_rom_banks()
    return read_rom_banks, rom_banks


@app.cell
def _(rom_banks):
    rom_banks
    return


@app.cell
def _(RomVerifier, rom_banks):
    def make_continuous_rom_image():
        result = b'\x00' * RomVerifier.ROM0_ADDR_START
        for bank in sorted(rom_banks.keys()):
            result += rom_banks[bank]

        with open('g850-roms/base.bin', 'rb') as f:
            base = f.read()
        result = base + result[len(base):]

        # add 0x1000 empty bytes to the end for fake port function creation
        result += b'\x00' * 0x1000

        with open('sharp-pc-g850-full.bin', 'wb') as f:
            f.write(result)

    # make_continuous_rom_image()
    return (make_continuous_rom_image,)


@app.cell(hide_code=True)
def _(IOPort, Type, df, rom_banks):
    class RomVerifier:
        RAM_ADDR_START = 0x100
        ROM0_ADDR_START = 0x8000
        # bank1 and up
        BANK_ADDR_START = 0xC000

        def __init__(self):
            self.rom_bank = None

            # Setting BK'2 to 1 enables the CPU's /CEROM2 signal and disconnects the main ROM.
            # BK'1 and BK'0 are output to the BANK1 and BANK0 terminals of the 40-pin system bus.
            self.ex_bank = None

            # RAM CE signal selection:
            # 0: CERAM1 (internal RAM)
            # 1: CERAM2 (external RAM on system bus)
            self.ram_bank = None

            self.ram = ['-'] * 0x8000

            self.i = 0

        def get_rom_bank(self, bank):
            assert(self.rom_bank is not None)
            if self.rom_bank != bank:
                raise ValueError(f"Expected rom_bank {hex(self.rom_bank)}, got {hex(bank)}")

        def get_ex_bank(self, bank):
            assert(self.ex_bank is not None)
            if self.ex_bank != bank:
                raise ValueError(f"Expected ex_bank {self.ex_bank}, got {bank}")

        def get_ram_bank(self, bank):
            assert(self.ram_bank is not None)
            if self.ram_bank != bank:
                raise ValueError(f"Expected ram_bank {hex(self.ram_bank)}, got {hex(bank)}")

        def set_rom_bank(self, bank):
            if self.rom_bank != bank:
                # print(f"Setting rom_bank to {hex(bank)}")
                pass
            self.rom_bank = bank

        def set_ex_bank(self, bank):
            if self.ex_bank != bank:
                # print(f"Setting ex_bank to {hex(bank)}")
                pass
            self.ex_bank = bank

        def set_ram_bank(self, bank):
            if self.ram_bank != bank:
                # print(f"Setting ram_bank to {hex(bank)}")
                pass
            self.ram_bank = bank

        def write(self, addr, val):
            if addr > self.RAM_ADDR_START and addr < self.ROM0_ADDR_START:
                self.ram[addr] = val
            if addr > self.ROM0_ADDR_START:
                raise ValueError(f"Unexpected write to ROM region: {hex(addr)}: {hex(val)}")

        def read(self, addr, val):
            if addr > self.ROM0_ADDR_START and addr < self.BANK_ADDR_START:
                expect = rom_banks[0][addr - self.ROM0_ADDR_START]
                if val != expect:
                    print(f"ex_bank({self.ex_bank}): mismatch at {hex(addr)}: {hex(val)} != {hex(expect)}")

            if addr > self.BANK_ADDR_START:
                expect = rom_banks[self.rom_bank][addr - self.BANK_ADDR_START]
                if val != expect:
                    print(f"rom_bank({self.rom_bank}): mismatch at {hex(addr)}: {hex(val)} != {hex(expect)}")

    def verify_rom_memory():
        verifier = RomVerifier()

        # IO Port documentation:
        # http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
        for r in df.iloc[0:1000000].itertuples():
            index = r.Index
            # print(r.type, r.val, r.addr)

            try:
                port = IOPort(r.addr) if r.type in [Type.IN_PORT, Type.OUT_PORT] else None
            except ValueError:
                continue

            if r.type == Type.WRITE:
                verifier.write(r.addr, r.val)
            elif r.type in [Type.READ, Type.FETCH]:
                verifier.read(r.addr, r.val)
            elif r.type == Type.IN_PORT:
                match port:
                    case IOPort.ROM_EX_BANK:
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        verifier.get_rom_bank(rom_bank)
                        verifier.get_ex_bank(ex_bank)
                    case IOPort.RAM_BANK:
                        verifier.get_ram_bank(r.val)
                    case IOPort.ROM_BANK:
                        verifier.get_rom_bank(r.val)
            elif r.type == Type.OUT_PORT:
                match port:
                    case IOPort.ROM_EX_BANK:
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        verifier.set_rom_bank(rom_bank)
                        verifier.set_ex_bank(ex_bank)
                    case IOPort.RAM_BANK:
                        verifier.set_ram_bank(r.val)
                    case IOPort.ROM_BANK:
                        verifier.set_rom_bank(r.val)
            else:
                raise ValueError(f"Unknown type {r.type}")

        return verifier

    # verifier = verify_rom_memory()
    return RomVerifier, verify_rom_memory


@app.cell(hide_code=True)
def _(df, mo):
    df_range = mo.md('''
    {start}

    {length}
    ''').batch(
    length=mo.ui.number(start=1, stop=1000000, value=100000, step=1, label='Length'),
    start=mo.ui.number(start=0, stop=df.shape[0], step=1, label='Start'),
    )
    df_range
    return (df_range,)


@app.cell(hide_code=True)
def _(alt, df, df_range, mo, pandas):
    def plot_df_addr(df):
        full_scale = alt.Scale(domain=[0x0, 0x10000])
        bars = alt.Chart(df).transform_aggregate(
            count='count()', groupby=['addr', 'type']
        ).transform_calculate(
            truncated_count="min(datum.count, 20)"
        ).mark_bar().encode(
            x=alt.X('addr:Q', title='Address (Hex)',
                axis=alt.Axis(labelExpr="format(datum.value, 'X')"),  # Format as hex
                scale=full_scale),
            y=alt.Y('truncated_count:Q', title='Number of Events'),
            color='type:N',
            tooltip=[alt.Tooltip('addr:Q', title='Address', format='X'), 'type:N', alt.Tooltip('count()', title='Count')]
        )

        rules = alt.Chart(pandas.DataFrame({'addr': [0x8000, 0xC000]})).mark_rule(
            color='blue',
            strokeWidth=1
        ).encode(
            x=alt.X('addr:Q', scale=full_scale),
        )

        # Combine bars and rules
        return (bars + rules).properties(title='Memory Bus Events by Address and Type')

    df_for_plot = df.iloc[df_range.value['start']:df_range.value['start'] + df_range.value['length']]
    mo.ui.altair_chart(plot_df_addr(df_for_plot))
    return df_for_plot, plot_df_addr


@app.cell
def _():
    from z80dis import z80
    z80.disasm(b'\xed\xb0', 10)
    return (z80,)


@app.cell
def _(df, df_valh):
    df_valh(df)
    return


@app.cell
def _(Type, df, z80):
    class ProcessBusEvents:
        def decode(self):
            disasm = z80.disasm(self.buf, self.pc)
            if len(disasm):
                print(f'{hex(self.pc)}: {disasm}')
                self.i += 1
                if self.i > 1000:
                    return True
            return False

        def process_bus_events(self, df):
            self.pc = None
            self.buf = b''
            self.i = 0
                
            for r in df.itertuples():
                if r.type == Type.FETCH:
                    self.pc = r.addr
                    self.buf = b''
                    if self.pc == 0xc000:
                        print('<'*40)
                    print(f'  {hex(self.pc)} {hex(r.val)}')
                    self.buf += bytes([r.val])
                    if self.decode():
                        break
                elif r.type == Type.READ:
                    print(f'  {hex(self.pc)} {hex(r.val)}')
                    self.buf += bytes([r.val])
                    if self.decode():
                        break

    ProcessBusEvents().process_bus_events(df)
    return (ProcessBusEvents,)


@app.cell
def _(df):
    df
    return


@app.cell
def _(Type):
    def df_valh(df):
        df2 = df.copy()
        df2['addrh'] = df2['addr'].apply(lambda x: hex(x))
        df2['valh'] = df2['val'].apply(lambda x: hex(x))
        return df2

    def io_df(df):
        df2 = df[df['type'].isin([Type.IN_PORT, Type.OUT_PORT])].copy()
        return df_valh(df2)
    return df_valh, io_df


@app.cell(hide_code=True)
def _(IOPort, SED1560, SED1560Parser, pandas):
    def parse_lcd_commands(df):
        commands = []
        for r in df.itertuples():
            parsed = None
            if r.port == IOPort.LCD_COMMAND:
                parsed = SED1560Parser.parse_out40(r.val)
            elif r.port == IOPort.LCD_OUT:
                parsed = SED1560Parser.parse_out41(r.val)
            else:
                parsed = SED1560.Unknown(addr=r.port.value, value=r.val)
            commands.append(parsed)

        processed = []
        i = 0
        while i < len(commands):
            match commands[i:i+3]:
                # for some reason InitialDisplayLine is always between two SetColumnPart commands
                case [SED1560.SetColumnPart(is_high=False, value=low), cmd,
                      SED1560.SetColumnPart(is_high=True, value=high)]:
                    processed.append(SED1560.SetColumn(value=low | high))
                    processed.append(cmd)
                    i += 3
                case [SED1560.SetColumnPart(is_high=True, value=high), cmd,
                      SED1560.SetColumnPart(is_high=False, value=low)]:
                    processed.append(SED1560.SetColumn(value=low | high))
                    processed.append(cmd)
                    i += 3
                case _:
                    processed.append(commands[i])
                    i += 1
        return processed

    def get_parsed_lcd_commands_df(processed):
        result = []
        for index, parsed in enumerate(processed):
            parsed_type = type(parsed).__name__
            # if CmdA, then get type from parsed.cmd
            if parsed_type == 'CmdA':
                parsed_type = parsed.cmd.name
            if parsed_type == 'Unknown':
                parsed_type = IOPort(parsed.addr).name

            result.append({
                "index": index,
                "type": parsed_type,
                **vars(parsed)
            })
        return pandas.DataFrame(result)
    return get_parsed_lcd_commands_df, parse_lcd_commands


@app.cell
def _(IOPort, df, get_parsed_lcd_commands_df, parse_lcd_commands):
    # # FIXME: what does it do??
    # SHIFT_KEY_INPUT = 0x13 # Read-only

    # KEY_INPUT = 0x10 # Read-only
    # SET_KEY_STROBE_LO = 0x11 # Write-only
    # SET_KEY_STROBE_HI = 0x12 # Write-only


    parsed_lcd_commands = parse_lcd_commands(
        df[
            df["port"].isin(
                [
                    IOPort.LCD_COMMAND,
                    IOPort.LCD_OUT,
                    IOPort.KEY_INPUT,
                    IOPort.SHIFT_KEY_INPUT,
                    IOPort.SET_KEY_STROBE_LO,
                    IOPort.SET_KEY_STROBE_HI,
                ]
            )
        ]
        .copy()
        .reset_index(drop=True)
    )
    parsed_lcd_commands_df = get_parsed_lcd_commands_df(parsed_lcd_commands)
    return parsed_lcd_commands, parsed_lcd_commands_df


@app.cell
def _():
    # parsed_lcd_commands_filtered
    return


@app.cell
def _():
    # Key Code table: https://ver0.sakura.ne.jp/doc/pcg800iocs.html
    # If you press the SHIFT key at the same time, the most significant bit becomes 1.
    return


@app.cell(hide_code=True)
def _(SED1560):
    # TODO: use info from https://www.akiyan.com/pc-g850_technical_data
    # to implement the remaining commands.
    class SED1560Intepreter:
        # VRAM: 166 x 65 bits (last page is 1-bit high)

        # 8 pages of 8 lines, last 9th page of 1 line
        PAGE_HEIGHT = 8  # pixels
        NUM_PAGES = 9

        LCD_WIDTH = 166
        LCD_HEIGHT = 8

        # When the Select ADC command is used to select inverse display operation, the column address decoder inverts the relationship between the RAM column data and the display segment outputs.

        def __init__(self):
            self.page = 0
            self.col = 0  # x coordinate

            self.com0 = 0  # Initial Display Line register, 6 bits

            self.display_on = None
            self.power_on = None
            self.contrast = None
            self.scanning_direction = None
            self.segments_display_mode = None

            # Initialize VRAM as a 2D array of bytes (each row is a list of LCD_WIDTH bytes)
            self.vram = [
                [0 for _ in range(self.LCD_WIDTH)] for _ in range(self.LCD_HEIGHT)
            ]

        def eval(self, cmd):
            match cmd:
                case SED1560.InitialDisplayLine(value=com0):
                    self.com0 = com0
                case SED1560.SetColumn(value=x):
                    self.col = x
                case SED1560.SetPageAddress(value=page):
                    self.page = page
                case SED1560.VRAMWrite(value=x):
                    self.vram[self.page][self.col] = x
                    # The counter automatically stops at the highest address, A6H.
                    self.col = min(self.col + 1, self.LCD_WIDTH - 1)
                case SED1560.SetCommonSegmentOutput(scanning_direction=direction, case=case):
                    self.scanning_direction = direction
                case SED1560.Contrast(contrast=contrast):
                    self.contrast = contrast
                case SED1560.PowerOn(on=on):
                    self.power_on = on
                case SED1560.PowerOnComplete():
                    pass
                case SED1560.CmdA(cmd=SED1560.CmdAType.DISPLAY_ON, value=value):
                    self.display_on = value
                case SED1560.CmdA(cmd=SED1560.CmdAType.SEGMENTS_DISPLAY_MODE, value=value):
                    self.segments_display_mode = value
                case SED1560.Unknown(addr=addr, value=value):
                    pass
                case _:
                    raise ValueError(f"Unhandled command: {cmd}")
    return (SED1560Intepreter,)


@app.cell(hide_code=True)
def _(lcd_commands_range):
    def filtered_lcd_commands(df):
        opts = lcd_commands_range
        df = df.iloc[
            opts.value["start"] : opts.value["start"] + opts.value["length"]
        ].copy()
        # use opts['show_initial_display_line'] to filter out InitialDisplayLine
        df = df[~(df["type"] == "InitialDisplayLine")] if not opts.value["show_initial_display_line"] else df

        return df
    return (filtered_lcd_commands,)


@app.cell(hide_code=True)
def _(mo, parsed_lcd_commands_df):
    def get_lcd_commands_range(df):
        return mo.md("""
        {start}

        {length}

        {show_initial_display_line}
        """).batch(
            length=mo.ui.number(
                start=1,
                stop=df.shape[0],
                value=df.shape[0],
                step=1,
                label="Length",
            ),
            start=mo.ui.number(
                start=0, stop=df.shape[0], step=1, label="Start"
            ),
            show_initial_display_line=mo.ui.checkbox(value=True, label="Show Initial Display Line"),
        )

    lcd_commands_range = get_lcd_commands_range(parsed_lcd_commands_df)
    lcd_commands_range
    return get_lcd_commands_range, lcd_commands_range


@app.cell
def _(SED1560Intepreter, draw_vram2, parsed_lcd_commands_filtered):
    display = SED1560Intepreter()
    for cmd in parsed_lcd_commands_filtered:
        display.eval(cmd)

    draw_vram2(display.vram)
    return cmd, display


@app.cell(hide_code=True)
def _(alt, filtered_lcd_commands, mo, parsed_lcd_commands_df):
    def plot_parsed_lcd_commands(df):
        min_index = df['index'].min()
        max_index = df['index'].max()
        x_scale = alt.Scale(domain=(min_index, max_index))

        key_columns = ['KEY_INPUT', 'SHIFT_KEY_INPUT', 'SET_KEY_STROBE_LO', 'SET_KEY_STROBE_HI']

        events_points = (
            alt.Chart(
                df[
                    ~df["type"].isin(
                        [
                            "InitialDisplayLine",
                            "SetColumnPart",
                            "SetColumn",
                            "SetPageAddress",
                            "VRAMWrite",
                            *key_columns,
                        ]
                    )
                ]
            )
            .mark_point()
            .encode(
                x=alt.X('index:Q', scale=x_scale),
                y="type:N",
                color="type:N",
                tooltip=["index", "type", "value"],
            )
        )

        key_charts = []
        for key in key_columns:
            chart = (
                alt.Chart(df[df["type"].isin([key])])
                .mark_point()
                .encode(
                    x=alt.X('index:Q', scale=x_scale),
                    y=alt.Y("value:Q", title="Value"),
                    color="type:N",
                    tooltip=["index", "type", "value"],
                )
                .properties(title=key)
            )
            key_charts.append(chart)


        vram_write = (
            alt.Chart(df[df["type"].isin(["VRAMWrite"])])
            .mark_point()
            .encode(
                x=alt.X('index:Q', scale=x_scale),
                y=alt.Y("value:Q", title="Value"),
                color="type:N",
                tooltip=["index", "type", "value"],
            )
            .properties(title="VRAM Write")
        )

        # also add SetColumnPart as two separate charts for is_high=False and is_high=True
        set_column_high = (
            alt.Chart(df[df["type"] == "SetColumn"])
            .mark_point()
            .encode(
                x=alt.X('index:Q', scale=x_scale),
                y=alt.Y("value:Q", title="Value"),
                # color="is_high:N",
                tooltip=["index", "type", "value"],
            )
            .properties(title="Set Column")
        )

        set_page_address = (
            alt.Chart(df[df["type"] == "SetPageAddress"])
            .mark_point()
            .encode(
                x=alt.X('index:Q', scale=x_scale),
                y="value:Q",
                color="type:N",
                tooltip=["index", "type", "value"],
            )
            .properties(title="Set Page Address")
        )

        initial_display_line = (
            alt.Chart(df[df["type"] == "InitialDisplayLine"])
            .mark_point()
            .encode(
                x=alt.X('index:Q', scale=x_scale),
                y="value:Q",
                color="type:N",
                tooltip=["index", "type", "value"],
            )
            .properties(title="Initial Display Line")
        )

        return alt.vconcat(
            events_points,
            *key_charts,
            vram_write,
            set_column_high,
            set_page_address,
            initial_display_line,
        )


    mo.ui.altair_chart(plot_parsed_lcd_commands(filtered_lcd_commands(parsed_lcd_commands_df)))
    return (plot_parsed_lcd_commands,)


@app.cell
def _():
    # 6641:6641+410
    # mo.ui.dataframe(filtered_lcd_commands(parsed_lcd_commands_df), page_size=20)
    return


@app.cell(hide_code=True)
def _(Enum, dataclass):
    class SED1560:
        class CmdAType(Enum):
            SET_RAM_SEGMENT_OUTPUT = 0x0  # 0: Normal, 1: Inverse
            DISPLAY_ON = 0xE              # 0: Off, 1: On
            DISPLAY_MODE = 0x6            # 0: Normal, 1: Inverse
            SEGMENTS_DISPLAY_MODE = 0x4   # 0: Normal, 1: All display segments On
            LCD_CONTROLLER_DUTY1 = 0x8    # See Table 5.3
            LCD_CONTROLLER_DUTY2 = 0xA

        @dataclass
        class InitialDisplayLine:
            value: int

        @dataclass
        class Contrast:
            contrast: int

        @dataclass
        class PowerOn:
            on: bool

        @dataclass
        class PowerOnComplete:
            pass

        @dataclass
        class SetPageAddress:
            value: int

        @dataclass
        class CmdA:
            cmd: 'SED1560.CmdAType'
            value: int

        @dataclass
        class SetCommonSegmentOutput:
            scanning_direction: int
            case: int

        @dataclass
        class SetColumnPart:
            is_high: bool  # True if updating the high nibble, False for low nibble
            value: int

        @dataclass
        class SetColumn:
            value: int

        @dataclass
        class VRAMWrite:
            value: int

        @dataclass
        class Unknown:
            addr: int
            value: int

    class SED1560Parser:
        @staticmethod
        def parse_out40(x: int):
            high = (x & 0xF0) >> 4
            low = x & 0x0F

            if (x >> 6) == 1:
                # Initial Display Line command
                com0 = x & 0x3F
                return SED1560.InitialDisplayLine(value=com0)
            elif (x >> 5) == 0b100:
                # Contrast command: lower 5 bits hold the contrast value
                contrast = x & 0b11111
                return SED1560.Contrast(contrast=contrast)
            elif (x >> 1) == 0b10010:
                # PSU On command: LSB determines state (0 or 1)
                on = bool(x & 0b1)
                return SED1560.PowerOn(on=on)
            elif x == 0b11101101:
                # Power on complete command
                return SED1560.PowerOnComplete()
            elif high == 0xB:
                # Set Page Address command
                return SED1560.SetPageAddress(value=low)
            elif high == 0xA:
                #  A: low nibble split into command and value
                command_a = SED1560.CmdAType(low & 0b1110)
                value = low & 0b1
                return SED1560.CmdA(cmd=command_a, value=value)
            elif high == 0xC:
                # Set Common and Segment Output Status Register command
                scanning_direction = low >> 3
                case = low & 0b111
                if case != 0b111:
                    raise ValueError(
                        f"Unhandled case: {bin(case)}, only SEG166 is supported"
                    )
                return SED1560.SetCommonSegmentOutput(
                    scanning_direction=scanning_direction,
                    case=case
                )
            elif high in [0x0, 0x1]:
                # Column address command: update column based on high/low nibble.
                if high:  # high nibble update
                    col = low << 4
                    is_high = True
                else:     # low nibble update
                    col = low
                    is_high = False
                return SED1560.SetColumnPart(is_high=is_high, value=col)
            else:
                raise SED1560.Unknown(addr=0x40, value=x)

        @staticmethod
        def parse_out41(x: int):
            return SED1560.VRAMWrite(value=x)
    return SED1560, SED1560Parser


@app.cell
def _(SED1560Parser):
    SED1560Parser.parse_out40(0xaf)
    return


@app.cell
def _(lcd_commands_range, parsed_lcd_commands):
    parsed_lcd_commands_filtered = parsed_lcd_commands[lcd_commands_range.value['start']: lcd_commands_range.value['start'] + lcd_commands_range.value['length']]
    return (parsed_lcd_commands_filtered,)


@app.cell(hide_code=True)
def _(Image, ImageDraw):
    def draw_vram2(vram, zoom=4):
        off_color = (0, 0, 0)
        on_color = (0, 255, 0)

        img_width = len(vram[0]) * zoom
        img_height = len(vram) * 8 * zoom
        image = Image.new("RGB", (img_width, img_height), off_color)
        draw = ImageDraw.Draw(image)

        for row in range(len(vram)):
            for col in range(len(vram[row])):
                byte = vram[row][col]
                for bit in range(8):
                    pixel_state = (byte >> bit) & 1
                    color = on_color if pixel_state else off_color

                    dx = col
                    dy = row * 8 + bit
                    draw.rectangle([dx * zoom, dy * zoom, dx * zoom + zoom - 1, dy * zoom + zoom - 1], fill=color)

        return image
    return (draw_vram2,)


if __name__ == "__main__":
    app.run()
