from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

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
    GROUND_STITCH_VIA_CENTERS,
    GROUND_STITCH_VIA_HOLE_DIAMETER,
    PICO_HOLE_DIAMETER,
    PICO_PAD_DIAMETER,
    PICO_VBUS_PHYSICAL_PIN,
    SIGNAL_SHRINK,
    SIGNAL_TRACE_WIDTH,
    ULN_COMPONENT_CUTOUT_BOUNDS,
    ULN_COMPONENT_CUTOUT_RADIUS,
    ULN_H_POSITIONS,
    ULN_HOLE_DIAMETER,
    ULN_PAD_DIAMETER,
    ULN_V_POSITIONS,
    VBUS_TOP_PATHS,
    VBUS_TRACE_WIDTH,
    pico_pin_position,
)

type Point2 = tuple[float, float]

ROUND_QUADRANTS = 24
GEOMETRY_TOLERANCE = 1.0e-6


@dataclass(frozen=True)
class ForgeParameters:
    board_thickness: float = 1.60
    trace_depth: float = 0.30
    press_plate_thickness: float = 4.00
    ridge_height: float = 0.25
    press_clearance: float = 0.15
    spike_height: float = 1.00
    spike_clearance: float = 0.25
    stl_tolerance: float = 0.03

    def validate(self) -> None:
        positive = {
            "board_thickness": self.board_thickness,
            "trace_depth": self.trace_depth,
            "press_plate_thickness": self.press_plate_thickness,
            "ridge_height": self.ridge_height,
            "press_clearance": self.press_clearance,
            "spike_height": self.spike_height,
            "spike_clearance": self.spike_clearance,
            "stl_tolerance": self.stl_tolerance,
        }
        for name, value in positive.items():
            if value <= 0.0:
                raise ValueError(f"{name} must be positive")
        if self.trace_depth >= self.board_thickness:
            raise ValueError("trace_depth must be less than board_thickness")
        if self.ridge_height > self.trace_depth:
            raise ValueError("ridge_height must not exceed trace_depth")
        if self.press_clearance >= min(SIGNAL_TRACE_WIDTH, PICO_PAD_DIAMETER):
            raise ValueError("press_clearance is too large for the narrowest top-copper feature")
        if self.spike_clearance >= min(
            PICO_HOLE_DIAMETER,
            ULN_HOLE_DIAMETER,
            GROUND_STITCH_VIA_HOLE_DIAMETER,
        ):
            raise ValueError("spike_clearance must be smaller than every connector hole")


@dataclass(frozen=True)
class Hole:
    center: Point2
    diameter: float
    net: str


@dataclass(frozen=True)
class ForgeLayout:
    outer_profile: Polygon
    base_profile: Polygon
    top_nets: dict[str, BaseGeometry]
    top_copper: BaseGeometry
    front_ground: BaseGeometry
    front_ground_foil: BaseGeometry
    bottom_ground: BaseGeometry
    ground_foil: BaseGeometry
    holes: tuple[Hole, ...]


def rounded_rectangle(bounds: tuple[float, float, float, float], radius: float) -> Polygon:
    left, bottom, right, top = bounds
    return box(left + radius, bottom + radius, right - radius, top - radius).buffer(
        radius,
        quad_segs=ROUND_QUADRANTS,
    )


def rotate_translate(point: Point2, origin: Point2, angle_degrees: float) -> Point2:
    angle = math.radians(angle_degrees)
    x, y = point
    return (
        origin[0] + x * math.cos(angle) - y * math.sin(angle),
        origin[1] + x * math.sin(angle) + y * math.cos(angle),
    )


def driver_point(driver_index: int, local_point: Point2) -> Point2:
    return rotate_translate(
        local_point,
        DRIVER_H1_POSITIONS[driver_index],
        DRIVER_ROTATIONS[driver_index],
    )


def trace(points: list[Point2] | tuple[Point2, ...], width: float) -> BaseGeometry:
    return LineString(points).buffer(width / 2.0, quad_segs=ROUND_QUADRANTS)


