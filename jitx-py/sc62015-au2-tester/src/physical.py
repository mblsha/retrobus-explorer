from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlacementSpec:
    x: float
    y: float
    rotation: int = 0

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)


BOARD_WIDTH = 90.0
BOARD_HEIGHT = 72.0
BOARD_CENTER_X = 6.0
MOUNTING_HOLE_DIAMETER = 2.2
MOUNTING_HOLE_PAD_DIAMETER = 3.6
MOUNTING_HOLE_EDGE_INSET = 5.0
MOUNTING_HOLE_CENTERS = (
    (BOARD_CENTER_X - BOARD_WIDTH / 2 + MOUNTING_HOLE_EDGE_INSET, -BOARD_HEIGHT / 2 + MOUNTING_HOLE_EDGE_INSET),
    (BOARD_CENTER_X + BOARD_WIDTH / 2 - MOUNTING_HOLE_EDGE_INSET, -BOARD_HEIGHT / 2 + MOUNTING_HOLE_EDGE_INSET),
    (BOARD_CENTER_X - BOARD_WIDTH / 2 + MOUNTING_HOLE_EDGE_INSET, BOARD_HEIGHT / 2 - MOUNTING_HOLE_EDGE_INSET),
    (BOARD_CENTER_X + BOARD_WIDTH / 2 - MOUNTING_HOLE_EDGE_INSET, BOARD_HEIGHT / 2 - MOUNTING_HOLE_EDGE_INSET),
)
AU2_ELEMENT_ORIGIN = (-27.5, 22.5)
AU2_BANK_CENTER = {"A": (10.5, -18.5), "B": (10.5, 18.5)}
# The 50-pin Au2 power/control connector sits left of Bank A. E_OE uses its
# LED0 pin (element signal L0, connector pin C29).
CONTROL_CONNECTOR_CENTER = (-11.0, -18.5)
CONTROL_CONNECTOR_PAIRS = 25
E_OE_CONTROL_CONNECTOR_PIN = 29

# Keep the Au2 mating element fixed, but translate the complete target-side
# assembly as one unit.  Its CPU center now shares the x coordinate of both
# data-bearing Au2 connector banks.
TOP_ASSEMBLY_SHIFT_X = AU2_BANK_CENTER["A"][0] - (-12.0)


def _top_placement(x: float, y: float, rotation: int = 0) -> PlacementSpec:
    return PlacementSpec(x + TOP_ASSEMBLY_SHIFT_X, y, rotation)


CPU_PLACEMENT = _top_placement(-12.0, 0.0, 90)

# Arrange the level translators around the SC62015 before assigning channels.
# The manufacturable arrangement is a loose ring: two LVC translators above,
# one LVC plus two TXS translators below, two LVC translators to the right,
# and three TXS translators to the left.
# In every pose the B/target-5-V side faces the CPU and the A/Au2-3.3-V side
# faces out toward a routing corridor.
LVC_TRANSLATOR_PLACEMENTS = (
    _top_placement(-16.5, 17.5, 90),  # U2: B side down, toward the CPU
    # U3 needs a real bottom-copper fanout corridor between its A-side
    # production via field and the Au2 B-row pads.  Keep its orientation and
    # x alignment, but move it 5 mm north so the 0.09/0.125-mm trace envelope
    # can fan monotonically without grazing adjacent vias or connector pads.
    _top_placement(-2.5, 27.0, 90),  # U3: B side down; clears connector-side 0402 clusters
    _top_placement(10.0, 7.5, 0),  # U4: B side left, toward the CPU
    _top_placement(10.0, -7.5, 0),  # U5: sparse output bank; B side toward CPU
    _top_placement(-2.5, -18.5, 270),  # U6: data + key banks beside D0-D7/K10-K17
)

# The two south translators are rotated so their B/5-V rows face north. Their
# centers are 7.7 mm apart, leaving 0.2 mm between rotated courtyards. Channel
# assignment follows the CPU edge monotonically, including both package/pin
# gaps, and therefore needs no target-side crossover.
SOUTH_TRANSLATOR_PLACEMENTS = (
    _top_placement(-21.0, -17.5, 90),
    _top_placement(-13.3, -17.5, 90),
)

# Three compact auto-direction translators form one monotonic column along
# the CPU's west edge. Their B/5-V rows face east toward the CPU. The column
# is offset 2 mm farther west to leave a legal two-layer E-port escape corridor.
# The first
# wraps the four nearest north-edge pads into the four west-edge control pads;
# the other two continue down E15..E0. The middle is centered on the CPU, with the
# 7.8/7.7-mm center spacing leaving 0.3/0.2 mm between the 7.5-mm-high
# TSSOP-20 courtyards.
WEST_TRANSLATOR_PLACEMENT = _top_placement(-31.0, 7.8, 0)
E_TRANSLATOR_PLACEMENTS = (
    _top_placement(-31.0, 0.0, 0),
    _top_placement(-31.0, -7.7, 0),
)
TXS_TRANSLATOR_PLACEMENTS = (
    SOUTH_TRANSLATOR_PLACEMENTS[0],
    WEST_TRANSLATOR_PLACEMENT,
    SOUTH_TRANSLATOR_PLACEMENTS[1],
    *E_TRANSLATOR_PLACEMENTS,
)

