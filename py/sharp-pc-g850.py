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
                    """The returned value (stored in the location pointed to by x) is built up by checking individual bits in the variable keyStrobe.
    For each bit that is set in keyStrobe, a corresponding element from the keyMatrix array is OR‑ed into the result.
    For example, if bit 0 (0x001) is set in keyStrobe, then keyMatrix[0] is included in the result.
    Interpretation:
    The result is a bit‑mask that represents which keys (or key groups) are currently “active” (i.e. pressed) for the rows/columns selected by the strobe.
    The exact mapping depends on how the key matrix is arranged on your calculator, but essentially each bit in the returned value indicates the state (pressed or not) of keys in one of the rows."""
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
                    """How to Interpret the Passed‑in Value:

    The Entire 8‑bit Value:
    The value written to port 0x11 is stored in keyStrobeLast and then OR‑ed into keyStrobe. This value acts as a bit‑mask that selects which parts of the key matrix will be read by the input routine on port 0x10.
    Bit 4 (0x10):
    If bit 4 is set in the written value, then the code additionally sets an interrupt flag (INTERRUPT_IA) in the interruptType register. This likely signals the CPU that a key‐action has occurred.
    Interpretation:
    To “select” a particular key (or group of keys), you write a value with the corresponding bit set. For example, writing 0x01 means “activate key matrix group 0,” writing 0x02 means “activate group 1,” and so on.
    In many designs, multiple strobe lines might be combined. Here the code even OR‑s new strobe bits into keyStrobe so that successive writes accumulate until they are cleared by the timing logic.
    Practical Note:
    When you send a byte to port 0x11, check its bits to determine which key row(s) it is selecting. Also note that setting bit 4 (0x10) will trigger an interrupt for key input processing."""
                    key_strobe |= r.val
                    print(f"write key_strobe: {hex(key_strobe)}")
                case 0x12:
                    """The byte you write is shifted left 8 bits and then OR‑ed into a “key strobe” mask.
    Meaning of the bits:
    The final 16‑bit value (keyStrobe) controls which parts of the key matrix are being “strobed” (i.e. activated for scanning).
    In the complementary input routine (port 0x10, not listed here) the bits of this strobe mask determine which rows (or columns) of the key matrix are read from the corresponding keyMatrix[] entries.
    For example, writing 0x01 results in 0x0100; that sets bit 8, which (by the code’s convention) selects one particular key line."""
                    key_strobe = (r.val << 8) & 0xFF00
                    print(f"write key_strobe: {hex(key_strobe)}")
                case 0x15:
                    """Only bit 7 of the written value matters.
    If bit 7 is set: xinEnabled becomes nonzero (typically 0x80), meaning the “Xin” input is enabled.
    If bit 7 is clear: xinEnabled is 0, disabling the Xin input.
    How to use it: Interpret the value as a flag—bit 7 = 1 means “enable external input (Xin)”; otherwise, disable it."""
                    xin_enabled = r.val & 0x80
                    print(f"write xin_enabled: {xin_enabled}")
                    pass
                case 0x16:
                    """The output byte is used as a mask to clear bits in the interruptType register.
    Each bit set to 1 in x: Causes the corresponding bit in interruptType to be cleared.
    How to use it: When you write a value here, each 1‑bit signals that you wish to acknowledge (or “clear”) that particular interrupt request. For example, writing 0x01 clears interrupt flag bit 0."""
                    print(f"write interruptType: {hex(r.val)}")
                    pass
                case 0x19:
                    """The byte is split into two parts:
    Lower nibble (bits 0–3):
    Taken modulo the total number of ROM banks, this value selects the new ROM bank.
    Bits 4–6 (x & 0x70, then shifted right by 4):
    These bits select the external ROM (EXROM) bank.
    How to use it:
    To select a given memory bank configuration, pack the desired ROM bank number into the lower 4 bits and the desired EXROM bank (0–7) into bits 4–6.
    For example, writing 0x23 means “select ROM bank 3 and EXROM bank 2.”"""
                    rom_bank = r.val & 0x0F
                    ex_bank = (r.val & 0x70) >> 4
                    print(f"write rom_bank: {rom_bank}, ex_bank: {ex_bank}")
                    pass
                case 0x1a:
                    print(f"boot rom on/off: {r.val}")
                case 0x1b:
                    """Only bit 2 (mask 0x04) of the written value is used.
    If (x & 0x04) is different from the current ramBank:
    The code swaps 0x8000 bytes between the main memory and external RAM (exram).
    How to use it:
    Write either 0x00 or 0x04 to select between two RAM banks. The value tells the system which bank is active."""
                    ram_bank = r.val & 0x04
                    print(f"write ram_bank: {ram_bank}")
                    pass
                case 0x1e:
                    """How to Interpret the Passed‑in Value:

    Value Masking:
    Only the lower two bits of the value (mask 0x03) are used.
    Interpretation:
    The value written sets the battery check mode by storing x & 0x03 into the variable battChk.
    For example:
    Writing 0x00 → battery check mode 0
    Writing 0x01 → mode 1
    Writing 0x02 → mode 2
    Writing 0x03 → mode 3
    What It Means:
    Although the provided code for the battery state (in port 0x1D) always returns 0, the mode set via port 0x1E would typically affect how the battery status is measured or reported. It might be used to select thresholds or to initiate a battery test sequence."""
                    print(f"write battery check mode: {r.val & 0x03}")
                case 0x40:
                    display.parse_out40(r.val)
                case 0x41:
                    display.parse_out41(r.val)
                case 0x69:
                    """The value written is treated as the desired ROM bank number.
    How to use it:
    Simply write the bank number you wish to activate. If the value differs from the current bank, the routine calls swrom() to remap the ROM into the CPU’s address space. (Typically, only the lower 4 bits are significant.)"""
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


