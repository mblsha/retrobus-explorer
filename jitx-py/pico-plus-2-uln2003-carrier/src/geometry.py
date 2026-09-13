from __future__ import annotations

PITCH = 2.54

SIGNAL_TRACE_WIDTH = 2.00
VBUS_TRACE_WIDTH = 2.00
COPPER_CLEARANCE = 0.25
GROUND_POUR_LAYERS = (0, 1)
GROUND_STITCH_VIA_DIAMETER = 1.60
GROUND_STITCH_VIA_HOLE_DIAMETER = 0.80
PICO_PAD_DIAMETER = 1.5658
PICO_HOLE_DIAMETER = 1.015
PICO_ROW_OFFSET = 8.89
PICO_ROW_HALF_LENGTH = 24.13
PICO_PIN_LABEL_SIZE = 1.00
PICO_PIN_LABEL_INSET = 3.50

# Connector coordinates are relative to H1 and come directly from the supplied
# calibrated photograph/OpenSCAD fit template.  The photograph is a top view,
# so X is mirrored from the earlier underside-derived geometry: the input row
# is along the module's bottom edge and the H1-H4 row is along its right edge.
ULN_HOLE_DIAMETER = 1.30
ULN_PAD_DIAMETER = 2.00
ULN_CONNECTOR_ARM_WIDTH = 3.00
ULN_H_POSITIONS = tuple((-index * PITCH, 0.0) for index in range(4))
ULN_V1 = (-10.7045, 19.4094)
ULN_V_POSITIONS = tuple((ULN_V1[0], ULN_V1[1] - index * PITCH) for index in range(4))

# The same photograph, calibrated from the 2.54 mm connector pitch, gives an
# approximately 35.4 x 31.0 mm module.  The carrier does not reproduce the
# module's four corner mounting holes; the central clearance opening extends
# toward those corners instead.
ULN_BOARD_BOUNDS = (-17.4, -5.4, 18.0, 25.6)
# Preserve the OpenSCAD template's exact 3 mm-wide L around the connector
# centrelines.  The far side leaves a 1.5 mm rim; the far/top edge is expanded
# by 1 mm for measured component clearance and leaves a 0.5 mm rim.
ULN_OUTER_RIM_WIDTH = 1.50
ULN_CUTOUT_TOP_EXPANSION = 1.00
ULN_COMPONENT_CUTOUT_BOUNDS = (
    ULN_V1[0] + ULN_CONNECTOR_ARM_WIDTH / 2.0,
    ULN_CONNECTOR_ARM_WIDTH / 2.0,
    ULN_BOARD_BOUNDS[2] - ULN_OUTER_RIM_WIDTH,
    ULN_BOARD_BOUNDS[3] - ULN_OUTER_RIM_WIDTH + ULN_CUTOUT_TOP_EXPANSION,
)
ULN_COMPONENT_CUTOUT_RADIUS = 2.0

BOARD_WIDTH = 76.0
BOARD_HEIGHT = 100.0
BOARD_RADIUS = 3.0
SIGNAL_SHRINK = 0.5

PICO_CENTER = (0.0, 0.0)
PICO_ROTATION = 90.0

# The Pico is horizontal. Drivers 1 and 2 form a centered, aligned row below
# it, while driver 3 is centered above it.  Placement is centered using the
# mirrored top-view module bounds.
DRIVER_H1_POSITIONS = (
    (6.9, -28.7045),
    (-26.2, -28.7045),
    (10.1, 28.7045),
)
DRIVER_ROTATIONS = (270.0, 270.0, 90.0)

DRIVER_GPIO_PINS = (
    (0, 1, 2, 3),
    (10, 11, 12, 13),
    (20, 21, 22, 26),
)
DRIVER_SIGNAL_PHYSICAL_PINS = (
    (1, 2, 4, 5),
    (14, 15, 16, 17),
    (26, 27, 29, 31),
)
DRIVER_GROUND_PHYSICAL_PINS = (13, 18, 23)
PICO_VBUS_PHYSICAL_PIN = 40

PICO_USED_PIN_LABELS = tuple(
    sorted(
        [
            (physical_pin, f"GP{gpio}")
            for gpios, physical_pins in zip(
                DRIVER_GPIO_PINS,
                DRIVER_SIGNAL_PHYSICAL_PINS,
                strict=True,
            )
            for gpio, physical_pin in zip(gpios, physical_pins, strict=True)
        ]
        + [(physical_pin, "GND") for physical_pin in DRIVER_GROUND_PHYSICAL_PINS]
        + [(PICO_VBUS_PHYSICAL_PIN, "5V")]
    )
)


def pico_pin_position(physical_pin: int) -> tuple[float, float]:
    if not 1 <= physical_pin <= 40:
        raise ValueError(f"Pico physical pin must be 1..40, got {physical_pin}")
    if physical_pin <= 20:
        row_position = -PICO_ROW_HALF_LENGTH + (physical_pin - 1) * PITCH
        return (-row_position, -PICO_ROW_OFFSET)
    row_position = PICO_ROW_HALF_LENGTH - (physical_pin - 21) * PITCH
    return (-row_position, PICO_ROW_OFFSET)


def pico_pin_label_position(physical_pin: int) -> tuple[float, float]:
    x, y = pico_pin_position(physical_pin)
    inset = PICO_PIN_LABEL_INSET if y < 0.0 else -PICO_PIN_LABEL_INSET
    return (x, y + inset)


PICO_VBUS_CENTER = pico_pin_position(PICO_VBUS_PHYSICAL_PIN)
DRIVER_VBUS_CENTERS = (
    (6.9, -23.6245),
    (-26.2, -23.6245),
    (10.1, 23.6245),
)
VBUS_TOP_PATHS = (
    [PICO_VBUS_CENTER, (35.0, 8.89)],
    [(35.0, 8.89), (35.0, 47.0), (15.0, 47.0), (15.0, 23.6245), DRIVER_VBUS_CENTERS[2]],
    [(35.0, 8.89), (35.0, -47.0), (-35.0, -47.0), (-35.0, -23.6245), DRIVER_VBUS_CENTERS[1]],
    [(0.5, -47.0), (0.5, -23.6245), DRIVER_VBUS_CENTERS[0]],
)
DRIVER_H1_H2_TOP_PATHS = (
    [(6.9, -26.1645), (6.9, -28.7045)],
    [(-26.2, -26.1645), (-26.2, -28.7045)],
    [(10.1, 26.1645), (10.1, 28.7045)],
)

# Join the front and back GND fills in open carrier material. The two side
# columns avoid the ULN component openings and the 5 V perimeter route; the
# centre row stitches the broad copper area between the Pico header rows. The
# larger-than-fab-minimum drill is intentional so the same holes can accept
# wire or eyelets when the board is made with the printable press tooling.
GROUND_STITCH_VIA_CENTERS = (
    *((-33.0, y) for y in (43.0, 35.0, 27.0, 19.0, 11.0, 3.0, -5.0, -10.0)),
    *((31.0, y) for y in (43.0, 35.0, 27.0, 19.0, 12.0, 3.0, -5.0, -10.0)),
    *((x, 0.0) for x in (-18.0, -9.0, 0.0, 9.0, 18.0)),
    (-25.0, 44.0),
    (-19.0, 44.0),
)


