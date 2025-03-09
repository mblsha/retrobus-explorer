import marimo

__generated_with = "0.11.17"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import altair as alt
    import pandas
    import datetime
    import time
    import humanize
    import time
    import asyncio
    import websockets
    import queue
    from contextlib import asynccontextmanager
    return (
        alt,
        asynccontextmanager,
        asyncio,
        datetime,
        humanize,
        mo,
        pandas,
        queue,
        time,
        websockets,
    )


@app.cell
def _():
    from enum import Enum
    from dataclasses import dataclass
    import struct

    from typing import NamedTuple, Optional, List
    return Enum, List, NamedTuple, Optional, dataclass, struct


@app.cell
def _():
    import sys
    sys.path.append("d3xx")

    # NOTE: expect d3xx/libftd3xx.dylib to be present
    import ftd3xx
    import _ftd3xx_linux as mft

    import ctypes
    return ctypes, ftd3xx, mft, sys


@app.cell(hide_code=True)
def _(ctypes, ftd3xx, mft):
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

        # benchmarks:
        # 100: ~5000 packets/sec, ~7MB/sec when mashing buttons; up to ~46% CPU load
        def read(self, datalen):
            bytesTransferred = mft.ULONG()
            data = ctypes.create_string_buffer(datalen)
            status = ftd3xx.call_ft(mft.FT_ReadPipeEx, self.D3XX.handle, mft.UCHAR(self.channel), data, mft.ULONG(datalen),
                                    ctypes.byref(bytesTransferred), 100)
            if bytesTransferred.value == 0:
                return None
            return data.raw[:bytesTransferred.value]
    return (Ft600Device,)


@app.cell
def _():
    from contextlib import ExitStack
    return (ExitStack,)


@app.cell
def _():
    import multiprocessing as mp
    import threading
    return mp, threading


@app.cell
def _():
    from z80bus import bus_parser
    from z80bus import sed1560
    from z80bus import key_matrix

    IOPort = bus_parser.IOPort
    Type = bus_parser.Type
    InstructionType = bus_parser.InstructionType
    return IOPort, InstructionType, Type, bus_parser, key_matrix, sed1560


@app.cell
def _():
    # myftdi = Ftdi()
    # myftdi.open_from_url(url='ftdi://ftdi:2232:FT4ZS6I3/2')
    # myftdi.set_baudrate(1_000_000)
    # myftdi.baudrate
    # myftdi.write_data(b'0000000')
    # ftdi_result = myftdi.read_data(size=100)
    # myftdi.close()
    # ftdi_result
    return


@app.cell
def _():
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""# Collect Data from SHARP PC-G850 System Bus""")
    return


@app.cell(hide_code=True)
def _(Enum, mo):
    class CollectDataType(Enum):
        STREAM_TO_FASTAPI = 0
        LOCAL_BUFFER = 1
        LOCAL_PIPELINE = 2

    collect_data_type = mo.ui.radio(
        options={
            "Stream to local FastAPI worker": CollectDataType.STREAM_TO_FASTAPI,
            "Local Pipeline (results in data loss)": CollectDataType.LOCAL_PIPELINE,
            "Local Buffer": CollectDataType.LOCAL_BUFFER,
        },
        value='Local Buffer',
    )
    collect_date_timeout = mo.ui.number(start=1, stop=10, value=3, step=1, label='Timeout (seconds)')
    return CollectDataType, collect_data_type, collect_date_timeout


@app.cell(hide_code=True)
def _(datetime, humanize):
    class TransferRateCalculator:
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
    return (TransferRateCalculator,)


@app.cell(hide_code=True)
def _(collect_data_type, collect_date_timeout, mo):
    collect_data_button = mo.ui.run_button(label="Collect Bus Data", disabled=collect_data_type.value is None)
    mo.vstack(
        [
            mo.hstack([collect_date_timeout, mo.plain_text('Stop capture after there\'s no activity for selected amount of seconds')], justify='start'),
            collect_data_type,
            collect_data_button,
        ]
    )
    return (collect_data_button,)


