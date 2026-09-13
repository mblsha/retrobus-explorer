from __future__ import annotations

from jitx.board import Board
from jitx.circuit import Circuit
from jitx.copper import Copper, Pour
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.placement import Placement, Side
from jitx.shapes.composites import rectangle
from jitx.shapes.primitive import Polyline, Text
from jitx.substrate import Substrate
from jitx.via import Via, ViaType
from shared_components.connectivity import connect_ports
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup
from shared_components.rpi_pico import Pico40PinHeaders

from src.components import Uln2003DriverInterface
from src.geometry import (
    BOARD_HEIGHT,
    BOARD_RADIUS,
    BOARD_WIDTH,
    COPPER_CLEARANCE,
    DRIVER_GPIO_PINS,
    DRIVER_GROUND_PHYSICAL_PINS,
    DRIVER_H1_H2_TOP_PATHS,
    DRIVER_H1_POSITIONS,
    DRIVER_ROTATIONS,
    DRIVER_SIGNAL_PHYSICAL_PINS,
    GROUND_POUR_LAYERS,
    GROUND_STITCH_VIA_CENTERS,
    GROUND_STITCH_VIA_DIAMETER,
    GROUND_STITCH_VIA_HOLE_DIAMETER,
    PICO_CENTER,
    PICO_PIN_LABEL_SIZE,
    PICO_ROTATION,
    PICO_USED_PIN_LABELS,
    PICO_VBUS_PHYSICAL_PIN,
    SIGNAL_SHRINK,
    SIGNAL_TRACE_WIDTH,
    VBUS_TOP_PATHS,
    VBUS_TRACE_WIDTH,
    pico_pin_label_position,
)

BOARD_REVISION = "rev1"

def make_board_geometry(*, shrink: float = 0.0):
    return rectangle(
        BOARD_WIDTH - 2.0 * shrink,
        BOARD_HEIGHT - 2.0 * shrink,
        radius=max(BOARD_RADIUS - shrink, 0.0),
    )


BOARD_SHAPE = make_board_geometry()
SIGNAL_AREA = make_board_geometry(shrink=SIGNAL_SHRINK)



def top_trace(width: float, points: list[tuple[float, float]]) -> Copper:
    return Copper(Polyline(width, points), layer=0)


def top_pin_label(text: str, position: tuple[float, float], *, rotate: float = 90.0) -> Silkscreen:
    return Silkscreen(
        Text(text, PICO_PIN_LABEL_SIZE).at(*position, rotate=rotate),
        side=FeatureSide.Top,
    )


class PicoPlus2Uln2003CarrierSubstrate(Substrate):
    stackup = jlcpcb_stackup(2)
    constraints = jlcpcb_fab_constraints(2)

    class GroundStitchVia(Via):
        start_layer = 0
        stop_layer = 1
        diameter = GROUND_STITCH_VIA_DIAMETER
        hole_diameter = GROUND_STITCH_VIA_HOLE_DIAMETER
        type = ViaType.MechanicalDrill


class PicoPlus2Uln2003CarrierCircuit(Circuit):
    def __init__(self):
        super().__init__()
        self.pico = Pico40PinHeaders()
        self.drivers = [Uln2003DriverInterface() for _ in range(3)]
        self.ground_stitch_vias = [
            PicoPlus2Uln2003CarrierSubstrate.GroundStitchVia().at(position) for position in GROUND_STITCH_VIA_CENTERS
        ]

        self.nets = []
        for driver_index, driver in enumerate(self.drivers):
            for input_index, (gpio, physical_pin) in enumerate(
                zip(
                    DRIVER_GPIO_PINS[driver_index],
                    DRIVER_SIGNAL_PHYSICAL_PINS[driver_index],
                    strict=True,
                )
            ):
                self.nets.append(
                    connect_ports(
                        f"DRV{driver_index + 1}_IN{input_index + 1}_GP{gpio}",
                        self.pico.pin(physical_pin),
                        driver.IN[input_index],
                    )
                )
            self.nets.append(
                connect_ports(
                    f"DRV{driver_index + 1}_H1_H2_BRIDGE",
                    driver.H1,
                    driver.H2,
                )
                + top_trace(
                    SIGNAL_TRACE_WIDTH,
                    DRIVER_H1_H2_TOP_PATHS[driver_index],
                )
            )

        vbus_net = connect_ports(
            "VBUS_5V",
            self.pico.pin(PICO_VBUS_PHYSICAL_PIN),
            *(driver.V5 for driver in self.drivers),
        )
        for path in VBUS_TOP_PATHS:
            vbus_net = vbus_net + top_trace(VBUS_TRACE_WIDTH, path)
        self.nets.append(vbus_net)

        ground_net = connect_ports(
            "GND",
            *(self.pico.pin(pin) for pin in DRIVER_GROUND_PHYSICAL_PINS),
            *(driver.GND for driver in self.drivers),
        )
        for via in self.ground_stitch_vias:
            ground_net = ground_net + via
        for layer in GROUND_POUR_LAYERS:
            ground_net = ground_net + Pour(
                SIGNAL_AREA,
                layer=layer,
                isolate=COPPER_CLEARANCE,
                orphans=False,
            )
        self.nets.append(ground_net)

        self.place(self.pico, Placement(PICO_CENTER, PICO_ROTATION, on=Side.Top))
        for driver, h1_position, rotation in zip(
            self.drivers,
            DRIVER_H1_POSITIONS,
            DRIVER_ROTATIONS,
            strict=True,
        ):
            self.place(driver, Placement(h1_position, rotation, on=Side.Top))

        for physical_pin, label in PICO_USED_PIN_LABELS:
            self += top_pin_label(label, pico_pin_label_position(physical_pin))

        self += Silkscreen(Text("PICO PLUS 2", 1.1).at(27.0, 45.0), side=FeatureSide.Top)
        self += Silkscreen(Text("ULN2003 #3", 1.0).at(27.0, 34.0), side=FeatureSide.Top)
        self += Silkscreen(Text("ULN2003 #1", 1.0).at(35.0, -29.0, rotate=90), side=FeatureSide.Top)
        self += Silkscreen(Text("ULN2003 #2", 1.0).at(-35.0, -29.0, rotate=90), side=FeatureSide.Top)
        self += Silkscreen(Text("5V FROM VBUS PIN 40", 1.0).at(29.0, -2.0, rotate=90), side=FeatureSide.Top)


class PicoPlus2Uln2003CarrierBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA
    label = Silkscreen(
        Text(f"Pico Plus 2 / 3x ULN2003  Rev A  {BOARD_REVISION}", 1.0).at(0.0, -49.0),
        side=FeatureSide.Top,
    )


class PicoPlus2Uln2003CarrierDesign(Design):
    substrate = PicoPlus2Uln2003CarrierSubstrate()
    board = PicoPlus2Uln2003CarrierBoard()
    circuit = PicoPlus2Uln2003CarrierCircuit()
