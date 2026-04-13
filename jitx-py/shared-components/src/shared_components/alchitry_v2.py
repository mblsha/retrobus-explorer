from __future__ import annotations

# Profile-aware Alchitry V2 bank wrappers derived from Alchitry's published
# pinout reference:
# https://alchitry.com/tutorials/references/pinouts-and-custom-elements/
#
# The page above is the primary provenance source for the Ft and Ft+ pin claims
# below. It specifies the exact signal usage on Bank A / Bank B / Control for
# those boards. These wrappers use that source of truth to keep reserved onboard
# Ft / Ft+ signals unavailable to external daughterboards by simply not exposing
# ports for those pins.
from dataclasses import dataclass
from functools import cache
from typing import Literal, cast

from jitx.component import Component
from jitx.feature import Courtyard
from jitx.landpattern import Landpattern, PadMapping
from jitx.net import Port
from jitx.shapes.composites import rectangle
from jitxlib.symbols.box import BoxConfig, BoxSymbol, PinGroup, Row

from shared_components.hirose_df40 import (
    DF40_80_BOTTOM_SPECS,
    DF40_80_TOP_SPECS,
    Df40PadSpec,
    place_df40_pad_specs,
)

PINOUTS_URL = "https://alchitry.com/tutorials/references/pinouts-and-custom-elements/"

BoardKey = Literal["ft", "ft_plus"]
ConnectorKey = Literal["A", "B", "C"]
PinRole = Literal["reserved_signal", "ground", "power"]

_BANK_GROUND_PINS = (
    1,
    2,
    7,
    8,
    13,
    14,
    19,
    20,
    25,
    26,
    31,
    32,
    37,
    38,
    43,
    44,
    49,
    50,
    55,
    56,
    61,
    62,
    67,
    68,
    73,
    74,
    79,
    80,
)
_CONTROL_GROUND_PINS = tuple(range(17, 29))
_CONTROL_3V3_PINS = tuple(range(1, 17, 2))
_CONTROL_VDD_PINS = tuple(range(2, 17, 2))

_FT_BANK_A_RESERVED = {
    3: "!Wakeup",
    4: "OE",
    5: "!Reset",
    6: "RD",
    9: "WR",
    10: "RXF",
    11: "BE1",
    12: "TXE",
    15: "BE0",
    16: "D15",
    17: "D13",
    18: "D14",
    21: "D10",
    22: "D12",
    23: "D9",
    24: "D11",
    27: "D6",
    28: "D8",
    29: "D5",
    30: "D7",
    33: "D2",
    34: "D4",
    35: "D1",
    36: "D3",
    39: "D0",
    41: "CLK",
}
_FT_PLUS_BANK_A_RESERVED = {
    3: "!Wakeup",
    4: "OE",
    5: "!Reset",
    6: "RD",
    9: "WR",
    10: "RXF",
    11: "BE3",
    12: "TXE",
    15: "BE0",
    16: "BE2",
    17: "D31",
    18: "BE1",
    21: "D28",
    22: "D30",
    23: "D27",
    24: "D29",
    27: "D24",
    28: "D26",
    29: "D23",
    30: "D25",
    33: "D20",
    34: "D22",
    35: "D19",
    36: "D21",
    39: "D16",
    40: "D18",
    41: "CLK",
    42: "D17",
}
_FT_PLUS_BANK_B_RESERVED = {
    3: "D0",
    4: "D2",
    5: "D1",
    6: "D3",
    9: "D4",
    10: "D6",
    11: "D5",
    12: "D7",
    15: "D8",
    16: "D10",
    17: "D9",
    18: "D11",
    21: "D12",
    22: "D14",
    23: "D13",
    24: "D15",
}


@dataclass(frozen=True)
class PinClaim:
    board: BoardKey
    connector: ConnectorKey
    pin: int
    signal: str
    role: PinRole
    source_url: str
    source_section: str


@dataclass(frozen=True)
class ConnectorUsageProfile:
    board: BoardKey
    connector: ConnectorKey
    pin_count: int
    claims: tuple[PinClaim, ...]

    def claims_by_pin(self) -> dict[int, PinClaim]:
        return {claim.pin: claim for claim in self.claims}

    def reserved_signal_pins(self) -> tuple[int, ...]:
        return tuple(sorted(claim.pin for claim in self.claims if claim.role == "reserved_signal"))

    def available_pins(self) -> tuple[int, ...]:
        reserved = set(self.reserved_signal_pins())
        return tuple(pin for pin in range(1, self.pin_count + 1) if pin not in reserved)

    def claim(self, pin: int) -> PinClaim | None:
        return self.claims_by_pin().get(pin)