app._unparsable_cell(
    r"""
        LCD_WIDTH = 166
        LCD_HEIGHT = 8

        def __init__(self):
            self.lcdRead = False     # Flag: whether a read was already performed
            self.lcdMod = False      # Special \"modification\" mode flag
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
            \"\"\"
            Parse an OUT command to port 0x40.
            x: integer 0-255 representing the byte written.
            This function decodes the high nibble (x & 0xf0) and then uses the low nibble
            as a parameter.
            \"\"\"
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
                # Set the display \"top\" offset.
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
            \"\"\"
            Parse an OUT command to port 0x41.
            x: integer 0-255 representing the byte to write to video RAM.
            This writes the data to VRAM at the current (lcdX, lcdY) coordinate,
            then increments lcdX.
            \"\"\"
            self.lcdRead = False
            if self.lcdX < self.LCD_WIDTH and self.lcdY < self.LCD_HEIGHT:
                self.vram[self.lcdY][self.lcdX] = x & 0xff
            self.debug(f'Wrote {x} to VRAM[{self.lcdY}][{self.lcdX}]')
            self.lcdX += 1

        def dump_vram(self):
            \"\"\"Print the VRAM contents (for debugging)\"\"\"
            for row in self.vram:
                print(\" \".join(f\"{byte:02X}\" for byte in row))

        def __str__(self):
            state = (
                f\"lcdX = {self.lcdX}\n\"
                f\"lcdY = {self.lcdY}\n\"
                f\"lcdTop = {self.lcdTop}\n\"
                f\"lcdContrast = {self.lcdContrast}\n\"
                f\"lcdDisabled = {self.lcdDisabled}\n\"
                f\"timerInterval = {self.timerInterval}\n\"
                f\"lcdMod = {self.lcdMod}\n\"
                f\"lcdEffectMirror = {self.lcdEffectMirror}\n\"
                f\"lcdEffectBlack = {self.lcdEffectBlack}\n\"
                f\"lcdEffectReverse = {self.lcdEffectReverse}\n\"
                f\"lcdEffectDark = {self.lcdEffectDark}\n\"
                f\"lcdEffectWhite = {self.lcdEffectWhite}\n\"
                f\"lcdTrim = {self.lcdTrim}\n\"
            )
            return state
    """,
    name="_"
)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