@app.cell(hide_code=True)
async def _(
    CollectDataType,
    Ft600Device,
    TransferRateCalculator,
    bus_parser,
    collect_data_button,
    collect_data_type,
    collect_date_timeout,
    datetime,
    humanize,
    mo,
    queue,
    time,
    websockets,
):
    mo.stop(not collect_data_button.value)


    class WebsocketAdapter:
        def __init__(self):
            self.websocket = None

        async def start(self):
            uri = "ws://localhost:8000/ws"
            self.websocket = await websockets.connect(uri, ping_interval=None)

        async def all_events(self):
            await self.websocket.close()
            return []


    class LocalPipelineAdapter:
        def __init__(self):
            self.errors_queue = queue.Queue()
            self.parser = bus_parser.PipelineBusParser(
                errors_queue=self.errors_queue,
                out_ports_queue=None,
                save_all_events=True,
            )
            self.buf = b""

        async def send(self, data):
            self.buf += data
            self.buf = self.parser.parse(self.buf)

        async def start(self):
            pass

        async def all_events(self):
            self.parser.flush()
            return self.parser.all_events


    class LocalBufferAdapter:
        def __init__(self):
            self.errors_queue = queue.Queue()
            self.buffer = []

        async def send(self, data):
            self.buffer.append(data)

        async def start(self):
            pass

        async def all_events(self):
            self.parser = bus_parser.PipelineBusParser(
                errors_queue=self.errors_queue,
                out_ports_queue=None,
                save_all_events=True,
            )
            combined_buffer = b''.join(self.buffer)
            expect_num_events = len(combined_buffer) / 4
            print(f'Buffer size: {humanize.naturalsize(len(combined_buffer), binary=True)}; expected number of events: {expect_num_events}')
            self.parser.parse(combined_buffer)
            self.parser.flush()
            return self.parser.all_events


    async def GetBusData(streamer, num_seconds_before_timeout=3):
        # 32KB at a time; Sub-1KB buffers result in FPGA buffer overflow,
        # which results in some events being lost.
        read_size = 2**15

        inst = streamer()
        await inst.start()

        with mo.status.spinner(
            subtitle="Waiting for buffer to clear ..."
        ) as _spinner:
            with Ft600Device() as d:
                # clear input buffer
                empty_count = 0
                while True:
                    bytes = d.read(read_size)
                    if bytes == None or len(bytes) == 0:
                        empty_count += 1
                    else:
                        empty_count = 0
                    if empty_count > 2:
                        break

                status_num_packets_sent = 0
                status_num_bytes_sent = 0

                start = datetime.datetime.now()
                rate_calculator = TransferRateCalculator(
                    lambda rate: _spinner.update(
                        subtitle=f"Collecting data ... {rate}"
                    )
                )

                d.write(b'S+')

                image_index = 1
                transmission_buf = b""
                last_transmission_time = None
                _spinner.update(subtitle="Collecting data ...")
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

                    transmission_buf += bytes
                    if not last_transmission_time or (
                        last_transmission_time - now
                    ) > datetime.timedelta(milliseconds=100):
                        await inst.send(transmission_buf)
                        status_num_packets_sent += 1
                        status_num_bytes_sent += len(bytes)
                        transmission_buf = b""

                        if (
                            collect_data_type.value
                            == CollectDataType.STREAM_TO_FASTAPI
                        ):
                            mo.output.replace(
                                mo.image(
                                    f"http://localhost:8000/lcd?force_redraw={image_index}"
                                )
                            )
                            image_index += 1

                d.write(b'S-')

            _spinner.update(subtitle="Collecting data ...")
            return await inst.all_events()
            time.sleep(0.1)
            return {
                "status_num_packets_sent": status_num_packets_sent,
                "status_num_bytes_sent": status_num_bytes_sent,
            }

    match collect_data_type.value:
        case CollectDataType.STREAM_TO_FASTAPI:
            streamer = WebsocketAdapter
        case CollectDataType.LOCAL_BUFFER:
            streamer = LocalBufferAdapter
        case CollectDataType.LOCAL_PIPELINE:
            streamer = LocalPipelineAdapter
    parsed = await GetBusData(streamer, collect_date_timeout.value)
    return (
        GetBusData,
        LocalBufferAdapter,
        LocalPipelineAdapter,
        WebsocketAdapter,
        parsed,
        streamer,
    )


@app.cell
def _(pandas, parsed):
    df = pandas.DataFrame(parsed)
    return (df,)


@app.cell
def _(bus_parser, df):
    df[df['type'].isin([bus_parser.Type.ERROR])]
    return


@app.cell
def _(df):
    df
    return


@app.cell
def _():
    def find_differences(p4, p6):
        for i in range(min(len(p4), len(p6))):
            if p4[i] != p6[i]:
                # print only changed keys/values, use __dict__ to get all keys/values
                diff = []
                for key in p4[i].__dict__.keys():
                    if key == 'pc':
                        continue
                    if p4[i].__dict__[key] != p6[i].__dict__[key]:
                        diff.append(f'  {key}: {p4[i].__dict__[key]} != {p6[i].__dict__[key]}')

                if len(diff) > 0:
                    print(f'{i}')
                    print('\n'.join(diff))
    return (find_differences,)