def add_net_shape(net_shapes: dict[str, list[BaseGeometry]], net: str, shape: BaseGeometry) -> None:
    net_shapes.setdefault(net, []).append(shape)


def signal_net_name(driver_index: int, input_index: int) -> str:
    gpio = DRIVER_GPIO_PINS[driver_index][input_index]
    return f"DRV{driver_index + 1}_IN{input_index + 1}_GP{gpio}"


def build_layout() -> ForgeLayout:
    outer_profile = rounded_rectangle(
        (-BOARD_WIDTH / 2.0, -BOARD_HEIGHT / 2.0, BOARD_WIDTH / 2.0, BOARD_HEIGHT / 2.0),
        BOARD_RADIUS,
    )
    signal_profile = rounded_rectangle(
        (
            -BOARD_WIDTH / 2.0 + SIGNAL_SHRINK,
            -BOARD_HEIGHT / 2.0 + SIGNAL_SHRINK,
            BOARD_WIDTH / 2.0 - SIGNAL_SHRINK,
            BOARD_HEIGHT / 2.0 - SIGNAL_SHRINK,
        ),
        BOARD_RADIUS - SIGNAL_SHRINK,
    )

    local_cutout = rounded_rectangle(ULN_COMPONENT_CUTOUT_BOUNDS, ULN_COMPONENT_CUTOUT_RADIUS)
    cutouts = []
    for origin, angle in zip(DRIVER_H1_POSITIONS, DRIVER_ROTATIONS, strict=True):
        rotated = affinity.rotate(local_cutout, angle, origin=(0.0, 0.0))
        cutouts.append(affinity.translate(rotated, xoff=origin[0], yoff=origin[1]))
    base_profile = outer_profile.difference(unary_union(cutouts))
    if not isinstance(base_profile, Polygon) or not base_profile.is_valid:
        raise RuntimeError("The printable PCB profile must be one valid connected polygon")

    signal_nets_by_pin: dict[int, str] = {}
    for driver_index, physical_pins in enumerate(DRIVER_SIGNAL_PHYSICAL_PINS):
        for input_index, physical_pin in enumerate(physical_pins):
            signal_nets_by_pin[physical_pin] = signal_net_name(driver_index, input_index)

    holes: list[Hole] = []
    net_shapes: dict[str, list[BaseGeometry]] = {}
    for physical_pin in range(1, 41):
        if physical_pin in signal_nets_by_pin:
            net = signal_nets_by_pin[physical_pin]
        elif physical_pin == PICO_VBUS_PHYSICAL_PIN:
            net = "VBUS_5V"
        elif physical_pin in DRIVER_GROUND_PHYSICAL_PINS:
            net = "GND"
        else:
            net = f"PICO_PIN_{physical_pin}"
        center = pico_pin_position(physical_pin)
        holes.append(Hole(center, PICO_HOLE_DIAMETER, net))
        add_net_shape(net_shapes, net, Point(center).buffer(PICO_PAD_DIAMETER / 2.0, quad_segs=ROUND_QUADRANTS))

    for driver_index in range(3):
        driver_nets = (
            f"DRV{driver_index + 1}_H1_H2_BRIDGE",
            f"DRV{driver_index + 1}_H1_H2_BRIDGE",
            "VBUS_5V",
            "GND",
            *(signal_net_name(driver_index, input_index) for input_index in range(4)),
        )
        local_positions = (*ULN_H_POSITIONS, *ULN_V_POSITIONS)
        for local_position, net in zip(local_positions, driver_nets, strict=True):
            center = driver_point(driver_index, local_position)
            holes.append(Hole(center, ULN_HOLE_DIAMETER, net))
            add_net_shape(net_shapes, net, Point(center).buffer(ULN_PAD_DIAMETER / 2.0, quad_segs=ROUND_QUADRANTS))

        for input_index, (physical_pin, local_position) in enumerate(
            zip(DRIVER_SIGNAL_PHYSICAL_PINS[driver_index], ULN_V_POSITIONS, strict=True)
        ):
            net = signal_net_name(driver_index, input_index)
            add_net_shape(
                net_shapes,
                net,
                trace(
                    [pico_pin_position(physical_pin), driver_point(driver_index, local_position)], SIGNAL_TRACE_WIDTH
                ),
            )
        add_net_shape(
            net_shapes,
            f"DRV{driver_index + 1}_H1_H2_BRIDGE",
            trace(DRIVER_H1_H2_TOP_PATHS[driver_index], SIGNAL_TRACE_WIDTH),
        )

    for path in VBUS_TOP_PATHS:
        add_net_shape(net_shapes, "VBUS_5V", trace(path, VBUS_TRACE_WIDTH))

    holes.extend(Hole(center, GROUND_STITCH_VIA_HOLE_DIAMETER, "GND") for center in GROUND_STITCH_VIA_CENTERS)

    top_nets = {net: unary_union(shapes).intersection(base_profile) for net, shapes in net_shapes.items()}
    for (left_name, left_shape), (right_name, right_shape) in combinations(top_nets.items(), 2):
        overlap_area = left_shape.intersection(right_shape).area
        if overlap_area > GEOMETRY_TOLERANCE:
            raise RuntimeError(f"Top copper nets {left_name} and {right_name} overlap by {overlap_area:.6f} square mm")
    top_copper = unary_union(list(top_nets.values())).intersection(base_profile)

    front_antipads = unary_union(
        [shape.buffer(COPPER_CLEARANCE, quad_segs=ROUND_QUADRANTS) for net, shape in top_nets.items() if net != "GND"]
    )
    front_ground = signal_profile.intersection(base_profile).difference(front_antipads)

    antipads = []
    all_holes = []
    for hole in holes:
        all_holes.append(Point(hole.center).buffer(hole.diameter / 2.0, quad_segs=ROUND_QUADRANTS))
        if hole.net != "GND":
            pad_diameter = PICO_PAD_DIAMETER if math.isclose(hole.diameter, PICO_HOLE_DIAMETER) else ULN_PAD_DIAMETER
            antipads.append(
                Point(hole.center).buffer(
                    pad_diameter / 2.0 + COPPER_CLEARANCE,
                    quad_segs=ROUND_QUADRANTS,
                )
            )
    bottom_ground = signal_profile.intersection(base_profile).difference(unary_union(antipads))
    front_ground_foil = front_ground.difference(unary_union(all_holes))
    ground_foil = bottom_ground.difference(unary_union(all_holes))
    if front_ground.is_empty or front_ground_foil.is_empty:
        raise RuntimeError("Front ground-plane geometry is empty")
    if bottom_ground.is_empty or ground_foil.is_empty:
        raise RuntimeError("Bottom ground-plane geometry is empty")

    return ForgeLayout(
        outer_profile=outer_profile,
        base_profile=base_profile,
        top_nets=top_nets,
        top_copper=top_copper,
        front_ground=front_ground,
        front_ground_foil=front_ground_foil,
        bottom_ground=bottom_ground,
        ground_foil=ground_foil,
        holes=tuple(holes),
    )


def hole_geometry(holes: tuple[Hole, ...]) -> BaseGeometry:
    return unary_union([Point(hole.center).buffer(hole.diameter / 2.0, quad_segs=ROUND_QUADRANTS) for hole in holes])


def mirror_holes_for_press(holes: tuple[Hole, ...]) -> tuple[Hole, ...]:
    return tuple(Hole((-hole.center[0], hole.center[1]), hole.diameter, hole.net) for hole in holes)


def clearance_estimates(parameters: ForgeParameters) -> dict[str, float]:
    """Parameter-derived clearances, not verification of exported solids."""
    return {
        "vertical_bottoming_clearance_mm": round(parameters.trace_depth - parameters.ridge_height, 4),
        "minimum_spike_radial_clearance_mm": round(parameters.spike_clearance / 2.0, 4),
    }
