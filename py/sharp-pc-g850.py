import marimo

__generated_with = "0.11.0"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _():
    import sys
    sys.path.append("d3xx")

    import ftd3xx
    import _ftd3xx_linux as mft
    return ftd3xx, mft, sys


@app.cell
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


@app.cell
def _(Ft600Device):
    import datetime
    import time

    def GetBusData(num_seconds_before_timeout=5):
        print(datetime.datetime.now())

        with Ft600Device() as d:
            # clear input buffer
            for i in range(100):
                bytes = d.read(256)

            print('Ready...')
            data = []

            start = datetime.datetime.now()
            while True:
                bytes = d.read(256)
                now = datetime.datetime.now()
                if bytes is None:
                    if (now - start).total_seconds() > num_seconds_before_timeout:
                        break
                    continue
                start = now
                data.append(bytes)

            print(f'Done. Received {len(data)} packets.')
            return data

            # print(d.write(b'--'))
            # print(d.write(b'++'))

    # DemoLoopback()
    data_lines = GetBusData()
    data_concat = b''.join(data_lines)
    print(f"Received {len(data_concat)} bytes")
    return GetBusData, data_concat, data_lines, datetime, time


@app.cell
def _(data_concat):
    from enum import Enum
    from dataclasses import dataclass
    import struct

    class Type(Enum):
        READ = "R"
        WRITE = "W"
        IN_PORT = "r"
        OUT_PORT = "w"

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

            # val  = struct.unpack("B", i[1:2])[0]
            # addr = struct.unpack("H", i[2:4])[0]
            val  = struct.unpack("B", data[offset+1:offset+2])[0]
            addr = struct.unpack("H", data[offset+2:offset+4])[0]
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
        elif r.type == Type.READ:
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
def _():
    a = 8
    1 + (a % 8 != 0)
    return (a,)


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
def _(display):
    display.vram
    return


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


@app.cell
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
def _(Type, banks, df):
    def verify_rom_memory():
        rom_bank = None
        ex_bank = None
        ram_bank = None

        i = 0

        for r in df.itertuples():
            # print(r.type, r.val, r.addr)
            if r.type == Type.WRITE:
                # print('write')
                pass
            elif r.type == Type.READ:
                # print('read')
                if rom_bank is None:
                    continue

                bank_start = 0xC000
                if r.addr > bank_start:
                    for bank in banks:
                        bank_size = len(banks[bank])
                        expect = banks[bank][r.addr - bank_start]
                        if r.val != expect:
                            print(f"mismatch at {hex(r.addr)}: {hex(r.val)} != {hex(expect)}")
                        else:
                            print(f"match at {hex(r.addr)}: {hex(r.val)} == {hex(expect)}")
                print(hex(r.addr))
                print(rom_bank)
                print(ex_bank)
                i += 1
                if i > 10:
                    return
                pass
            elif r.type == Type.IN_PORT:
                match r.addr:
                    case 0x19:
                        assert(rom_bank is not None)
                        assert(ex_bank is not None)
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        # print(f"read rom_bank: {rom_bank}, ex_bank: {ex_bank}")
                        pass
                    case 0x69:
                        assert(rom_bank is not None)
                        rom_bank = r.val & 0x0F
                        # print(f"read rom_bank: {rom_bank}")
                        pass
                    case _:
                        pass
            elif r.type == Type.OUT_PORT:
                match r.addr:
                    case 0x19:
                        rom_bank = r.val & 0x0F
                        ex_bank = (r.val & 0x70) >> 4
                        # print(f"write rom_bank: {rom_bank}, ex_bank: {ex_bank}")
                        pass
                    case 0x1b:
                        ram_bank = r.val & 0x04
                        # print(f"write ram_bank: {ram_bank}")
                        pass
                    case 0x69:
                        rom_bank = r.val & 0x0F
                        # print(f"write rom_bank: {rom_bank}")
                        pass
                    case _:
                        pass
            else:
                raise ValueError(f"Unknown type {r.type}")

    verify_rom_memory()
    return (verify_rom_memory,)


if __name__ == "__main__":
    app.run()