@app.cell(hide_code=True)
def _(Type, z80):
    class ProcessBusEvents:
        def __init__(self):
            self.pc = None
            self.buf = b''
            self.decoded = False

        def decode(self):
            disasm = z80.disasm(self.buf, self.pc)
            if len(disasm):
                self.decoded = True
                print(f'  {hex(self.pc)}: {disasm} "{self.buf.hex()}"')

        def fetch(self, addr, val):
            self.pc = addr
            self.buf = bytes([val])
            self.decoded = False
            self.decode()

        def read(self, addr, val):
            if self.decoded:
                pass
            else:
                self.buf += bytes([val])
                self.decode()

        def process_bus_events(self, df):            
            for r in df.itertuples():
                if r.type == Type.FETCH:
                    self.fetch(r.addr, r.val)
                elif r.type == Type.READ:
                    self.read(r.addr, r.val)

        def analyze_portion_of_trace(self, parsed, analyze_min_max):
            start = min(analyze_min_max)
            end = max(analyze_min_max)
            for index, e in enumerate(parsed[start:end]):
                # print(f"{index + start}: {e}")
                if e.type == Type.FETCH:
                    print(f'M:{hex(e.addr)} → {hex(e.val)}{" " + str(e.instr) if e.instr else ""}')
                    self.fetch(e.addr, e.val)
                elif e.type == Type.READ:
                    print(f'R:{hex(e.addr)} → {hex(e.val)}')
                    self.read(e.addr, e.val)
                elif e.type == Type.WRITE:
                    print(f"W:{hex(e.addr)} ← {hex(e.val)}")
                elif e.type == Type.IN_PORT:
                    print(f"  {e.port.name} {hex(e.val)}")
                elif e.type == Type.OUT_PORT:
                    print(f"  {e.port.name} {hex(e.val)}")
                elif e.type == Type.READ_STACK:
                    print(f"S:{hex(e.addr)} → {hex(e.val)}")
                elif e.type == Type.WRITE_STACK:
                    print(f"S:{hex(e.addr)} ← {hex(e.val)}")

    # ProcessBusEvents().analyze_portion_of_trace(parsed, [411265, 411355 + 5])
    return (ProcessBusEvents,)


@app.cell
def _():
    # PC-G850
    FUNCTIONS = {
        0xBA36: "set_rom_bank",
        # modifies stack
        0x93CD: "jump_after_set_rom_bank",
        0x93F3: "jump_after_set_rom_bank_cleanup",
        # https://www.akiyan.com/pc-g850_technical_data
        0x8440: "draw_char",  # BE62h
        0x8738: "draw_char_continuous",  # BFEEh
        0x84BF: "draw_string",  # BFF1h
        0x89BE: "is_key_down",  # BE53h
        0x88C1: "wait_for_key_down",  # BCFDh
    }

    BNIDA_NAMES_RAW = {
        "33856": "draw_char",
        "33983": "draw_string",
        "34027": "scroll_display_one_line_up",
        "34091": "read_lcd_command_until_something?",
        "34616": "draw_char_continuous",
        "35009": "wait_for_key_down",
        "35262": "is_key_down",
        "35304": "scan_key_down?_wrap",
        "35309": "scan_key_down?",
        "35419": "key_something_halt?",
        "35501": "wait_80",
        "35510": "wait_332",
        "35516": "wait",
        "36431": "do_halt?",
        "37610": "delay?",
        "37893": "draw_after_reset?",
        "41317": "draw_run_program_mode",
        "42796": "error_in?",
        "43005": "break_in?",
        "43114": "get_lcd_row_to_draw_possibly_scroll",
        "47117": "draw_string2?",
        "47670": "set_rom_bank",
        "48381": "wait_for_key_down_wrap",
        "48441": "draw_after_reset_wrap",
        "48723": "is_key_down_wrap",
        "49131": "scroll_display_one_line_up_wrap",
        "49134": "draw_char_continuous_wrap",
        "49137": "draw_string_wrap",
        "49152": "main?",
        "65321": "do_reset_memory?",
    }

    BNIDA_NAMES = {int(k, 10): v for k, v in BNIDA_NAMES_RAW.items()}

    def get_function_name(addr: int):
        if addr in BNIDA_NAMES:
            return BNIDA_NAMES[addr]
        if addr in FUNCTIONS:
            return FUNCTIONS[addr]
        return f"sub_{hex(addr)[2:]}"
    return BNIDA_NAMES, BNIDA_NAMES_RAW, FUNCTIONS, get_function_name


@app.cell
def _():
    import dataclasses
    return (dataclasses,)


@app.cell
def _():
    def print_be5f():
        for i in range(26):
            print(f'{hex(i+0x61)}: \'{chr(ord("a")+i)}\',')
    print_be5f()
    return (print_be5f,)


