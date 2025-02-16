import marimo

__generated_with = "0.11.5"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import altair as alt
    return (alt,)


@app.cell
def _():
    import sys
    sys.path.append("d3xx")

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
def _(Enum, IOPort, Optional, data_concat, dataclass, struct):
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
        addr: int # uint16
        port: Optional[IOPort]
        # raw:  bytes

    def parse_data(data):
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

            port = None
            if type in [Type.IN_PORT, Type.OUT_PORT]:
                addr &= 0xFF
                try:
                    port = IOPort(addr)
                except:
                    errors.append(f"Invalid port at offset {offset}: {hex(addr)}")

            r.append(Event(type, val, addr, port))
        return r, errors

    parsed, errors = parse_data(data_concat)
    errors
    return Event, Type, errors, parse_data, parsed


@app.cell
def _(mo, parsed):
    import pandas
    df = pandas.DataFrame(parsed)
    mo.ui.dataframe(df, page_size=20)
    return df, pandas


@app.cell
def _(Type, df):
    in_ports = []
    out_ports = []

    for i in sorted(list(set(df[df['type'].isin([Type.IN_PORT])]['addr']))):
        in_ports.append(hex(i))

    for i in sorted(list(set(df[df['type'].isin([Type.OUT_PORT])]['addr']))):
        out_ports.append(hex(i))

    print('in_ports: ' + ','.join(in_ports))
    print('out_ports: ' + ','.join(out_ports))
    return i, in_ports, out_ports


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


@app.cell
def _(IOPort, PCG850Display, Type, df):
    def process_trace():
        display = PCG850Display()
        xin_enabled = None
        key_strobe = 0
        
        unhandled_inport = set()
        unhandled_outport = set()

        # IO Port descriptions:
        # http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
        for r in df.itertuples():
            # print(r.type, r.val, r.addr)
            try:
                port = IOPort(r.addr) if r.type in [Type.IN_PORT, Type.OUT_PORT] else None
            except ValueError:
                continue
                
            if r.type == Type.WRITE:
                pass
            elif r.type in [Type.READ, Type.FETCH]:
                pass
            elif r.type == Type.IN_PORT:
                match port:
                    case IOPort.KEY_INPUT:
                        key_strobe = r.val
                        print(f"read key_strobe: {hex(key_strobe)}")
                    case 0x15:
                        xin_enabled = r.val
                        print(f"read xin_enabled: {xin_enabled}")
                    case 0x19:
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        print(f"read rom_bank: {rom_bank}, ex_bank: {ex_bank}")
                        pass
                    case 0x40:
                        # FIXME: fails??
                        # if r.val != 0:
                        #     raise ValueError(f"Unexpected value for IN_PORT 0x40: {r.val}")
                        pass
                    case 0x69:
                        rom_bank = r.val & 0x0F
                        print(f"read rom_bank: {rom_bank}")
                        pass
                    # case _:
                    #     unhandled_inport.add(r.addr)
                    #     # raise ValueError(f"Unknown in_port {hex(r.addr)}")
        
        
            elif r.type == Type.OUT_PORT:
                match r.addr:
                    case 0x11:
                        key_strobe |= r.val
                        print(f"write key_strobe: {hex(key_strobe)}")
                    case 0x12:
                        key_strobe = (r.val << 8) & 0xFF00
                        print(f"write key_strobe: {hex(key_strobe)}")
                    case 0x15:
                        xin_enabled = r.val & 0x80
                        print(f"write xin_enabled: {xin_enabled}")
                        pass
                    case 0x16:
                        print(f"write interruptType: {hex(r.val)}")
                        pass
                    case 0x19:
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        print(f"write rom_bank: {rom_bank}, ex_bank: {ex_bank}")
                        pass
                    case 0x1a:
                        print(f"boot rom on/off: {r.val}")
                    case 0x1b:
                        ram_bank = r.val & 0x04
                        print(f"write ram_bank: {ram_bank}")
                        pass
                    case 0x1e:
                        print(f"write battery check mode: {r.val & 0x03}")
                    case 0x40:
                        display.parse_out40(r.val)
                    case 0x41:
                        display.parse_out41(r.val)
                    case 0x69:
                        rom_bank = r.val & 0x0F
                        print(f"write rom_bank: {rom_bank}")
                        pass
                    case 0xed:
                        pass
                    case _:
                        unhandled_outport.add(r.addr)
                        # raise ValueError(f"Unknown out_port {hex(r.addr)}")
            else:
                raise ValueError(f"Unknown type {r.type}")

        return display

    # display = process_trace()
    # display.dump_vram()
    return (process_trace,)


