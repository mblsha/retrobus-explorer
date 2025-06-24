
from z80bus.bus_parser import IOPort
from z80bus.sed1560 import SED1560, SED1560Interpreter, SED1560Parser
from z80bus.test_bus_parser import normal_parse, out_port

# Type alias for all possible SED1560 command types
SED1560Command = (
    SED1560.InitialDisplayLine
    | SED1560.Contrast
    | SED1560.PowerOn
    | SED1560.PowerOnComplete
    | SED1560.SetPageAddress
    | SED1560.CmdA
    | SED1560.SetCommonSegmentOutput
    | SED1560.SetColumnPart
    | SED1560.SetColumn
    | SED1560.VRAMWrite
    | SED1560.Unknown
)


def parse40(val: int) -> SED1560Command:
    return SED1560Parser.parse_out40(val)  # type: ignore[no-any-return]


def parse41(val: int) -> SED1560.VRAMWrite:
    return SED1560Parser.parse_out41(val)  # type: ignore[no-any-return]


def parse(data: bytes) -> list[SED1560Command]:
    events, errors = normal_parse(data)
    assert len(errors) == 0
    return SED1560Parser.parse_bus_commands(events)  # type: ignore[no-any-return]


def interpret(data: bytes) -> SED1560Interpreter:
    r = SED1560Interpreter()
    for e in parse(data):
        r.eval(e)
    return r


def test_out41():
    assert parse41(0x00) == SED1560.VRAMWrite(value=0x00)


def out_cmd(value: int) -> bytes:
    return out_port(value, IOPort.LCD_COMMAND)


def out_data(value: int) -> bytes:
    return out_port(value, IOPort.LCD_OUT)


def test_parse_bus_commands():
    assert parse(b"") == []
    assert parse(out_cmd(0x00)) == [SED1560.SetColumnPart(is_high=False, value=0x00)]
    assert parse(out_data(0x12)) == [SED1560.VRAMWrite(value=0x12)]


def test_set_column_part():
    if not SED1560Parser.COMBINE_SET_COLUMN_PART:
        return

    assert parse40(0x00) == SED1560.SetColumnPart(is_high=False, value=0x00)
    assert parse40(0x0F) == SED1560.SetColumnPart(is_high=False, value=0x0F)
    assert parse40(0x10) == SED1560.SetColumnPart(is_high=True, value=0x00)
    assert parse40(0x1F) == SED1560.SetColumnPart(is_high=True, value=0xF0)

    assert parse(out_cmd(0x12) + out_data(0x12) + out_cmd(0x03)) == [
        SED1560.SetColumn(value=0x23),
        SED1560.VRAMWrite(value=0x12),
    ]
    assert parse(out_cmd(0x04) + out_data(0x12) + out_cmd(0x15)) == [
        SED1560.SetColumn(value=0x54),
        SED1560.VRAMWrite(value=0x12),
    ]


def test_interpret_columns():
    assert interpret(out_cmd(0x02)).col == 0x02
    assert interpret(out_cmd(0x13)).col == 0x30