@app.cell
def _():
    class DrawCharInterpreter:
        CHAR_NAMES = {
            0: "␣",
            33: "A",
            34: "B",
            35: "C",
            36: "D",
            37: "E",
            38: "F",
            39: "G",
            40: "H",
            41: "I",
            42: "J",
            43: "K",
            44: "L",
            45: "M",
            46: "N",
            47: "O",
            48: "P",
            49: "Q",
            50: "R",
            51: "S",
            52: "T",
            53: "U",
            54: "V",
            55: "W",
            56: "X",
            57: "Y",
            58: "Z",
            0x1E: ">",
        }

        CHAR_NAMES_BE5F = {
            0x20: "␣",
            0x2A: "*",
            0x41: "A",
            0x42: "B",
            0x43: "C",
            0x44: "D",
            0x45: "E",
            0x46: "F",
            0x47: "G",
            0x48: "H",
            0x49: "I",
            0x4A: "J",
            0x4B: "K",
            0x4C: "L",
            0x4D: "M",
            0x4E: "N",
            0x4F: "O",
            0x50: "P",
            0x51: "Q",
            0x52: "R",
            0x53: "S",
            0x54: "T",
            0x55: "U",
            0x56: "V",
            0x57: "W",
            0x58: "X",
            0x59: "Y",
            0x5A: "Z",
            0x61: "a",
            0x62: "b",
            0x63: "c",
            0x64: "d",
            0x65: "e",
            0x66: "f",
            0x67: "g",
            0x68: "h",
            0x69: "i",
            0x6A: "j",
            0x6B: "k",
            0x6C: "l",
            0x6D: "m",
            0x6E: "n",
            0x6F: "o",
            0x70: "p",
            0x71: "q",
            0x72: "r",
            0x73: "s",
            0x74: "t",
            0x75: "u",
            0x76: "v",
            0x77: "w",
            0x78: "x",
            0x79: "y",
            0x7A: "z",
        }

        @staticmethod
        def char_num(char, func_addr):
            if func_addr == 0xBE5F:
                char += 0x10
            return char

        @staticmethod
        def char_name(char, func_addr):
            if func_addr == 0xBE5F:
                if char in DrawCharInterpreter.CHAR_NAMES_BE5F:
                    return DrawCharInterpreter.CHAR_NAMES_BE5F[char]
                return hex(char)

            if char in DrawCharInterpreter.CHAR_NAMES:
                return DrawCharInterpreter.CHAR_NAMES[char]
            return hex(char)
    return (DrawCharInterpreter,)


@app.cell
def _(bus_parser):
    hex(0xd34f + bus_parser.BANK_SIZE * 2), hex(0xd00c + bus_parser.BANK_SIZE * 2)
    return