@app.cell
def _(Image, ImageDraw, List, Tuple, dataclass):
    @dataclass
    class Machineinfo:
        cell_width: int  # Width (in pixels) per cell
        cell_height: int # Height (in pixels) per cell
        lcd_cols: int    # Number of cells horizontally
        lcd_rows: int    # Number of cells vertically
        vram_cols: int
        vram_rows: int

        @property
        def vram_width(self):
            return self.vram_cols * self.cell_width

        @property
        def vram_height(self):
            return self.vram_rows * 8

    g850info = Machineinfo(
        cell_width=6,
        cell_height=8,
        lcd_cols=24,
        lcd_rows=6,
        vram_cols=24,
        vram_rows=8,
    )

    def draw_vram(vram: List[int],
                  machine: Machineinfo,
                  lcdTop: int,
                  zoom: int = 1,
                  off_color: Tuple[int, int, int] = (0, 0, 0),
                  on_color: Tuple[int, int, int] = (0, 255, 0)
                  ) -> Image.Image:
        lcd_cols = machine.lcd_cols
        lcd_rows = machine.lcd_rows
        cell_width  = machine.cell_width
        cell_height = machine.cell_height
        vram_width  = machine.vram_width

        lcd_width = lcd_cols * cell_width
        lcd_height = lcd_rows * cell_height
        img_width  = lcd_width * zoom
        img_height = lcd_height * zoom
        print(f'Image size: {img_width} x {img_height}')

        image = Image.new("RGB", (img_width, img_height), off_color)
        draw = ImageDraw.Draw(image)

        vram_offset = (lcdTop // 8) * vram_width
        shift = lcdTop % 8;
        for y in range(0, lcd_height, cell_height):
            for x0 in range(0, lcd_width, cell_width):
                for x in range(cell_width):
                    pat = vram[vram_offset] >> shift | vram[vram_offset + vram_width] << (8 - shift)

                    for p in range(cell_height):
                        bit = 1 << p
                        dx = x0 + x + p
                        dy = y
                        color = on_color if bit else off_color
                        draw.rectangle([dx * zoom, dy * zoom, dx * zoom + zoom - 1, dy * zoom + zoom - 1], fill=color)    

                    vram_offset += 1
            vram_offset += 1

        return image

    # vram = sum(display.vram, [])
    # # print(len(vram))
    # draw_vram(vram, g850info, display.lcdTop, zoom=4)
    return Machineinfo, draw_vram, g850info


@app.cell
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


@app.cell
def _(mo):
    mo.md(r"""# Trying to match the reads in the ROM region with the known good ROM dumps""")
    return


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

    verifier = verify_rom_memory()
    return RomVerifier, verifier, verify_rom_memory


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
def _(Type):
    def df_valh(df):
        df2 = df.copy()
        df2['addrh'] = df2['addr'].apply(lambda x: hex(x))
        df2['valh'] = df2['val'].apply(lambda x: hex(x))
        return df2

    def io_df(df):
        df2 = df[df['type'].isin([Type.IN_PORT, Type.OUT_PORT])].copy()
        return df_valh(df2)
        
    # io_df(df_for_plot)
    return df_valh, io_df


@app.cell
def _(IOPort, df, df_valh):
    # df3 = df[df['type'].isin([Type.IN_PORT, Type.OUT_PORT])].copy()
    lcd_commands = df[df['port'].isin([IOPort.LCD_COMMAND, IOPort.LCD_OUT])].copy().reset_index(drop=True)
    # lcd_commands = lcd_commands[lcd_commands['val'] != 0]
    # df3['key'] = df3['val'].apply(lambda x: KEY_TO_NAME[x & 0x7f])

    df_valh(lcd_commands)
    return (lcd_commands,)


@app.cell
def _(lcd_commands_range):
    def filtered_lcd_commands(df):
        df = df.iloc[
            lcd_commands_range.value["start"] : lcd_commands_range.value["start"]
            + lcd_commands_range.value["length"]
        ]
        return df
    return (filtered_lcd_commands,)


@app.cell(hide_code=True)
def _(lcd_commands, mo):
    def get_lcd_commands_range(df):
        return mo.md("""
        {start}
        
        {length}
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
        )

    lcd_commands_range = get_lcd_commands_range(lcd_commands)
    lcd_commands_range
    return get_lcd_commands_range, lcd_commands_range


@app.cell
def _(IOPort, SED1560, filtered_lcd_commands, lcd_commands, pandas):
    def parse_lcd_commands(df):
        df = filtered_lcd_commands(df)

        result = []
        for r in df.itertuples():
            if r.port == IOPort.LCD_COMMAND:
                parsed = SED1560.Parser.parse_out40(r.val)
            elif r.port == IOPort.LCD_OUT:
                parsed = SED1560.Parser.parse_out41(r.val)

            parsed_type = type(parsed).__name__
            # if CmdA, then get type from parsed.cmd
            if parsed_type == 'CmdA':
                parsed_type = parsed.cmd.name
            
            result.append({
                "index": r.Index,
                "type": parsed_type,
                **vars(parsed)
            })
        return pandas.DataFrame(result)
        # return draw_vram2(display.vram)

    parse_lcd_commands(lcd_commands)
    return (parse_lcd_commands,)


@app.cell(hide_code=True)
def _(IOPort, SED1560, SetColumn, filtered_lcd_commands):
    def preprocess_lcd_commands(df):
        df = filtered_lcd_commands(df)

        commands = []
        for r in df.itertuples():
            if r.port == IOPort.LCD_COMMAND:
                parsed = SED1560.Parser.parse_out40(r.val)
            elif r.port == IOPort.LCD_OUT:
                parsed = SED1560.Parser.parse_out41(r.val)
            commands.append(parsed)

        processed = []
        i = 0
        while i < len(commands):
            match commands[i:i+2]:
                case [SED1560.SetColumnPart(is_high=False, value=low),
                      SED1560.SetColumnPart(is_high=True, value=high)]:
                    print('match1')
                    processed.append(SetColumn(value=low | high))
                    i += 2
                case [SED1560.SetColumnPart(is_high=True, value=high),
                      SED1560.SetColumnPart(is_high=False, value=low)]:
                    print('match2')
                    processed.append(SetColumn(value=low | high))
                    i += 2
                case _:
                    processed.append(commands[i])
                    i += 1
                
        return processed

    # preprocess_lcd_commands(lcd_commands)
    return (preprocess_lcd_commands,)


@app.cell
def _(alt, lcd_commands, mo, parse_lcd_commands):
    def plot_parsed_lcd_commands(df):
        df = parse_lcd_commands(df)
        events_points = alt.Chart(df[~df['type'].isin(['InitialDisplayLine', 'SetColumnPart', 'SetPageAddress', 'VRAMWrite'])]).mark_point().encode(
            x='index:Q',
            y='type:N',
            color='type:N',
            tooltip=['index', 'type', 'value']
        )

        sub_charts = alt.Chart(df[df['type'].isin(['VRAMWrite'])]).mark_point().encode(
            x='index:Q',
            y=alt.Y('value:Q', title="Value"),
            color='type:N',
            tooltip=['index', 'type', 'value']
        ).properties(title="VRAM Write")

        # also add SetColumnPart as two separate charts for is_high=False and is_high=True
        set_column_high = alt.Chart(df[df['type'] == 'SetColumnPart']).mark_point().encode(
            x='index:Q',
            y=alt.Y('value:Q', title="Value"),
            color='is_high:N',
            tooltip=['index', 'type', 'value', 'is_high']
        ).properties(title="Set Column")

        set_page_address = alt.Chart(df[df['type'] == 'SetPageAddress']).mark_point().encode(
            x='index:Q',
            y='value:Q',
            color='type:N',
            tooltip=['index', 'type', 'value']
        ).properties(title="Set Page Address")
        
        initial_display_line = alt.Chart(df[df['type'] == 'InitialDisplayLine']).mark_point().encode(
            x='index:Q',
            y='value:Q',
            color='type:N',
            tooltip=['index', 'type', 'value']
        ).properties(title="Initial Display Line")

        return alt.vconcat(events_points, sub_charts, set_column_high, set_page_address, initial_display_line)


    mo.ui.altair_chart(plot_parsed_lcd_commands(lcd_commands))
    return (plot_parsed_lcd_commands,)


@app.cell
def _(df_valh, filtered_lcd_commands, lcd_commands):
    df_valh(filtered_lcd_commands(lcd_commands))
    return


@app.cell
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
            x: int
            high: int
            low: int

        class Parser:
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
                    raise SED1560.Unknown(x=x, high=high, low=low)

            @staticmethod
            def parse_out41(x: int):
                return SED1560.VRAMWrite(value=x)

    return (SED1560,)


@app.cell(hide_code=True)
def _():
    # # need to mask off last bit
    # class SED1560_CmdA(Enum):
    #     SET_RAM_SEGMENT_OUTPUT = 0x0  # 0: Normal, 1: Inverse
    #     DISPLAY_ON = 0xE  # 0: Off, 1: On
    #     DISPLAY_MODE = 0x6  # 0: Normal, 1: Inverse
    #     SEGMENTS_DISPLAY_MODE = 0x4  # 0: Normal, 1: All display segments On
    #     LCD_CONTROLLER_DUTY1 = 0x8  # See Table 5.3
    #     LCD_CONTROLLER_DUTY2 = 0xA


    # # display controller is SED1560
    # class SED1560:
    #     # VRAM: 166 x 65 bits (last page is 1-bit high)

    #     # 8 pages of 8 lines, last 9th page of 1 line
    #     PAGE_HEIGHT = 8  # pixels
    #     NUM_PAGES = 9

    #     LCD_WIDTH = 166
    #     LCD_HEIGHT = 8

    #     # When the Select ADC command is used to select inverse display operation, the column address decoder inverts the relationship between the RAM column data and the display segment outputs.

    #     def __init__(self):
    #         self.page = 0
    #         self.col = 0  # x coordinate

    #         self.com0 = 0  # Initial Display Line register, 6 bits

    #         # Initialize VRAM as a 2D array of bytes (each row is a list of LCD_WIDTH bytes)
    #         self.vram = [
    #             [0 for _ in range(self.LCD_WIDTH)] for _ in range(self.LCD_HEIGHT)
    #         ]

    #     def debug(self, str):
    #         print(">display: " + str)
    #         pass

    #     def parse_out40(self, x, index=None):
    #         high = (x & 0xF0) >> 4
    #         low = x & 0x0F

    #         if (x >> 6) == 1:
    #             # Initial Display Line
    #             self.com0 = x & 0x3F
    #             # self.debug(f'com0 ← {self.com0}')
    #         elif (x >> 5) == 0b100:
    #             self.contrast = x & 0b11111
    #             print(f"contrast: {self.contrast}")
    #         elif (x >> 1) == 0b10010:
    #             self.psu_on = x & 0b1
    #             print(f"{index}: psu_on: {self.psu_on}")
    #         elif x == 0b11101101:
    #             self.power_on_complete = True
    #             print(f"{index}: power_on_complete")
    #         elif high == 0xB:
    #             # Set Page Address
    #             self.page = low
    #             # self.debug(f'page ← {self.page}')
    #         elif high == 0xA:
    #             cmd = SED1560_CmdA(low & 0b1110)
    #             val = low & 0b1
    #             print(f"{index}: cmd_a: {cmd}, val: {val}")
    #         elif high == 0xC:
    #             # Sets the common and segment output status register.
    #             # This command selects the role of the COM/SEG dual pins and determines the LCD driver output status.
    #             self.scanning_direction = low >> 3
    #             case = low & 0b111
    #             if case != 0b111:
    #                 raise ValueError(
    #                     f"Unhandled case: {bin(case)}, only SEG166 is supported"
    #                 )
    #             print(
    #                 f"scanning_direction: {self.scanning_direction}, case: {bin(case)}"
    #             )
    #         elif high in [0x0, 0x1]:
    #             if high:
    #                 self.col = (self.col & 0x0F) | low
    #             else:
    #                 self.col = (self.col & 0xF0) | low
    #             # self.debug(f'col ← {self.col} ({'high' if high else 'low'})')
    #         else:
    #             print(f"{x:08b}: Unhandled high: {hex(high)}, low: {hex(low)}")

    #     def parse_out41(self, x):
    #         # if not x:
    #         #     return

    #         # print(f'VRAM[{self.page}][{self.col}] ← {hex(x)}')
    #         self.vram[self.page][self.col] = x

    #         # The counter automatically stops at the highest address, A6H.
    #         self.col = min(self.col + 1, self.LCD_WIDTH - 1)
    return


@app.cell
def _():
    return


@app.cell(hide_code=True)
def _():
    # # display controller is SED1560
    # class SED1560:
    #     # VRAM: 166 x 65 bits

    #     # 8 pages of 8 lines, last 9th page of 1 line
    #     PAGE_HEIGHT = 8 # pixels
    #     NUM_PAGES = 9

    #     LCD_WIDTH = 166
    #     LCD_HEIGHT = 8 

    #     def __init__(self):
    #         self.page = 0
    #         self.col = 0 # x coordinate

    #         # Initialize VRAM as a 2D array of bytes (each row is a list of LCD_WIDTH bytes)
    #         self.vram = [[0 for _ in range(self.LCD_WIDTH)] for _ in range(self.LCD_HEIGHT)]

    #     def updateLCDContrast(self):
    #         pass

    #     def debug(self, str):
    #         print('>display: ' + str)
    #         pass

    #     def parse_out40(self, x):
    #         print(f"{x:08b}")
    #         self.lcdRead = False
    #         high = x & 0xf0
    #         low = x & 0x0f

    #         if (x >> 6) == 1:
    #             # Initial Display Line
    #             self.lcdTop = x & 0x3F
    #             self.debug(f'Set lcdTop to {self.lcdTop}')

    #         elif high == 0x00:
    #             # Set lower nibble of horizontal coordinate if not in lcdMod mode.
    #             if not self.lcdMod:
    #                 self.lcdX = (self.lcdX & 0xf0) | low
    #                 self.debug(f'Set lcdX low to {self.lcdX}')

    #         elif high == 0x10:
    #             # Set upper nibble of lcdX.
    #             if not self.lcdMod:
    #                 # (x << 4) gives the new high nibble.
    #                 self.lcdX = ((x & 0xff) << 4) | (self.lcdX & 0x0f)
    #                 self.debug(f'Set lcdX high to {self.lcdX}')

    #         elif high == 0x20:
    #             # Enable/disable the LCD.
    #             if x == 0x24:
    #                 self.lcdDisabled = True
    #                 self.debug('LCD disabled')
    #             elif x == 0x25:
    #                 self.lcdDisabled = False
    #                 self.debug('LCD enabled')
    #             self.updateLCDContrast()

    #         elif high == 0x30:
    #             # Set timer interval.
    #             self.timerInterval = 16192 * (low + 1)
    #             self.debug(f'Set timer interval to {self.timerInterval}')

    #         elif high in (0x80, 0x90):
    #             # Set the LCD contrast.
    #             self.lcdContrast = x - 0x80
    #             self.debug(f'Set lcdContrast to {self.lcdContrast}')
    #             self.updateLCDContrast()

    #         elif high == 0xa0:
    #             # Control LCD effects.
    #             if x == 0xa0:
    #                 self.lcdEffectMirror = False
    #                 self.debug('LCD effect: mirror off')
    #             elif x == 0xa1:
    #                 self.lcdEffectMirror = True
    #                 self.debug('LCD effect: mirror on')
    #             elif x == 0xa4:
    #                 self.lcdEffectBlack = False
    #                 self.debug('LCD effect: black off')
    #             elif x == 0xa5:
    #                 self.lcdEffectBlack = True
    #                 self.debug('LCD effect: black on')
    #             elif x == 0xa6:
    #                 self.lcdEffectReverse = False
    #                 self.debug('LCD effect: reverse off')
    #             elif x == 0xa7:
    #                 self.lcdEffectReverse = True
    #                 self.debug('LCD effect: reverse on')
    #             elif x == 0xa8:
    #                 self.lcdEffectDark = True
    #                 self.debug('LCD effect: dark on')
    #             elif x == 0xa9:
    #                 self.lcdEffectDark = False
    #                 self.debug('LCD effect: dark off')
    #             elif x == 0xae:
    #                 self.lcdEffectWhite = True
    #                 self.debug('LCD effect: white on')
    #             elif x == 0xaf:
    #                 self.lcdEffectWhite = False
    #                 self.debug('LCD effect: white off')
    #             else:
    #                 raise ValueError(f'Unknown LCD effect: {x}')
    #             self.updateLCDContrast()

    #         elif high == 0xb0:
    #             # Set vertical coordinate.
    #             self.lcdY = low
    #             self.debug(f'Set lcdY to {self.lcdY}')

    #         elif high == 0xc0:
    #             # Set LCD trim value.
    #             self.lcdTrim = low
    #             self.debug(f'Set lcdTrim to {self.lcdTrim}')

    #         elif high == 0xe0:
    #             # Special mode commands.
    #             if x == 0xe0:
    #                 self.lcdMod = True
    #                 self.lcdX2 = self.lcdX
    #                 self.debug('Entered modification mode')
    #             elif x == 0xe2:
    #                 # Reset contrast and modification mode.
    #                 self.lcdContrast = 0
    #                 self.lcdMod = False
    #                 self.debug('Reset contrast and modification mode')
    #                 self.updateLCDContrast()
    #             elif x == 0xee:
    #                 self.lcdMod = False
    #                 self.lcdX = self.lcdX2
    #                 self.debug('Exited modification mode, restored lcdX to {self.lcdX}')

    #     def parse_out41(self, x):
    #         if not x:
    #             return
    #         print(f'VRAM[{self.lcdY}][{self.lcdX}] ← {hex(x)}')

    #         self.lcdRead = False
    #         if self.lcdX < self.LCD_WIDTH and self.lcdY < self.LCD_HEIGHT:
    #             self.vram[self.lcdY][self.lcdX] = x & 0xff

    #         # The counter automatically stops at the highest address, A6H.
    #         self.lcdX += math.max(self.lcdX + 1, self.LCD_WIDTH - 1)

    #     def dump_vram(self):
    #         for row in self.vram:
    #             print(" ".join(f"{byte:02X}" for byte in row))

    #     def __str__(self):
    #         state = (
    #             f"lcdX = {self.lcdX}\n"
    #             f"lcdY = {self.lcdY}\n"
    #             f"lcdTop = {self.lcdTop}\n"
    #             f"lcdContrast = {self.lcdContrast}\n"
    #             f"lcdDisabled = {self.lcdDisabled}\n"
    #             f"timerInterval = {self.timerInterval}\n"
    #             f"lcdMod = {self.lcdMod}\n"
    #             f"lcdEffectMirror = {self.lcdEffectMirror}\n"
    #             f"lcdEffectBlack = {self.lcdEffectBlack}\n"
    #             f"lcdEffectReverse = {self.lcdEffectReverse}\n"
    #             f"lcdEffectDark = {self.lcdEffectDark}\n"
    #             f"lcdEffectWhite = {self.lcdEffectWhite}\n"
    #             f"lcdTrim = {self.lcdTrim}\n"
    #         )
    #         return state
    return


@app.cell
def _():
    # 
    return


if __name__ == "__main__":
    app.run()