@dataclass(frozen=True)
class AlchitryV2UsageProfile:
    key: BoardKey
    display_name: str
    connectors: tuple[ConnectorUsageProfile, ...]

    def connector_profile(self, connector: ConnectorKey) -> ConnectorUsageProfile:
        for profile in self.connectors:
            if profile.connector == connector:
                return profile
        raise KeyError(f"Unknown connector {connector!r} for profile {self.key!r}")

    def claims(self, connector: ConnectorKey | None = None) -> tuple[PinClaim, ...]:
        if connector is None:
            return tuple(
                claim
                for profile in self.connectors
                for claim in sorted(profile.claims, key=lambda item: (item.connector, item.pin))
            )
        return tuple(sorted(self.connector_profile(connector).claims, key=lambda item: item.pin))


def _signal_claims(
    board: BoardKey,
    connector: ConnectorKey,
    section: str,
    mapping: dict[int, str],
) -> tuple[PinClaim, ...]:
    return tuple(
        PinClaim(
            board=board,
            connector=connector,
            pin=pin,
            signal=signal,
            role="reserved_signal",
            source_url=PINOUTS_URL,
            source_section=section,
        )
        for pin, signal in sorted(mapping.items())
    )


def _constant_claims(
    board: BoardKey,
    connector: ConnectorKey,
    section: str,
    pins: tuple[int, ...],
    *,
    signal: str,
    role: PinRole,
) -> tuple[PinClaim, ...]:
    return tuple(
        PinClaim(
            board=board,
            connector=connector,
            pin=pin,
            signal=signal,
            role=role,
            source_url=PINOUTS_URL,
            source_section=section,
        )
        for pin in pins
    )


def _control_power_claims(board: BoardKey, section: str) -> tuple[PinClaim, ...]:
    return (
        _constant_claims(board, "C", section, _CONTROL_3V3_PINS, signal="+3.3V", role="power")
        + _constant_claims(board, "C", section, _CONTROL_VDD_PINS, signal="VDD", role="power")
        + _constant_claims(board, "C", section, _CONTROL_GROUND_PINS, signal="GND", role="ground")
    )


FT_PROFILE = AlchitryV2UsageProfile(
    key="ft",
    display_name="Ft",
    connectors=(
        ConnectorUsageProfile(
            board="ft",
            connector="A",
            pin_count=80,
            claims=(
                _signal_claims("ft", "A", "Ft / Bank A", _FT_BANK_A_RESERVED)
                + _constant_claims("ft", "A", "Ft / Bank A", _BANK_GROUND_PINS, signal="GND", role="ground")
            ),
        ),
        ConnectorUsageProfile(
            board="ft",
            connector="B",
            pin_count=80,
            claims=_constant_claims("ft", "B", "Ft / Bank B", _BANK_GROUND_PINS, signal="GND", role="ground"),
        ),
        ConnectorUsageProfile(
            board="ft",
            connector="C",
            pin_count=50,
            claims=_control_power_claims("ft", "Ft / Control"),
        ),
    ),
)

FT_PLUS_PROFILE = AlchitryV2UsageProfile(
    key="ft_plus",
    display_name="Ft+",
    connectors=(
        ConnectorUsageProfile(
            board="ft_plus",
            connector="A",
            pin_count=80,
            claims=(
                _signal_claims("ft_plus", "A", "Ft+ / Bank A", _FT_PLUS_BANK_A_RESERVED)
                + _constant_claims("ft_plus", "A", "Ft+ / Bank A", _BANK_GROUND_PINS, signal="GND", role="ground")
            ),
        ),
        ConnectorUsageProfile(
            board="ft_plus",
            connector="B",
            pin_count=80,
            claims=(
                _signal_claims("ft_plus", "B", "Ft+ / Bank B", _FT_PLUS_BANK_B_RESERVED)
                + _constant_claims("ft_plus", "B", "Ft+ / Bank B", _BANK_GROUND_PINS, signal="GND", role="ground")
            ),
        ),
        ConnectorUsageProfile(
            board="ft_plus",
            connector="C",
            pin_count=50,
            claims=_control_power_claims("ft_plus", "Ft+ / Control"),
        ),
    ),
)

PROFILES_BY_NAME = {
    FT_PROFILE.key: FT_PROFILE,
    FT_PLUS_PROFILE.key: FT_PLUS_PROFILE,
}


def resolve_profile(profile: str | AlchitryV2UsageProfile | None) -> AlchitryV2UsageProfile | None:
    if profile is None:
        return None
    if isinstance(profile, AlchitryV2UsageProfile):
        return profile
    profile_key = cast(BoardKey, profile)
    try:
        return PROFILES_BY_NAME[profile_key]
    except KeyError as exc:
        raise KeyError(f"Unknown Alchitry V2 profile {profile!r}") from exc


def profile_claims(
    profile: str | AlchitryV2UsageProfile,
    connector: ConnectorKey | None = None,
) -> tuple[PinClaim, ...]:
    resolved = resolve_profile(profile)
    if resolved is None:
        return ()
    return resolved.claims(connector)


def reserved_signal_pins(
    profile: str | AlchitryV2UsageProfile,
    connector: Literal["A", "B"],
) -> tuple[int, ...]:
    resolved = resolve_profile(profile)
    if resolved is None:
        return ()
    return resolved.connector_profile(connector).reserved_signal_pins()