@app.cell
def _(
    DrawCharInterpreter,
    InstructionType,
    Optional,
    PerfettoTraceBuilder,
    Pyz80Runner,
    Type,
    dataclass,
    dataclasses,
    datetime,
    get_function_name,
    key_matrix,
    mo,
    parsed,
    pyz80,
):
    @dataclass
    class PerfettoStack:
        begin_event: object
        begin_ts: int
        reg: Optional[pyz80.RegisterPair]

        caller: int
        pc: int
        expected_return_addr: int


    class PerfettoTraceCreator:
        def __init__(self):
            self.pc = None
            self.last_stack_event = None
            self.last_stack_event_index = None
            self.stack = []
            self.ts = 0
            self.index = None
            self.builder = None

            self.main_thread = None
            self.keys_thread = None
            self.draw_char_thread = None
            self.draw_char_addr = {0x8440, 0xbe62, 0xbe5f}

            self.runner = Pyz80Runner()
            self.key_matrix = key_matrix.KeyMatrixInterpreter()
            self.last_pressed_keys = []

            self.enrichment = {
                # draw_char
                0x8440: {'A': 'char', 'D': 'y', 'E': 'x'},
                0xbe5f: {'A': 'char', 'D': 'y', 'E': 'x'},
                0xbe62: {'A': 'char', 'D': 'y', 'E': 'x'},
                # draw_char_continuous
                0x8738: {'A': 'char', 'B': 'num_char', 'D': 'y', 'E': 'x'},
                0xbfee: {'A': 'char', 'B': 'num_char', 'D': 'y', 'E': 'x'},
                # draw_string
                0x84bf: {'B': 'num_char', 'D': 'y', 'E': 'x', 'HL': 'str_ptr'},
                0xbff1: {'B': 'num_char', 'D': 'y', 'E': 'x', 'HL': 'str_ptr'},
            }

            self.interesting_functions = set(self.enrichment.keys())
            self.interesting_functions.add(0x14000) # alternative string draw?

        def create_perfetto_trace(self, data):
            current_date_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.builder = PerfettoTraceBuilder(f'SHARP PC-G850 {current_date_time_str}')

            self.main_thread = self.builder.add_thread_descriptor(self.builder.process_uuid, "main")
            self.keys_thread = self.builder.add_thread_descriptor(self.builder.process_uuid, "keys")
            self.draw_char_thread = self.builder.add_thread_descriptor(self.builder.process_uuid, "draw_char")

            for index, e in enumerate(data):
                self.index = index
                self.ts += 1

                self.runner.eval(e)

                if e.type == Type.FETCH:
                    self.pc = e.addr

                    # it might be useful later
                    if len(self.stack) > 0 and not self.stack[-1].reg:
                        self.stack[-1].reg = self.runner.reg()

                    # self.runner.eval(e) will move the pc to the last_pc
                    if self.runner.last_pc_full in self.interesting_functions:
                        self.enrich_interesting_function(self.runner.last_pc_full)

                    if self.last_stack_event is not None:
                        if self.last_stack_event.instr == InstructionType.CALL:
                            self._handle_call_event(e)
                        else:
                            self._handle_ret_event(e)
                    self.last_stack_event = None
                    self.last_stack_event_index = None
                elif e.type in [Type.IN_PORT, Type.OUT_PORT]:
                    self._handle_port_event(e)

                    self.key_matrix.eval(e)
                    if self.last_pressed_keys != self.key_matrix.pressed_keys():
                        self._handle_pressed_keys(self.last_pressed_keys, self.key_matrix.pressed_keys())
                        self.last_pressed_keys = self.key_matrix.pressed_keys()
                elif e.type in [Type.READ_STACK, Type.WRITE_STACK]:
                    self._handle_stack_event(e)

                # next FETCH instruction will be the destination of the CALL/RET
                if e.instr in [InstructionType.CALL, InstructionType.RET]:
                    self.last_stack_event = e
                    self.last_stack_event_index = index

            return self.builder

        # FIXME: ideally want separate tracks for the items, as they're independent and not nested
        def _handle_pressed_keys(self, last, curr):
            # first need to close the slices for the keys that are no longer pressed
            stop_pressed = set(last) - set(curr)
            for k in stop_pressed:
                self.builder.add_slice_event(self.keys_thread, self.ts, 'end')

            # then open slices for keys that weren't pressed before and are pressed now
            start_pressed = set(curr) - set(last)
            for k in start_pressed:
                self.builder.add_slice_event(self.keys_thread, self.ts, 'begin', f'key {k}')

        def _annotate_common(self, be, e, name):
            with be.annotation(name) as ann:
                ann.int("index", self.last_stack_event_index)
                ann.pointer("pc", self.pc)
                ann.pointer("caller", self.last_stack_event.addr)
                if e.bank:
                    ann.int("bank", e.bank)

        def _handle_call_event(self, e):
            function_name = get_function_name(self.pc)
            with self.builder.add_slice_event(self.main_thread, self.ts, 'begin', function_name) as begin_event:
                expected_return_addr = self.last_stack_event.addr + 3
                self.stack.append(PerfettoStack(
                    begin_event=begin_event,
                    begin_ts=self.ts,
                    reg=None,
                    caller=self.last_stack_event.addr,
                    pc=self.pc,
                    expected_return_addr=expected_return_addr
                ))
                self._annotate_common(begin_event, e, 'call')

        def enrich_interesting_function(self, addr):
            assert len(self.stack) > 0
            s = self.stack[-1]
            if addr in self.enrichment:
                with s.begin_event.annotation("enrich") as ann:
                    for reg, field in self.enrichment[addr].items():
                        if len(reg) == 2:
                            high = getattr(self.runner.reg(), reg[0])
                            low = getattr(self.runner.reg(), reg[1])
                            ann.pointer(field, (high << 8) | low)
                        else:
                            ann.int(field, getattr(self.runner.reg(), reg))
            else:   
                with s.begin_event.annotation("reg") as ann:
                    reg = self.runner.reg()
                    # iterate over all fields in RegisterPair and add them to the annotation as pointers
                    for field in dataclasses.fields(reg):
                        ann.pointer(field.name, getattr(reg, field.name))

        def create_draw_char_slice(self, s, e):
            char = DrawCharInterpreter.char_name(s.reg.A, s.pc)
            begin = self.builder.add_slice_event(self.draw_char_thread, s.begin_ts, 'begin', char)
            with begin.annotation('draw_char') as ann:
                ann.pointer("char", s.reg.A)
                ann.pointer("x", s.reg.E)
                ann.pointer("y", s.reg.D)
            self.builder.add_slice_event(self.draw_char_thread, self.ts, 'end')

        def _handle_mismatched_ret_event(self, e, s):
            # sub_93cd hacks the return address after switching rom bank
            if self.last_stack_event.addr == 0x93f2:
                self._handle_call_event(e)
                self.stack[-1].expected_return_addr = 0x93f3
                return

            with self.builder.add_instant_event(self.main_thread, self.ts, 'BAD_RET').annotation('ret') as ann:
                ann.int("index", self.index)
                ann.pointer("pc", self.pc)
                ann.pointer("expected_return_addr", s.expected_return_addr)

        def _handle_ret_event(self, e):
            if self.stack:
                s = self.stack.pop()

                if s.pc in self.draw_char_addr:
                    self.create_draw_char_slice(s, e)

                self.builder.add_slice_event(self.main_thread, self.ts, 'end')
                self._annotate_common(s.begin_event, e, 'ret')

                if self.pc != s.expected_return_addr:
                    self._handle_mismatched_ret_event(e, s)
            else:
                underflow = self.builder.add_instant_event(self.main_thread, self.ts, 'UNDERFLOW')
                self._annotate_common(underflow, e, 'ret')

        def _handle_port_event(self, e):
            direction = 'in' if e.type == Type.IN_PORT else 'out'
            name = f'{e.port.name} {direction} {hex(e.val)}'
            with self.builder.add_instant_event(self.main_thread, self.ts, name).annotation('call') as ann:
                ann.int("index", self.index)
                ann.pointer("pc", self.pc)
                ann.pointer("port", e.port.value)
                ann.pointer("val", e.val)

        def _handle_stack_event(self, e):
            direction = 'POP' if e.type == Type.READ_STACK else 'PUSH'
            name = f'{direction} {hex(e.val)}'
            with self.builder.add_instant_event(self.main_thread, self.ts, name).annotation('stack') as ann:
                ann.int("index", self.index)
                ann.pointer("pc", self.pc)
                ann.pointer("addr", e.addr)
                ann.pointer("val", e.val)


    def get_perfetto_trace_data():
        ppp = PerfettoTraceCreator().create_perfetto_trace(parsed)
        return ppp.serialize()

    download_perfetto = mo.download(
        label='Download Perfetto Trace',
        data=get_perfetto_trace_data,
        filename="sharp-pc-g850-perfetto.pb",
    )
    len(get_perfetto_trace_data())
    download_perfetto
    return (
        PerfettoStack,
        PerfettoTraceCreator,
        download_perfetto,
        get_perfetto_trace_data,
    )