CONTROL_PULL_PLACEMENTS = {
    "CTRL_OE_N": _top_placement(-11.5, -25.0),
    "KEY_OE_N": _top_placement(-25.0, -25.0),
    "D_OE_N": _top_placement(2.0, -25.0, 90),
    "D_DIR": _top_placement(5.0, -25.0, 90),
    # E_OE now terminates on the control connector's LED0 pin, so its
    # safe-state pull sits just south of that connector.
    "E_OE": _top_placement(-33.0, -22.0),
}

RESET_PULL_PLACEMENT = _top_placement(-24.5, 28.0)
TARGET_BULK_CAP_PLACEMENT = _top_placement(-21.5, 28.0)
TESTPAD_PLACEMENTS = {
    "TARGET": _top_placement(-24.0, -30.0),
    "VDD": _top_placement(-17.0, -30.0),
    "VCC": _top_placement(-10.0, -30.0),
    "VDISP": _top_placement(-3.0, -30.0),
    "VA": _top_placement(4.0, -30.0),
}

AU2_ROW_OFFSET = 1.355
AU2_PAIR_PITCH = 0.4
AU2_PAIRS_PER_CONNECTOR = 40

LVC_A_PIN_NUMBERS = (
    (47, 46, 44, 43, 41, 40, 38, 37),
    (36, 35, 33, 32, 30, 29, 27, 26),
)
LVC_B_PIN_NUMBERS = (
    (2, 3, 5, 6, 8, 9, 11, 12),
    (13, 14, 16, 17, 19, 20, 22, 23),
)
TXS_A_PIN_NUMBERS = (1, 3, 4, 5, 6, 7, 8, 9)
TXS_B_PIN_NUMBERS = (20, 18, 17, 16, 15, 14, 13, 12)


def _rotate(point: tuple[float, float], rotation: int) -> tuple[float, float]:
    x, y = point
    normalized = rotation % 360
    if normalized == 0:
        return (x, y)
    if normalized == 90:
        return (-y, x)
    if normalized == 180:
        return (-x, -y)
    if normalized == 270:
        return (y, -x)
    raise ValueError(f"rotation must be a multiple of 90 degrees, got {rotation}")


def _place(local: tuple[float, float], placement: PlacementSpec) -> tuple[float, float]:
    x, y = _rotate(local, placement.rotation)
    return (x + placement.x, y + placement.y)


def _tssop48_pad_position(pin: int) -> tuple[float, float]:
    if 1 <= pin <= 24:
        return (-3.75, 5.75 - 0.5 * (pin - 1))
    if 25 <= pin <= 48:
        return (3.75, 5.75 - 0.5 * (48 - pin))
    raise ValueError(f"invalid TSSOP-48 pin {pin}")


def _tssop20_pad_position(pin: int) -> tuple[float, float]:
    if 1 <= pin <= 10:
        return (-3.15, 2.925 - 0.65 * (pin - 1))
    if 11 <= pin <= 20:
        return (3.15, 2.925 - 0.65 * (20 - pin))
    raise ValueError(f"invalid TSSOP-20 pin {pin}")


LVC_PIN_COUNT = 48
TXS_PIN_COUNT = 20


@dataclass(frozen=True, slots=True)
class DecouplingSite:
    name: str
    rail: str
    owner_pin: int
    capacitor: PlacementSpec


@dataclass(frozen=True, slots=True)
class TranslatorDecouplingCluster:
    translator: PlacementSpec
    package: str
    sites: tuple[DecouplingSite, ...]


def _decoupling_site(
    translator: PlacementSpec,
    *,
    package_half_width: float,
    pin: int,
    pin_position: tuple[float, float],
    rail: str,
) -> DecouplingSite:
    """Place one owner-relative 0402 beside a physical supply pin.

    Capacitor p[0] is the rail pad and always faces the package.  The 0.25-mm
    courtyard gap includes a 0.05-mm copper-clearance margin for adjacent
    fine-pitch leads. The placement rotates with the translator, so a parent
    placement edit cannot strand or electrically reverse a decoupler.
    """
    pin_x, pin_y = pin_position
    outward_x = 1.0 if pin_x > 0 else -1.0
    cap_local = (outward_x * (package_half_width + 0.25 + 0.85), pin_y)
    cap_rotation_local = 0 if outward_x > 0 else 180
    cap_x, cap_y = _place(cap_local, translator)
    capacitor = PlacementSpec(cap_x, cap_y, (translator.rotation + cap_rotation_local) % 360)

    return DecouplingSite(
        name=f"{rail}-{pin}",
        rail=rail,
        owner_pin=pin,
        capacitor=capacitor,
    )


