from z80bus.bus_parser import IOPort, Event, Type
import copy
import math


class KeyMatrixInterpreter:
    def __init__(self):
        self.strobe_hi = 0
        self.strobe_lo = 0
        self.cur = []
        self.last_full_state = []

    def __eq__(self, other):
        return (
            self.strobe_hi == other.strobe_hi
            and self.strobe_lo == other.strobe_lo
            and self.cur == other.cur
            and self.last_full_state == other.last_full_state
        )

    def pressed_keys(self):
        return self.last_full_state

    def eval(self, event: Event):
        match event.port:
            case IOPort.SET_KEY_STROBE_HI:
                # only two lower bits are used, rest should be ignored
                self.strobe_hi = event.val & 0b11
            case IOPort.SET_KEY_STROBE_LO:
                self.strobe_lo = event.val
            case IOPort.KEY_INPUT:
                strobe = (self.strobe_hi << 8) | self.strobe_lo
                if event.val == 0 or strobe == 0:
                    return
                # column is the power of 2 of the strobe value, only has 1 bit set
                column = int(math.log2(strobe))
                for i in range(8):
                    if event.val & (1 << i):
                        row = i
                        self.cur.append((column, i))
            case IOPort.SHIFT_KEY_INPUT:
                # key matrix scanning ends with SHIFT_KEY_INPUT query
                self.last_full_state = copy.deepcopy(self.cur)
                self.cur = []