@app.cell(hide_code=True)
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

        def __enter__(self):
            return self

        def __exit__(self, type, value, traceback):
            pass

        def annotation(self, name):
            ann = self.event.debug_annotations.add()
            ann.name = name
            return DebugAnnotation(ann)

    class PerfettoTraceBuilder:
        def __init__(self, process_name: str):
            self.trace = perfetto.Trace()
            self.last_track_uuid = 0
            self.trusted_packet_sequence_id = 0x123
            # self.process_uuid = 0x456
            self.pid = 1234
            self.last_tid = 1
            # self.tid = 5678

            self.process_uuid = self.add_process_descriptor(process_name)
            # self.add_thread_descriptor(thread_descriptor)

        def add_process_descriptor(self, process_name: str):
            self.last_track_uuid += 1
            track_uuid = self.last_track_uuid

            packet = self.trace.packet.add()
            packet.track_descriptor.uuid = track_uuid # self.process_uuid
            packet.track_descriptor.process.pid = self.pid
            packet.track_descriptor.process.process_name = process_name
            return track_uuid

        def add_thread_descriptor(self, process_uuid: int, thread_name: str):
            self.last_track_uuid += 1
            track_uuid = self.last_track_uuid

            packet = self.trace.packet.add()
            packet.track_descriptor.uuid = track_uuid
            packet.track_descriptor.parent_uuid = process_uuid
            packet.track_descriptor.thread.pid = self.pid
            packet.track_descriptor.thread.tid = self.last_tid
            self.last_tid += 1
            packet.track_descriptor.thread.thread_name = thread_name
            return track_uuid

        def add_slice_event(self, track_uuid, timestamp: int, event_type: str, name: str = None):
            packet = self.trace.packet.add()
            packet.timestamp = timestamp

            if event_type == 'begin':
                packet.track_event.type = perfetto.TrackEvent.TYPE_SLICE_BEGIN
                packet.track_event.name = name
            elif event_type == 'end':
                packet.track_event.type = perfetto.TrackEvent.TYPE_SLICE_END
            else:
                raise ValueError("event_type must be either 'begin' or 'end'.")

            packet.track_event.track_uuid = track_uuid
            packet.trusted_packet_sequence_id = self.trusted_packet_sequence_id
            return TrackEvent(packet.track_event)

        def add_instant_event(self, track_uuid, timestamp: int, name: str):
            packet = self.trace.packet.add()
            packet.timestamp = timestamp
            packet.track_event.type = perfetto.TrackEvent.TYPE_INSTANT
            packet.track_event.track_uuid = track_uuid
            packet.track_event.name = name
            packet.trusted_packet_sequence_id = self.trusted_packet_sequence_id
            return TrackEvent(packet.track_event)

        def serialize(self) -> bytes:
            return self.trace.SerializeToString()
    return DebugAnnotation, PerfettoTraceBuilder, TrackEvent, perfetto


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
def _(Type):
    def df_valh(df):
        df2 = df.copy()
        for col in ['pc', 'addr', 'val']:
            if col in df2.columns:
                df2[col + 'h'] = df2[col].apply(lambda x: hex(x))
        return df2

    def io_df(df):
        df2 = df[df['type'].isin([Type.IN_PORT, Type.OUT_PORT])].copy()
        return df_valh(df2)
    return df_valh, io_df


