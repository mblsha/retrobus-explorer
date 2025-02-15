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


@app.cell(hide_code=True)
def _(data_concat):
    from enum import Enum
    from dataclasses import dataclass
    import struct

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

            if type in [Type.IN_PORT, Type.OUT_PORT]:
                addr &= 0xFF

            r.append(Event(type, val, addr))
        return r, errors

    parsed, errors = parse_data(data_concat)
    errors
    return Enum, Event, Type, dataclass, errors, parse_data, parsed, struct


@app.cell
def _(mo, parsed):
    import pandas
    df = pandas.DataFrame(parsed)
    mo.ui.dataframe(df, page_size=20)
    return df, pandas


@app.cell
def _(df):
    set(df['type'])
    return


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
def _(PCG850Display, Type, df):
    display = PCG850Display()
    rom_bank = None
    ex_bank = None
    xin_enabled = None
    key_strobe = 0

    unhandled_inport = set()
    unhandled_outport = set()

    for r in df.itertuples():
        # print(r.type, r.val, r.addr)
        if r.type == Type.WRITE:
            # print('write')
            pass
        elif r.type in [Type.READ, Type.FETCH]:
            # print('read')
            pass
        elif r.type == Type.IN_PORT:
            # print('in_port')
            # match per r.addr
            match r.addr:
                case 0x10:
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
                case _:
                    unhandled_inport.add(r.addr)
                    # raise ValueError(f"Unknown in_port {hex(r.addr)}")


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

    # print(display)
    display.dump_vram()
    print(f"unhandled_inport: {unhandled_inport}")
    print(f"unhandled_outport: {unhandled_outport}")
    return (
        display,
        ex_bank,
        key_strobe,
        r,
        ram_bank,
        rom_bank,
        unhandled_inport,
        unhandled_outport,
        xin_enabled,
    )


