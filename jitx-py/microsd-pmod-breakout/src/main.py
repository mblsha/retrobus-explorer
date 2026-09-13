from __future__ import annotations

from math import cos, radians, sin
from pathlib import Path

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.copper import Pour
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Port
from jitx.placement import Placement, Side
from jitx.shapes.primitive import Anchor, Arc, ArcPolygon, Text
from jitx.substrate import Substrate
from jitx.via import Via, ViaType
from shared_components.fabrication import JlcpcbTwoLayer08Stackup, JlcpcbTwoLayerFabConstraints
from shared_components.graphics import bottom_side_text as bottom_text
from shared_components.metadata import git_revision_date
from shared_components.micro_sd import (
    MICRO_SD_CARD_SHOULDER_X,
    MICRO_SD_DATA_PORTS,
    MICRO_SD_EDGE_ORIGIN,
    MICRO_SD_EDGE_PAD_CENTERS,
    MICRO_SD_EDGE_ROTATION,
    MicroSdCardEdge,
    micro_sd_card_outline,
)
from shared_components.nets import connect_ports
from shared_components.pmod import (
    PMOD_DATA_PINS,
    PMOD_PAD_CENTERS,
    PMOD_PAD_DIAMETER,
    PMOD_PIN_NAMES,
    PMOD_ROW_SPACING,
    PmodHeader2x6,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = git_revision_date(REPO_ROOT)
BOARD_THICKNESS_MM = 0.8
BOARD_CENTER_Y = 5.5
BOARD_BOTTOM_Y = -3.75
BOARD_TOP_Y = 14.75
BOARD_HEIGHT = BOARD_TOP_Y - BOARD_BOTTOM_Y
TAIL_CHAMFER_X = MICRO_SD_CARD_SHOULDER_X + 3.0
PMOD_ORIGIN = (27.0, BOARD_CENTER_Y)
BOTTOM_HEADER_ROTATION = 0.0
TOP_HEADER_ROTATION = 180.0
PMOD_EDGE_COPPER_CLEARANCE = 0.6
PMOD_OUTBOARD_PAD_CENTER_X = PMOD_ORIGIN[0] + PMOD_ROW_SPACING / 2.0
BOARD_REAR_X = PMOD_OUTBOARD_PAD_CENTER_X + PMOD_PAD_DIAMETER / 2.0 + PMOD_EDGE_COPPER_CLEARANCE
BOARD_WIDTH = BOARD_REAR_X
BOARD_REAR_CORNER_RADIUS = 2.0
BOARD_REAR_CORNER_X = BOARD_REAR_X - BOARD_REAR_CORNER_RADIUS
BOARD_REAR_BOTTOM_CORNER_Y = BOARD_BOTTOM_Y + BOARD_REAR_CORNER_RADIUS
BOARD_REAR_TOP_CORNER_Y = BOARD_TOP_Y - BOARD_REAR_CORNER_RADIUS

BOARD_OUTLINE = micro_sd_card_outline(
    [
        (16.5, -1.5),
        (TAIL_CHAMFER_X, BOARD_BOTTOM_Y),
        Arc(
            (BOARD_REAR_CORNER_X, BOARD_REAR_BOTTOM_CORNER_Y),
            BOARD_REAR_CORNER_RADIUS,
            270.0,
            90.0,
        ),
        Arc(
            (BOARD_REAR_CORNER_X, BOARD_REAR_TOP_CORNER_Y),
            BOARD_REAR_CORNER_RADIUS,
            0.0,
            90.0,
        ),
        (TAIL_CHAMFER_X, BOARD_TOP_Y),
        (16.5, 12.5),
    ]
)
BOARD_SHAPE = ArcPolygon(BOARD_OUTLINE)

POUR_EDGE_CLEARANCE = 0.5
POUR_REAR_X = BOARD_REAR_X - POUR_EDGE_CLEARANCE
POUR_BOTTOM_Y = BOARD_BOTTOM_Y + POUR_EDGE_CLEARANCE
POUR_TOP_Y = BOARD_TOP_Y - POUR_EDGE_CLEARANCE
POUR_REAR_RADIUS = BOARD_REAR_CORNER_RADIUS - POUR_EDGE_CLEARANCE
POUR_REAR_CORNER_X = POUR_REAR_X - POUR_REAR_RADIUS
SIGNAL_AREA = ArcPolygon(
    [
        (0.5, 0.5),
        (14.7, 0.5),
        (16.7, -1.5),
        (18.2, POUR_BOTTOM_Y),
        Arc(
            (POUR_REAR_CORNER_X, POUR_BOTTOM_Y + POUR_REAR_RADIUS),
            POUR_REAR_RADIUS,
            270.0,
            90.0,
        ),
        Arc(
            (POUR_REAR_CORNER_X, POUR_TOP_Y - POUR_REAR_RADIUS),
            POUR_REAR_RADIUS,
            0.0,
            90.0,
        ),
        (18.2, POUR_TOP_Y),
        (16.7, 12.5),
        (14.7, 10.5),
        (9.8, 10.5),
        (9.0, 9.5),
        (0.5, 9.5),
    ]
)

# Exhaustive zero-crossing rank-1 mappings over all 20,160 six-of-eight PMOD
# assignments. Both variants rank direct bottom-copper paths because the PMOD
# connector's plated through-hole pads are available from either board face.
BOTTOM_HEADER_SD_TO_PMOD_PIN = {
    "DAT2": 7,
    "DAT3": 8,
    "CMD": 9,
    "CLK": 3,
    "DAT0": 10,
    "DAT1": 4,
}
TOP_HEADER_SD_TO_PMOD_PIN = {
    "DAT2": 4,
    "DAT3": 10,
    "CMD": 3,
    "CLK": 9,
    "DAT0": 8,
    "DAT1": 7,
}

PMOD_ROW_LABEL_SIZE = 0.43
PMOD_ROW_LABEL_X = 24.20
PMOD_BOTTOM_ROW_LABEL_X = 23.65
PMOD_ROW_LABEL_Y_OFFSET = 0.36


def transformed_point(
    point: tuple[float, float],
    origin: tuple[float, float],
    side: Side,
    rotation: float,
) -> tuple[float, float]:
    x, y = point
    local_x = -x if side == Side.Bottom else x
    angle = radians(rotation)
    return (
        origin[0] + local_x * cos(angle) - y * sin(angle),
        origin[1] + local_x * sin(angle) + y * cos(angle),
    )


def micro_sd_pad_center(name: str) -> tuple[float, float]:
    return MICRO_SD_EDGE_PAD_CENTERS[name]


def pmod_pad_center(pin: int, side: Side, rotation: float) -> tuple[float, float]:
    return transformed_point(PMOD_PAD_CENTERS[pin], PMOD_ORIGIN, side, rotation)


def pmod_pin_label(pin: int, sd_to_pmod_pin: dict[str, int]) -> str:
    label = f"{pin} {PMOD_PIN_NAMES[pin]}"
    signal_by_pin = {pmod_pin: signal for signal, pmod_pin in sd_to_pmod_pin.items()}
    if signal := signal_by_pin.get(pin):
        label += f"/SD_{signal}"
    return label


def pmod_row_labels(
    side: Side,
    rotation: float,
    sd_to_pmod_pin: dict[str, int],
) -> tuple[tuple[float, tuple[str, str]], ...]:
    rows: dict[float, list[int]] = {}
    for pin in range(1, 13):
        _x, y = pmod_pad_center(pin, side, rotation)
        rows.setdefault(round(y, 6), []).append(pin)
    return tuple(
        (
            y,
            tuple(pmod_pin_label(pin, sd_to_pmod_pin) for pin in sorted(pins)),
        )
        for y, pins in sorted(rows.items(), reverse=True)
    )  # ty: ignore[invalid-return-type]


class MicroSdPmodEmulatorSubstrate(Substrate):
    stackup = JlcpcbTwoLayer08Stackup()
    constraints = JlcpcbTwoLayerFabConstraints()

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = 0.6
        hole_diameter = 0.3
        type = ViaType.MechanicalDrill


class MicroSdPmodEmulatorCircuit(Circuit):
    gnd = Port()

    def __init__(
        self,
        *,
        pmod_side: Side,
        pmod_rotation: float,
        sd_to_pmod_pin: dict[str, int],
        header_side_name: str,
    ):
        super().__init__()
        if set(sd_to_pmod_pin) != set(MICRO_SD_DATA_PORTS):
            raise ValueError("mapping must cover every fungible microSD data signal exactly once")
        if len(set(sd_to_pmod_pin.values())) != len(sd_to_pmod_pin):
            raise ValueError("mapping must assign unique PMOD positions")
        if not set(sd_to_pmod_pin.values()) <= set(PMOD_DATA_PINS):
            raise ValueError("mapping may target only PMOD data positions")

        self.pmod_side = pmod_side
        self.pmod_rotation = pmod_rotation
        self.sd_to_pmod_pin = dict(sd_to_pmod_pin)
        self.card = MicroSdCardEdge()
        self.pmod = PmodHeader2x6()
        self.ground_pours = [
            Pour(SIGNAL_AREA, layer=0, isolate=0.2, orphans=False),
            Pour(SIGNAL_AREA, layer=1, isolate=0.2, orphans=False),
        ]

        ground_net = connect_ports("GND", self.gnd, self.card.VSS)
        for pour in self.ground_pours:
            ground_net = ground_net + pour
        signal_nets = [
            connect_ports(
                f"SD_{name}",
                getattr(self.card, name),
                self.pmod.pin(pin),
            )
            for name, pin in self.sd_to_pmod_pin.items()
        ]
        self.nets = [ground_net, *signal_nets]

        self.place(
            self.card,
            Placement(MICRO_SD_EDGE_ORIGIN, MICRO_SD_EDGE_ROTATION, on=Side.Bottom),
        )
        self.place(
            self.pmod,
            Placement(PMOD_ORIGIN, self.pmod_rotation, on=self.pmod_side),
        )

        self += Silkscreen(Text("microSD EMULATOR", 0.66).at(13.2, 9.0), side=FeatureSide.Top)
        self += Silkscreen(
            Text(f"PMOD HEADER {header_side_name}", 0.56).at(13.2, 7.7),
            side=FeatureSide.Top,
        )
        self += Silkscreen(Text("PWR NC / 0.8mm ENIG", 0.50).at(13.2, 6.4), side=FeatureSide.Top)
        self += Silkscreen(Text("INSERT", 0.60).at(7.0, 4.2), side=FeatureSide.Top)
        self += Silkscreen(Text("<", 0.9).at(3.9, 4.2), side=FeatureSide.Top)
        self += Silkscreen(
            bottom_text(f"microSD-PMOD {BOARD_DATE}", 0.52, 12.0, 1.0),
            side=FeatureSide.Bottom,
        )

        for y, labels in pmod_row_labels(
            self.pmod_side,
            self.pmod_rotation,
            self.sd_to_pmod_pin,
        ):
            for label, y_offset in zip(
                labels,
                (PMOD_ROW_LABEL_Y_OFFSET, -PMOD_ROW_LABEL_Y_OFFSET),
                strict=True,
            ):
                label_y = y + y_offset
                self += Silkscreen(
                    Text(label, PMOD_ROW_LABEL_SIZE, Anchor.E).at(PMOD_ROW_LABEL_X, label_y),
                    side=FeatureSide.Top,
                )
                self += Silkscreen(
                    bottom_text(
                        label,
                        PMOD_ROW_LABEL_SIZE,
                        PMOD_BOTTOM_ROW_LABEL_X,
                        label_y,
                        anchor=Anchor.W,
                    ),
                    side=FeatureSide.Bottom,
                )


class MicroSdPmodEmulatorBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class MicroSdPmodEmulatorDesign(Design):
    substrate = MicroSdPmodEmulatorSubstrate()
    board = MicroSdPmodEmulatorBoard()
    circuit = MicroSdPmodEmulatorCircuit(
        pmod_side=Side.Bottom,
        pmod_rotation=BOTTOM_HEADER_ROTATION,
        sd_to_pmod_pin=BOTTOM_HEADER_SD_TO_PMOD_PIN,
        header_side_name="BOTTOM",
    )


class MicroSdPmodEmulatorTopHeaderDesign(Design):
    substrate = MicroSdPmodEmulatorSubstrate()
    board = MicroSdPmodEmulatorBoard()
    circuit = MicroSdPmodEmulatorCircuit(
        pmod_side=Side.Top,
        pmod_rotation=TOP_HEADER_ROTATION,
        sd_to_pmod_pin=TOP_HEADER_SD_TO_PMOD_PIN,
        header_side_name="TOP R180",
    )