@app.cell
def _(IOPort, df, sed1560):
    def do_parse_lcd_commsnds(df):
        return sed1560.SED1560Parser.parse_bus_commands(
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
            # .reset_index(drop=True)
        )

    parsed_lcd_commands = do_parse_lcd_commsnds(df)
    parsed_lcd_commands_df = sed1560.SED1560Parser.parsed_commands_to_df(parsed_lcd_commands)
    return do_parse_lcd_commsnds, parsed_lcd_commands, parsed_lcd_commands_df


@app.cell
def _(IOPort, df, lcd_commands_range):
    dfports = df[
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

    # df_valh(dfports[lcd_commands_range.value['start']:lcd_commands_range.value['start']+lcd_commands_range.value['length']])
    # print the original index that corresponds to lcd_commands_range.value['start']
    orig_start = dfports.index[lcd_commands_range.value['start']]
    orig_end = dfports.index[lcd_commands_range.value['start']+lcd_commands_range.value['length']]
    orig_start, orig_end
    return dfports, orig_end, orig_start


@app.cell
def _(IOPort, Type, bus_parser, dataclass, rom_banks):
    # Pyz80Runner

    import pyz80

    @dataclass
    class RegisterPair:
        A: int
        F: int
        B: int
        C: int
        D: int
        E: int
        H: int
        L: int

    class Pyz80Runner:
        # after we get out of bootrom this is where the execution is expected to start
        START_ADDR = 0xC000

        def __init__(self, debug_index_start=None, debug_index_end=None):
            # Initial state variables
            self.last_pc = None
            self.last_pc_full = None
            self.pc = self.START_ADDR
            self.pc_full = self.pc
            self.rom_bank = 0

            self.debug_index_start = debug_index_start
            self.debug_index_end = debug_index_end

            self.index = 0
            self.ready_to_eval = False
            self.at_least_one_instruction_is_executed = False

            self.expected_reads = {}
            self.expected_writes = {}
            self.actual_reads = {}
            self.actual_writes = {}
            self.io_reads = {}
            self.io_writes = {}

            # Instantiate the Z80 processor with callback methods
            self.z80 = pyz80.Z80(
                self.read_byte,
                self.write_byte,
                self.in_port,
                self.out_port,
                returnPortAs16Bits=False,
            )
            if self.debug_index_start is not None:
                assert self.debug_index_end is not None
                print(f"Debugging from {self.debug_index_start} to {self.debug_index_end}")
                self.z80.set_debug_message(self.debug_message)
            self.z80.PC = self.pc

        def read_byte(self, addr):
            try:
                ret = self.expected_reads[addr]
            except KeyError as e:
                if addr >= 0x87B7 and addr <= 0x87C0:
                    return rom_banks[0][addr - 0x8000]
            
                # FIXME: why stack could become misaligned?
                if addr < bus_parser.ROM_ADDR_START and addr >= bus_parser.ROM_ADDR_START - bus_parser.STACK_SIZE:
                    return 0

                if addr >= bus_parser.ROM_ADDR_START and addr < bus_parser.BANK_ADDR_START:
                    return rom_banks[0][addr - bus_parser.ROM_ADDR_START]
                if addr > bus_parser.BANK_ADDR_START:
                    return rom_banks[self.rom_bank][addr - bus_parser.BANK_ADDR_START]

                self.debug_expected_state()
                # raise ValueError(
                #     f"{self.index} {hex(self.last_pc)} Expected read at {hex(addr)} not found (rom_bank: {self.rom_bank})"
                # ) from e
                ret = 0
            self.actual_reads[addr] = ret
            return ret

        def write_byte(self, addr, value):
            self.actual_writes[addr] = value

        def in_port(self, port):
            try:
                return self.io_reads[port]
            except KeyError as e:
                # FIXME
                return 0

        def out_port(self, port, value):
            self.io_writes[port] = value

        def debug_message(self, msg):
            if self.index >= self.debug_index_start and self.index < self.debug_index_end:
                print(f"{self.index} DEBUG:", msg)

        def print_dict_hex(self, d):
            return {hex(k): hex(v) for k, v in d.items()}

        def debug_expected_state(self):
            print(
                f"reads: {self.print_dict_hex(self.expected_reads)}; "
                f"writes: {self.print_dict_hex(self.expected_writes)}; "
                f"io_reads: {self.print_dict_hex(self.io_reads)}; "
                f"io_writes: {self.print_dict_hex(self.io_writes)}"
            )

        def run_z80(self):
            if not self.at_least_one_instruction_is_executed:
                return

            # print(f"run {hex(self.last_pc)} ({hex(self.pc)})")
            # self.debug_expected_state()

            # FIXME: sub_87b7 results in desyncing, also it appears to skip some memory reads on the bus???
            # if self.z80.PC != self.last_pc:
            #     raise ValueError(f"Expected PC {hex(self.last_pc)}, got {hex(self.z80.PC)}")
            self.z80.PC = self.last_pc

            # don't try to execute HALT, as it'll prevent further analysis
            if self.expected_reads[self.last_pc] != 0x76: # HALT
                # print(f"z80.PC: {hex(self.z80.PC)}, pc: {hex(self.last_pc)}")
                try:
                    self.z80.execute(1)
                except RuntimeError as e:
                    self.debug_expected_state()
                    raise ValueError(
                        f"{self.index} {hex(self.last_pc)} (rom_bank: {self.rom_bank})"
                    ) from e

            # Clear expected and actual operations after an instruction finishes
            self.expected_reads.clear()
            self.expected_writes.clear()
            self.actual_reads.clear()
            self.actual_writes.clear()
            self.io_reads.clear()
            self.io_writes.clear()

        def reverse_full_addr(self, full_address):
            if self.rom_bank is None or self.rom_bank == 0:
                return full_address  # No transformation was applied

            if full_address < bus_parser.BANK_ADDR_START:
                return full_address

            return full_address - (bus_parser.BANK_SIZE * (self.rom_bank - 1))

        # this is expected to be called only after we get to the START_ADDR execution
        def _eval(self, r):
            if r.type == Type.FETCH:
                # need to wait until the next instruction before running the first one
                if r.addr != self.START_ADDR:
                    self.at_least_one_instruction_is_executed = True

                self.last_pc_full = self.pc_full
                self.last_pc = self.pc
                self.pc_full = r.addr
                self.pc = self.reverse_full_addr(self.pc_full)
                self.run_z80()

                self.expected_reads[self.reverse_full_addr(r.addr)] = r.val
            elif r.type in [Type.READ, Type.READ_STACK]:
                self.expected_reads[self.reverse_full_addr(r.addr)] = r.val
            elif r.type in [Type.WRITE, Type.WRITE_STACK]:
                self.expected_writes[self.reverse_full_addr(r.addr)] = r.val
            elif r.type == Type.IN_PORT:
                self.io_reads[r.port.value] = r.val
            elif r.type == Type.OUT_PORT:
                if r.port == IOPort.ROM_BANK:
                    self.rom_bank = r.val
                elif r.port == IOPort.ROM_EX_BANK:
                    self.rom_bank = r.val & 0x0F

                self.io_writes[r.port.value] = r.val
            else:
                print(f"{self.index}: {r.type} {hex(r.addr)} {r.val}")

        def reg(self):
            p = self.z80.reg.pair
            return RegisterPair(A=p.A, F=p.F, B=p.B, C=p.C, D=p.D, E=p.E, H=p.H, L=p.L)

        def eval(self, r):
            self.index += 1
            if r.type == Type.FETCH:
                # don't try to execute what's in the bootrom
                if r.addr == self.START_ADDR:
                    self.ready_to_eval = True

            if self.ready_to_eval:
                self._eval(r)

        def run_trace(self, df):
            self.index = 0
            for r in df:
                self.eval(r)

            return self.reg()

    # runner = Pyz80Runner()
    # runner.run_trace(parsed)
    return Pyz80Runner, RegisterPair, pyz80


@app.cell
def _():
    # df_valh(dfports[lcd_commands_range.value['start']:lcd_commands_range.value['start']+lcd_commands_range.value['length']])
    return


@app.cell
def _(df, df_valh, orig_end, orig_start):
    df_valh(df[orig_start+1:orig_end])
    return


@app.cell
def _(df, df_valh):
    df_valh(df[412722-20:])
    return


@app.cell
def _(Pyz80Runner, df, orig_end, orig_start):
    runner = Pyz80Runner(debug_index_start=orig_start, debug_index_end=orig_end)
    for index, r in enumerate(df.itertuples()):
        # print(index)
        runner.eval(r)
    print(runner.index)
    return index, r, runner


app._unparsable_cell(
    r"""
    df[]
    """,
    name="_"
)


@app.cell
def _(dfports, lcd_commands_range):
    dfports.iloc[lcd_commands_range.value['start']:lcd_commands_range.value['start']+1]
    return


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


@app.cell(hide_code=True)
def _(lcd_commands_range, parsed_lcd_commands):
    parsed_lcd_commands_filtered = parsed_lcd_commands[lcd_commands_range.value['start']: lcd_commands_range.value['start'] + lcd_commands_range.value['length']]
    return (parsed_lcd_commands_filtered,)


@app.cell
def _(parsed_lcd_commands_filtered, sed1560):
    display = sed1560.SED1560Interpreter()
    for cmd in parsed_lcd_commands_filtered:
        display.eval(cmd)

    display.vram_image()
    return cmd, display


@app.cell(hide_code=True)
def _(alt, filtered_lcd_commands, mo, parsed_lcd_commands_df):
    def plot_parsed_lcd_commands(df):
        min_index = df['index'].min()
        max_index = df['index'].max()
        x_scale = alt.Scale(domain=(min_index, max_index))

        key_columns = [] # 'KEY_INPUT'] #, 'SHIFT_KEY_INPUT', 'SET_KEY_STROBE_LO', 'SET_KEY_STROBE_HI']
        # key_columns = []

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


if __name__ == "__main__":
    app.run()