@app.cell
def _():
    class PCG850Display:
        LCD_WIDTH = 166
        LCD_HEIGHT = 9

        def __init__(self):
            self.lcdRead = False     # Flag: whether a read was already performed
            self.lcdMod = False      # Special "modification" mode flag
            self.lcdX = 0            # Current horizontal coordinate (0-255)
            self.lcdX2 = 0           # Backup horizontal coordinate (used in lcdMod)
            self.lcdY = 0            # Current vertical coordinate (0-7)
            self.lcdTop = 0          # Top offset of the display
            self.lcdContrast = 0     # Contrast level (0-?)
            self.lcdDisabled = False # Whether the LCD is disabled
            self.timerInterval = 0   # Timer interval (derived from OUT 0x40 command 0x30)
            self.lcdEffectMirror = False
            self.lcdEffectBlack = False
            self.lcdEffectReverse = False
            self.lcdEffectDark = False
            self.lcdEffectWhite = False
            self.lcdTrim = 0         # LCD trim value

            # Initialize VRAM as a 2D array of bytes (each row is a list of LCD_WIDTH bytes)
            self.vram = [[0 for _ in range(self.LCD_WIDTH)] for _ in range(self.LCD_HEIGHT)]

        def updateLCDContrast(self):
            # In the real system, this would update the LCD hardware contrast.
            # For our simulation, we simply note that the contrast (and effects)
            # have been updated.
            # (You might print or log the new contrast if needed.)
            pass

        def debug(self, str):
            print('>display: ' + str)

        def parse_out40(self, x):
            """
            Parse an OUT command to port 0x40.
            x: integer 0-255 representing the byte written.
            This function decodes the high nibble (x & 0xf0) and then uses the low nibble
            as a parameter.
            """
            self.lcdRead = False
            high = x & 0xf0
            low = x & 0x0f

            if high == 0x00:
                # Set lower nibble of horizontal coordinate if not in lcdMod mode.
                if not self.lcdMod:
                    self.lcdX = (self.lcdX & 0xf0) | low
                    self.debug(f'Set lcdX low to {self.lcdX}')

            elif high == 0x10:
                # Set upper nibble of lcdX.
                if not self.lcdMod:
                    # (x << 4) gives the new high nibble.
                    self.lcdX = ((x & 0xff) << 4) | (self.lcdX & 0x0f)
                    self.debug(f'Set lcdX high to {self.lcdX}')

            elif high == 0x20:
                # Enable/disable the LCD.
                if x == 0x24:
                    self.lcdDisabled = True
                    self.debug('LCD disabled')
                elif x == 0x25:
                    self.lcdDisabled = False
                    self.debug('LCD enabled')
                self.updateLCDContrast()

            elif high == 0x30:
                # Set timer interval.
                self.timerInterval = 16192 * (low + 1)
                self.debug(f'Set timer interval to {self.timerInterval}')

            elif high in (0x40, 0x50, 0x60, 0x70):
                # Set the display "top" offset.
                self.lcdTop = x - 0x40
                self.debug(f'Set lcdTop to {self.lcdTop}')

            elif high in (0x80, 0x90):
                # Set the LCD contrast.
                self.lcdContrast = x - 0x80
                self.debug(f'Set lcdContrast to {self.lcdContrast}')
                self.updateLCDContrast()

            elif high == 0xa0:
                # Control LCD effects.
                if x == 0xa0:
                    self.lcdEffectMirror = False
                    self.debug('LCD effect: mirror off')
                elif x == 0xa1:
                    self.lcdEffectMirror = True
                    self.debug('LCD effect: mirror on')
                elif x == 0xa4:
                    self.lcdEffectBlack = False
                    self.debug('LCD effect: black off')
                elif x == 0xa5:
                    self.lcdEffectBlack = True
                    self.debug('LCD effect: black on')
                elif x == 0xa6:
                    self.lcdEffectReverse = False
                    self.debug('LCD effect: reverse off')
                elif x == 0xa7:
                    self.lcdEffectReverse = True
                    self.debug('LCD effect: reverse on')
                elif x == 0xa8:
                    self.lcdEffectDark = True
                    self.debug('LCD effect: dark on')
                elif x == 0xa9:
                    self.lcdEffectDark = False
                    self.debug('LCD effect: dark off')
                elif x == 0xae:
                    self.lcdEffectWhite = True
                    self.debug('LCD effect: white on')
                elif x == 0xaf:
                    self.lcdEffectWhite = False
                    self.debug('LCD effect: white off')
                else:
                    raise ValueError(f'Unknown LCD effect: {x}')
                self.updateLCDContrast()

            elif high == 0xb0:
                # Set vertical coordinate.
                self.lcdY = low
                self.debug(f'Set lcdY to {self.lcdY}')

            elif high == 0xc0:
                # Set LCD trim value.
                self.lcdTrim = low
                self.debug(f'Set lcdTrim to {self.lcdTrim}')

            elif high == 0xe0:
                # Special mode commands.
                if x == 0xe0:
                    self.lcdMod = True
                    self.lcdX2 = self.lcdX
                    self.debug('Entered modification mode')
                elif x == 0xe2:
                    # Reset contrast and modification mode.
                    self.lcdContrast = 0
                    self.lcdMod = False
                    self.debug('Reset contrast and modification mode')
                    self.updateLCDContrast()
                elif x == 0xee:
                    self.lcdMod = False
                    self.lcdX = self.lcdX2
                    self.debug('Exited modification mode, restored lcdX to {self.lcdX}')

            # Other high values: do nothing

        def parse_out41(self, x):
            """
            Parse an OUT command to port 0x41.
            x: integer 0-255 representing the byte to write to video RAM.
            This writes the data to VRAM at the current (lcdX, lcdY) coordinate,
            then increments lcdX.
            """
            self.lcdRead = False
            if self.lcdX < self.LCD_WIDTH and self.lcdY < self.LCD_HEIGHT:
                self.vram[self.lcdY][self.lcdX] = x & 0xff
            self.debug(f'Wrote {x} to VRAM[{self.lcdY}][{self.lcdX}]')
            self.lcdX += 1

        def dump_vram(self):
            """Print the VRAM contents (for debugging)"""
            for row in self.vram:
                print(" ".join(f"{byte:02X}" for byte in row))

        def __str__(self):
            state = (
                f"lcdX = {self.lcdX}\n"
                f"lcdY = {self.lcdY}\n"
                f"lcdTop = {self.lcdTop}\n"
                f"lcdContrast = {self.lcdContrast}\n"
                f"lcdDisabled = {self.lcdDisabled}\n"
                f"timerInterval = {self.timerInterval}\n"
                f"lcdMod = {self.lcdMod}\n"
                f"lcdEffectMirror = {self.lcdEffectMirror}\n"
                f"lcdEffectBlack = {self.lcdEffectBlack}\n"
                f"lcdEffectReverse = {self.lcdEffectReverse}\n"
                f"lcdEffectDark = {self.lcdEffectDark}\n"
                f"lcdEffectWhite = {self.lcdEffectWhite}\n"
                f"lcdTrim = {self.lcdTrim}\n"
            )
            return state
    return (PCG850Display,)


@app.cell
def _(Tuple, dataclass, display):
    from typing import NamedTuple, Optional, List
    from PIL import Image, ImageDraw

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

    vram = sum(display.vram, [])
    # print(len(vram))
    draw_vram(vram, g850info, display.lcdTop, zoom=4)
    return (
        Image,
        ImageDraw,
        List,
        Machineinfo,
        NamedTuple,
        Optional,
        draw_vram,
        g850info,
        vram,
    )


@app.cell
def _(Image, ImageDraw, display):
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

    draw_vram2(display.vram)
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