def _make_bank_landpattern_class(
    class_name: str,
    specs: tuple[Df40PadSpec, ...],
) -> type[Landpattern]:
    x_values = [spec.x for spec in specs]
    y_values = [spec.y for spec in specs]
    width = max(x_values) - min(x_values) + 2.0
    height = max(y_values) - min(y_values) + 2.0

    class _Landpattern(Landpattern):
        def __init__(self):
            place_df40_pad_specs(self, specs)
            self.courtyard = Courtyard(rectangle(width, height))

    _Landpattern.__name__ = class_name
    return _Landpattern


@cache
def _make_bank_component_class(
    connector: Literal["A", "B"],
    *,
    top: bool,
    profile_key: str | None,
) -> type[Component]:
    specs = DF40_80_TOP_SPECS if top else DF40_80_BOTTOM_SPECS
    landpattern_class = _make_bank_landpattern_class(
        f"AlchitryV2Bank{connector}{'Top' if top else 'Bottom'}Landpattern",
        specs,
    )
    profile = resolve_profile(profile_key)
    connector_profile = profile.connector_profile(connector) if profile else None
    reserved = connector_profile.reserved_signal_pins() if connector_profile else ()
    claims_by_pin = connector_profile.claims_by_pin() if connector_profile else {}
    available = tuple(pin for pin in range(1, 81) if pin not in set(reserved))
    class_name = "AlchitryV2Bank{}{}{}".format(
        connector,
        "Top" if top else "Bottom",
        "" if profile is None else profile.display_name.replace("+", "Plus"),
    )
    description = "Alchitry V2 Bank {} {} connector".format(
        connector,
        "top-side" if top else "bottom-side",
    )
    if profile is not None:
        description += f" with {profile.display_name} reserved-signal pin mask"

    def __init__(self):
        self.landpattern = landpattern_class()
        rows = [
            Row(left=PinGroup([cast(Port, getattr(self, f"p{pin_number}"))]))
            for pin_number in available
        ]
        self.symbol = BoxSymbol(rows=rows, config=BoxConfig(group_spacing=1))
        self.pad_mapping = PadMapping(
            {
                cast(Port, getattr(self, f"p{pin_number}")): getattr(self.landpattern, f"pad_{pin_number}")
                for pin_number in available
            }
        )
        self.available_pin_numbers = available
        self.reserved_pin_numbers = reserved

    def pin(self, number: int) -> Port:
        if number in reserved:
            claim = claims_by_pin[number]
            profile_name = profile.display_name if profile else "the active profile"
            raise ValueError(
                f"Pin {connector}{number} is reserved by {profile_name} for {claim.signal} ({claim.source_section})"
            )
        return cast(Port, getattr(self, f"p{number}"))

    def claim(self, number: int) -> PinClaim | None:
        return claims_by_pin.get(number)

    attrs: dict[str, object] = {
        "__init__": __init__,
        "pin": pin,
        "claim": claim,
        "manufacturer": "Alchitry / Hirose",
        "mpn": "DF40 series 80-pin",
        "description": description,
        "reference_designator_prefix": "J",
        "value": f"ALCHITRY_V2_BANK_{connector}",
        "connector_name": connector,
        "profile_name": None if profile is None else profile.key,
        "profile_display_name": None if profile is None else profile.display_name,
        "available_pin_numbers": available,
        "reserved_pin_numbers": reserved,
        "pin_claims": claims_by_pin,
    }
    for pin_number in available:
        attrs[f"p{pin_number}"] = Port()
    return type(class_name, (Component,), attrs)


def make_alchitry_v2_bank(
    connector: Literal["A", "B"],
    *,
    top: bool,
    profile: str | AlchitryV2UsageProfile | None = None,
) -> Component:
    resolved = resolve_profile(profile)
    class_ = _make_bank_component_class(
        connector,
        top=top,
        profile_key=None if resolved is None else resolved.key,
    )
    return class_()


def make_alchitry_v2_bank_top(
    connector: Literal["A", "B"],
    *,
    profile: str | AlchitryV2UsageProfile | None = None,
) -> Component:
    return make_alchitry_v2_bank(connector, top=True, profile=profile)


def make_alchitry_v2_bank_bottom(
    connector: Literal["A", "B"],
    *,
    profile: str | AlchitryV2UsageProfile | None = None,
) -> Component:
    return make_alchitry_v2_bank(connector, top=False, profile=profile)


__all__ = [
    "AlchitryV2UsageProfile",
    "ConnectorUsageProfile",
    "FT_PLUS_PROFILE",
    "FT_PROFILE",
    "PINOUTS_URL",
    "PROFILES_BY_NAME",
    "PinClaim",
    "make_alchitry_v2_bank",
    "make_alchitry_v2_bank_bottom",
    "make_alchitry_v2_bank_top",
    "profile_claims",
    "reserved_signal_pins",
    "resolve_profile",
]
