from z80bus.bus_parser import IOPort
from z80bus.key_matrix import KeyMatrixInterpreter, PressedKey
from z80bus.test_bus_parser import in_port, normal_parse, out_port


def eval(data: bytes) -> KeyMatrixInterpreter:
    r = KeyMatrixInterpreter()
    events, errors = normal_parse(data)
    assert len(errors) == 0
    for e in events:
        r.eval(e)
    return r


def test_key_matrix():
    assert eval(b"") == KeyMatrixInterpreter()
    assert eval(out_port(0x00, IOPort.SET_KEY_STROBE_HI)).strobe_hi == 0
    assert eval(out_port(0xF0, IOPort.SET_KEY_STROBE_HI)).strobe_hi == 0
    assert eval(out_port(0xF1, IOPort.SET_KEY_STROBE_HI)).strobe_hi == 1
    assert eval(out_port(0xFF, IOPort.SET_KEY_STROBE_HI)).strobe_hi == 3

    assert eval(out_port(0xFF, IOPort.SET_KEY_STROBE_LO)).strobe_lo == 0xFF
    assert eval(out_port(0x00, IOPort.SET_KEY_STROBE_LO)).strobe_lo == 0x00

    # can only scan when both strobe colum and row bits have non-zero bits
    assert eval(in_port(0xFF, IOPort.KEY_INPUT)).cur == []
    assert eval(
        out_port(0x01, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x00, IOPort.KEY_INPUT)
    ).cur == []

    assert eval(
        out_port(0x01, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x01, IOPort.KEY_INPUT)
    ).cur == [PressedKey(row=0, col=0)]
    assert eval(
        out_port(0x01, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x02, IOPort.KEY_INPUT)
    ).cur == [PressedKey(row=0, col=1)]
    assert eval(
        out_port(0x01, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x03, IOPort.KEY_INPUT)
    ).cur == [PressedKey(row=0, col=0), PressedKey(row=0, col=1)]
    assert eval(
        out_port(0x02, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x02, IOPort.KEY_INPUT)
    ).cur == [PressedKey(row=1, col=1)]

    assert eval(
        out_port(0x01, IOPort.SET_KEY_STROBE_HI)
        + out_port(0x00, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x01, IOPort.KEY_INPUT)
    ).cur == [PressedKey(row=8, col=0)]

    assert eval(
        out_port(0x02, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x02, IOPort.KEY_INPUT)
        + in_port(0x00, IOPort.SHIFT_KEY_INPUT)
    ).cur == []
    assert str(eval(
        out_port(0x02, IOPort.SET_KEY_STROBE_LO)
        + in_port(0x02, IOPort.KEY_INPUT)
        + in_port(0x00, IOPort.SHIFT_KEY_INPUT)
    )) == "S"
