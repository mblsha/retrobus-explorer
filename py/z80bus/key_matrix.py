from dataclasses import dataclass

from z80bus.bus_parser import Event, IOPort

# https://ver0.sakura.ne.jp/doc/pcg800iocs.html shows how the keycodes are mapped
# to the key matrix.

# SET_KEY_STROBE are rows
# KEY_INPUT are columns
KEY_MATRIX = [
    ["OFF", "Q", "W", "E", "R", "T", "Y", "U"],
    ["A", "S", "D", "F", "G", "H", "J", "K"],
    ["Z", "X", "C", "V", "B", "N", "M", ","],
    ["BASIC", "TEXT", "CAPS", "カナ", "⇥", "␣", "↓", "↑"],
    ["←", "→", "ANS", "0", ".", "=", "+", "↩"],
    ["L", ";", "CONST", "1", "2", "3", "−", "M+"],
    ["I", "O", "INS", "4", "5", "6", "∗", "R•CM"],
    ["P", "⌫", "π", "7", "8", "9", "/", ")"],
    ["nPr", "→DEG", "√", "x²", "yˣ∧", "(", "1/x", "MDF"],
    ["2nd F", "SIN", "COS", "ln", "LOG", "TAN", "F↔E", "CLS"],
]


@dataclass
class PressedKey:
    row: int
    col: int

    def __hash__(self):
        return hash((self.row, self.col))

    def __str__(self):
        if self.row == 0xff and self.col == 0xff:
            return "SHIFT"
        return KEY_MATRIX[self.row][self.col]


@dataclass
class KeyMatrixState:
    pressed_keys: list[PressedKey]
    shift_pressed: bool


class KeyMatrixInterpreter:
    def __init__(self):
        # strobing rows
        self.strobe_hi = 0
        self.strobe_lo = 0
        self.cur = []
        self.last_full_state = []
        self.last_shift_state = False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, KeyMatrixInterpreter):
            return NotImplemented
        return (
            self.strobe_hi == other.strobe_hi
            and self.strobe_lo == other.strobe_lo
            and self.cur == other.cur
            and self.last_full_state == other.last_full_state
            and self.last_shift_state == other.last_shift_state
        )

    def pressed_keys(self):
        if self.last_shift_state:
            return self.last_full_state + [PressedKey(row=0xff, col=0xff)]
        return self.last_full_state

    def __str__(self):
        r = []
        if self.last_shift_state:
            r.append("SHIFT")
        for k in self.last_full_state:
            r.append(str(k))
        return ", ".join(r)

    # string representation

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
                row = self._row_from_strobe(strobe)
                for i in range(8):
                    if event.val & (1 << i):
                        self.cur.append(PressedKey(row=row, col=i))
            case IOPort.SHIFT_KEY_INPUT:
                # key matrix scanning ends with SHIFT_KEY_INPUT query
                self.last_full_state = self.cur.copy()
                self.last_shift_state = event.val
                self.cur = []

    @staticmethod
    def _row_from_strobe(strobe: int) -> int:
        """Return the index of the active row for the given strobe mask."""
        return strobe.bit_length() - 1