@app.cell
def _(Type, df):
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
            # if self.rom_bank != bank:
            #     print(f"Expected rom_bank {hex(self.rom_bank)}, got {hex(bank)}")
            # else:
            #     print(f"!Expected rom_bank {hex(self.rom_bank)}, got {hex(bank)}")
            # assert(self.rom_bank == bank)

        def get_ex_bank(self, bank):
            assert(self.ex_bank is not None)
            # if self.ex_bank != bank:
            #     print(f"Expected ex_bank {self.ex_bank}, got {bank}")
            # assert(self.ex_bank == bank)

        def set_rom_bank(self, bank):
            # print(f"Setting rom_bank to {hex(bank)}")
            self.rom_bank = bank

        def set_ex_bank(self, bank):
            if bank != 0:
                raise ValueError(f"Unexpected ex_bank value: {hex(bank)}")
            # print(f"Setting ex_bank to {hex(bank)}")
            self.ex_bank = bank

        def get_ram_bank(self, bank):
            pass

        def set_ram_bank(self, bank):
            self.ram_bank = bank

        def write(self, addr, val):
            if addr > self.RAM_ADDR_START and addr < self.ROM0_ADDR_START:
                self.ram[addr] = val
            # if addr > self.ROM0_ADDR_START:
            #     print(f"Unexpected write to ROM region: {hex(addr)}: {hex(val)}")
            pass

        def read(self, addr, val):
            pass
            # if self.i > 10:
            #     return

            # if addr > self.ROM0_ADDR_START:
            #     print(f'addr: {hex(addr)}, val: {hex(val)}')

            # if rom_bank is None:
            #     return

            # if addr > self.ROM0_ADDR_START and addr < self.BANK_ADDR_START:
            #     self.i += 1
            #     expect = rom_banks[0][addr - self.ROM0_ADDR_START]
            #     if val != expect:
            #         print(f"0mismatch at {hex(addr)}: {hex(val)} != {hex(expect)}")
            #     else:
            #         print(f"0match at {hex(addr)}: {hex(val)} == {hex(expect)}")


    def verify_rom_memory():
        verifier = RomVerifier()

        # IO Port documentation:
        # http://park19.wakwak.com/~gadget_factory/factory/pokecom/io.html
        for r in df.itertuples():
            # print(r.type, r.val, r.addr)
            if r.type == Type.WRITE:
                # verifier.write(r.addr, r.val)
                pass
            elif r.type in [Type.READ, Type.FETCH]:
                # verifier.read(r.addr, r.val)
                pass
            elif r.type == Type.IN_PORT:
                match r.addr:
                    case 0x19:
                        # rom_bank = r.val & 0x0F
                        # ex_bank = (r.val & 0x70) >> 4
                        # verifier.get_rom_bank(rom_bank)
                        # verifier.get_ex_bank(ex_bank)
                        pass
                    case 0x1b:
                        # verifier.get_ram_bank(r.val)
                        pass
                    case 0x69:
                        # verifier.get_rom_bank(r.val)
                        pass
                    case _:
                        pass
            elif r.type == Type.OUT_PORT:
                match r.addr:
                    case 0x19:
                        # rom_bank = r.val & 0x0F
                        # ex_bank = (r.val & 0x70) >> 4
                        # verifier.set_rom_bank(rom_bank)
                        # verifier.set_ex_bank(ex_bank)
                        pass
                    case 0x1b:
                        # verifier.set_ram_bank(r.val)
                        pass
                    case 0x69:
                        # verifier.set_rom_bank(r.val)
                        pass
                    case 0x6f:
                        print('foo')
                    case _:
                        pass
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
def _(df_for_plot, df_valh):
    df_valh(df_for_plot)
    return


@app.cell
def _():
    from z80dis import z80
    z80.disasm(b'\xed\xb0', 10)
    return (z80,)


@app.cell
def _(Type, df_for_plot):
    def df_valh(df):
        df2 = df.copy()
        df2['addrh'] = df2['addr'].apply(lambda x: hex(x))
        df2['valh'] = df2['val'].apply(lambda x: hex(x))
        return df2

    def io_df(df):
        df2 = df[df['type'].isin([Type.IN_PORT, Type.OUT_PORT])].copy()
        return df_valh(df2)
        
    io_df(df_for_plot)
    return df_valh, io_df


@app.cell
def _(df):
    # filter df to be only reads within 0x1000 and 0x2000
    df2 = df[(df['addr'] >= 0x5500) & (df['addr'] < 0x5600)]

    # sort them by addr and convert val to hex
    df2 = df2.sort_values(by=['addr'])
    df2['addrh'] = df2['addr'].apply(lambda x: hex(x))
    df2['valh'] = df2['val'].apply(lambda x: hex(x))
    df2 = df2.drop_duplicates()
    return (df2,)


@app.cell
def _(df2):
    df2
    return


@app.cell
def _(df):
    # goal is to inspect all reads around 0x1000 to figure out why there are skips

    start_row = 3502261
    df_sel = df.iloc[start_row : start_row + 21]
    df_sel['addrh'] = df_sel['addr'].apply(lambda x: hex(x))
    df_sel['valh']  = df_sel['val'].apply(lambda x: hex(x))
    df_sel
    return df_sel, start_row


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
