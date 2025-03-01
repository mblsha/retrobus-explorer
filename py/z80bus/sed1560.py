# SED1560 is an LCD controller from SHARP PC-G850.

from enum import Enum
from dataclasses import dataclass
from PIL import Image, ImageDraw
import multiprocessing as mp
import threading
import queue
import datetime
import copy

from typing import List
import pandas

from bus_parser import (
    Event,
    ErrorType,
    Type,
    IOPort,
)


class SED1560:
    class CmdAType(Enum):
        SET_RAM_SEGMENT_OUTPUT = 0x0  # 0: Normal, 1: Inverse
        DISPLAY_ON = 0xE  # 0: Off, 1: On
        DISPLAY_MODE = 0x6  # 0: Normal, 1: Inverse
        SEGMENTS_DISPLAY_MODE = 0x4  # 0: Normal, 1: All display segments On
        LCD_CONTROLLER_DUTY1 = 0x8  # See Table 5.3
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
        cmd: "SED1560.CmdAType"
        value: int

    @dataclass
    class SetCommonSegmentOutput:
        scanning_direction: int
        case: int

    @dataclass
    class SetColumnPart:
        # True if updating the high nibble, False for low nibble
        is_high: bool
        # if is_high, the value is already shifted by 4 bits
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
                scanning_direction=scanning_direction, case=case
            )
        elif high in [0x0, 0x1]:
            # Column address command: update column based on high/low nibble.
            if high:  # high nibble update
                col = low << 4
                is_high = True
            else:  # low nibble update
                col = low
                is_high = False
            return SED1560.SetColumnPart(is_high=is_high, value=col)
        else:
            raise ValueError(SED1560.Unknown(addr=0x40, value=x))

    @staticmethod
    def parse_out41(x: int):
        return SED1560.VRAMWrite(value=x)

    @staticmethod
    def parse_bus_commands(events):
        commands = []

        def iterate(r):
            parsed = None
            if r.port == IOPort.LCD_COMMAND:
                parsed = SED1560Parser.parse_out40(r.val)
            elif r.port == IOPort.LCD_OUT:
                parsed = SED1560Parser.parse_out41(r.val)
            else:
                parsed = SED1560.Unknown(addr=r.port.value, value=r.val)
            commands.append(parsed)

        # events is either dataframe or List[Event]
        if isinstance(events, pandas.DataFrame):
            for r in events.itertuples():
                iterate(r)
        else:
            for r in events:
                iterate(r)

        processed = []
        i = 0
        while i < len(commands):
            match commands[i : i + 3]:
                # for some reason InitialDisplayLine is always between two SetColumnPart commands
                case [
                    SED1560.SetColumnPart(is_high=False, value=low),
                    cmd,
                    SED1560.SetColumnPart(is_high=True, value=high),
                ]:
                    processed.append(SED1560.SetColumn(value=low | high))
                    processed.append(cmd)
                    i += 3
                case [
                    SED1560.SetColumnPart(is_high=True, value=high),
                    cmd,
                    SED1560.SetColumnPart(is_high=False, value=low),
                ]:
                    processed.append(SED1560.SetColumn(value=low | high))
                    processed.append(cmd)
                    i += 3
                case _:
                    processed.append(commands[i])
                    i += 1
        return processed

    @staticmethod
    def parsed_commands_to_df(processed):
        result = []
        for index, parsed in enumerate(processed):
            parsed_type = type(parsed).__name__
            # if CmdA, then get type from parsed.cmd
            if parsed_type == "CmdA":
                parsed_type = parsed.cmd.name
            if parsed_type == "Unknown":
                parsed_type = IOPort(parsed.addr).name

            result.append({"index": index, "type": parsed_type, **vars(parsed)})
        return pandas.DataFrame(result)


# TODO: use info from https://www.akiyan.com/pc-g850_technical_data
# to implement the remaining commands.
class SED1560Interpreter:
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
        self.vram = [[0 for _ in range(self.LCD_WIDTH)] for _ in range(self.LCD_HEIGHT)]

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
            case SED1560.SetCommonSegmentOutput(
                scanning_direction=direction, case=case
            ):
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
            case SED1560.SetColumnPart(is_high=is_high, value=value):
                if is_high:
                    self.col = (self.col & 0x0F) | value
                else:
                    self.col = (self.col & 0xF0) | value
            case SED1560.Unknown(addr=addr, value=value):
                pass
            case _:
                raise ValueError(f"Unhandled command: {cmd}")

    def vram_image(self, zoom=4):
        off_color = (0, 0, 0)
        on_color = (0, 255, 0)

        img_width = len(self.vram[0]) * zoom
        img_height = len(self.vram) * 6 * zoom
        image = Image.new("RGB", (img_width, img_height), off_color)
        draw = ImageDraw.Draw(image)

        for row in range(len(self.vram)):
            for col in range(len(self.vram[row])):
                byte = self.vram[row][col]
                for bit in range(8):
                    pixel_state = (byte >> bit) & 1
                    color = on_color if pixel_state else off_color

                    dx = col
                    dy = row * 8 + bit
                    draw.rectangle(
                        [
                            dx * zoom,
                            dy * zoom,
                            dx * zoom + zoom - 1,
                            dy * zoom + zoom - 1,
                        ],
                        fill=color,
                    )

        return image


def interpret_lcd_thread(input_queue, display_queue, status_queue):
    last_output = None
    display = SED1560Interpreter()

    status_num_evals = 0
    status_num_empty_queue = 0
    status_num_draws = 0
    status_num_display_not_ready = 0

    while True:
        data = input_queue.get()
        # print(f'LCD: got {data}')
        if data is None:
            break

        try:
            for e in SED1560Parser.parse_bus_commands([data]):
                # print(e)
                status_num_evals += 1
                display.eval(e)
        except Exception as e:
            print(e)
            continue

        # print(f'LCD: {display.col} {display.page}')
        # print(f'last_output is None: {last_output is None} or last_output != display.vram: {last_output != display.vram}')
        if last_output is None or last_output != display.vram:
            if display_queue.empty():
                print("LCD: putting")
                status_num_draws += 1
                last_output = copy.deepcopy(display.vram)
                display_queue.put(display.vram_image())
            else:
                status_num_display_not_ready += 1

    display_queue.put(None)
    status_queue.put(
        {
            "num_evals": status_num_evals,
            "num_draws": status_num_draws,
            "num_display_not_ready": status_num_display_not_ready,
            "num_empty_queue": status_num_empty_queue,
        }
    )
    print("interpret_lcd_thread done")


class DrawLCDContext:
    def __init__(self, input_queue, display_queue):
        self.input_queue = input_queue
        self.display_queue = display_queue
        self.status_queue = mp.Queue()
        self.process = mp.Process(
            target=interpret_lcd_thread,
            args=(input_queue, display_queue, self.status_queue),
        )
        # self.process = threading.Thread(
        #     target=interpret_lcd_thread, args=(input_queue, display_queue)
        # )

    def __enter__(self):
        self.process.start()
        print(f'DrawLCDContext: pid {self.process.pid}')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.input_queue.put(None)
        print(f"DrawLCDContext: exit1 {datetime.datetime.now()}")
        self.process.join()
        print(f"DrawLCDContext: exit2 {datetime.datetime.now()}")

        self.display_queue.put(None)
        print(self.status_queue.get())