def translator_decoupling_clusters() -> tuple[TranslatorDecouplingCluster, ...]:
    clusters = []
    for placement in LVC_TRANSLATOR_PLACEMENTS:
        sites = tuple(
            _decoupling_site(
                placement,
                package_half_width=4.25,
                pin=pin,
                pin_position=_tssop48_pad_position(pin),
                rail=rail,
            )
            for rail, pins in (("V3V3", (31, 42)), ("TARGET", (7, 18)))
            for pin in pins
        )
        clusters.append(TranslatorDecouplingCluster(placement, "TSSOP-48", sites))
    for placement in TXS_TRANSLATOR_PLACEMENTS:
        sites = tuple(
            _decoupling_site(
                placement,
                package_half_width=4.1,
                pin=pin,
                pin_position=_tssop20_pad_position(pin),
                rail=rail,
            )
            for rail, pin in (("V3V3", 2), ("TARGET", 19))
        )
        clusters.append(TranslatorDecouplingCluster(placement, "TSSOP-20", sites))
    return tuple(clusters)


TRANSLATOR_DECOUPLING_CLUSTERS = translator_decoupling_clusters()


def lvc_pin_pad_point(translator_index: int, pin: int) -> tuple[float, float]:
    return _place(_tssop48_pad_position(pin), LVC_TRANSLATOR_PLACEMENTS[translator_index])


def txs_pin_pad_point(translator_index: int, pin: int) -> tuple[float, float]:
    return _place(_tssop20_pad_position(pin), TXS_TRANSLATOR_PLACEMENTS[translator_index])


def lvc_a_pad_point(translator_index: int, bank_index: int, channel: int) -> tuple[float, float]:
    pin = LVC_A_PIN_NUMBERS[bank_index][channel]
    return _place(_tssop48_pad_position(pin), LVC_TRANSLATOR_PLACEMENTS[translator_index])


def lvc_b_pad_point(translator_index: int, bank_index: int, channel: int) -> tuple[float, float]:
    pin = LVC_B_PIN_NUMBERS[bank_index][channel]
    return _place(_tssop48_pad_position(pin), LVC_TRANSLATOR_PLACEMENTS[translator_index])


def txs_a_pad_point(translator_index: int, channel: int) -> tuple[float, float]:
    pin = TXS_A_PIN_NUMBERS[channel]
    return _place(_tssop20_pad_position(pin), TXS_TRANSLATOR_PLACEMENTS[translator_index])


def txs_b_pad_point(translator_index: int, channel: int) -> tuple[float, float]:
    pin = TXS_B_PIN_NUMBERS[channel]
    return _place(_tssop20_pad_position(pin), TXS_TRANSLATOR_PLACEMENTS[translator_index])


def cpu_pad_point(signal: str) -> tuple[float, float]:
    # Import locally to avoid pinmap -> physical -> pinmap during module load.
    from src.pinmap import CPU_PIN_NAMES_BY_NUMBER

    pin_index = CPU_PIN_NAMES_BY_NUMBER.index(signal)
    if pin_index < 30:
        local = (-8.7, 9.425 - 0.65 * pin_index)
    elif pin_index < 50:
        local = (-6.175 + 0.65 * (pin_index - 30), -11.7)
    elif pin_index < 80:
        local = (8.7, -9.425 + 0.65 * (pin_index - 50))
    else:
        local = (6.175 - 0.65 * (pin_index - 80), 11.7)
    return _place(local, CPU_PLACEMENT)


def control_pull_anchor_point(name: str) -> tuple[float, float]:
    placement = CONTROL_PULL_PLACEMENTS[name]
    # The Au2/control net is connected to p[0].
    return _place((-0.5, 0.0), placement)


def au2_gpio_pad_point(pin_name: str) -> tuple[float, float]:
    connector = pin_name[0]
    pin = int(pin_name[1:])
    center_x, center_y = AU2_BANK_CENTER[connector]
    pair_index = (pin - 1) // 2
    x = center_x + AU2_PAIR_PITCH * (pair_index - (AU2_PAIRS_PER_CONNECTOR - 1) / 2)
    y = center_y + (AU2_ROW_OFFSET if pin % 2 else -AU2_ROW_OFFSET)
    return (x, y)


def control_connector_pad_point(pin: int) -> tuple[float, float]:
    center_x, center_y = CONTROL_CONNECTOR_CENTER
    pair_index = (pin - 1) // 2
    x = center_x + AU2_PAIR_PITCH * (pair_index - (CONTROL_CONNECTOR_PAIRS - 1) / 2)
    y = center_y + (AU2_ROW_OFFSET if pin % 2 else -AU2_ROW_OFFSET)
    return (x, y)
