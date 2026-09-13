from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol, cast

from alchitry_v2_elements import AlchitryV2BottomElement
from jitx.board import Board
from jitx.circuit import Circuit, Route
from jitx.design import Design
from jitx.feature import Silkscreen
from jitx.layerindex import Side as FeatureSide
from jitx.net import Port, Provide
from jitx.placement import Placement, Side
from jitx.shapes.composites import rectangle
from jitx.substrate import Substrate
from jitx.via import Via, ViaType
from shared_components.connectivity import connect_ports
from shared_components.fabrication import jlcpcb_fab_constraints, jlcpcb_stackup, silkscreen_text
from shared_components.testpads import gnd_testpads_class

from src.assignment import (
    CONNECTION_BY_CHANNEL,
    CONNECTIONS,
)
from src.components import (
    Capacitor0402,
    Capacitor0805,
    Resistor0402,
    Sc62015B02,
    Sn74Lvc16T245,
    TestPad,
    Txs0108e,
)
from src.net_topology import power_net
from src.physical import (
    AU2_ELEMENT_ORIGIN,
    BOARD_CENTER_X,
    BOARD_HEIGHT,
    BOARD_WIDTH,
    CONTROL_PULL_PLACEMENTS,
    CPU_PLACEMENT,
    LVC_TRANSLATOR_PLACEMENTS,
    MOUNTING_HOLE_DIAMETER,
    MOUNTING_HOLE_EDGE_INSET,
    MOUNTING_HOLE_PAD_DIAMETER,
    RESET_PULL_PLACEMENT,
    TARGET_BULK_CAP_PLACEMENT,
    TESTPAD_PLACEMENTS,
    TOP_ASSEMBLY_SHIFT_X,
    TRANSLATOR_DECOUPLING_CLUSTERS,
)
from src.pinmap import (
    ACTIVE_LOW_ENABLE_CONTROL_NAMES,
    ASSIGNABLE_AU2_GPIO_NAMES,
    AU2_PIN_BY_LOGICAL_SIGNAL,
    AUTO_BIDIRECTIONAL_BANKS,
    BANKS,
    CONTROL_SIGNAL_NAMES,
    E_PORT_BANKS,
    ENABLE_CONTROL_SIGNAL_NAMES,
    SOUTH_AUTO_BANKS,
    signal_to_net_name,
)
from src.via_policy import SIGNAL_VIA_DIAMETER_MM, SIGNAL_VIA_DRILL_MM

REPO_ROOT = Path(__file__).resolve().parents[3]
BOARD_DATE = subprocess.check_output(
    ["git", "log", "-1", "--format=%cs"],
    text=True,
    cwd=REPO_ROOT,
).strip()

BOARD_SHAPE = rectangle(BOARD_WIDTH, BOARD_HEIGHT, radius=3.0).at(BOARD_CENTER_X, 0.0)
SIGNAL_AREA = rectangle(BOARD_WIDTH - 1.0, BOARD_HEIGHT - 1.0, radius=2.5).at(BOARD_CENTER_X, 0.0)
MOUNTING_HOLE_ARRAY_WIDTH = 2.0 * (BOARD_WIDTH / 2.0 - MOUNTING_HOLE_EDGE_INSET + MOUNTING_HOLE_PAD_DIAMETER)
MOUNTING_HOLE_ARRAY_HEIGHT = 2.0 * (BOARD_HEIGHT / 2.0 - MOUNTING_HOLE_EDGE_INSET + MOUNTING_HOLE_PAD_DIAMETER)
ADAPTER_MOUNTING_HOLES = gnd_testpads_class(
    diameter=MOUNTING_HOLE_PAD_DIAMETER,
    hole_diameter=MOUNTING_HOLE_DIAMETER,
    width=MOUNTING_HOLE_ARRAY_WIDTH,
    height=MOUNTING_HOLE_ARRAY_HEIGHT,
)


class AlchitryV2BottomInterface(Protocol):
    GND: Port
    V3V3: Port
    VCC: Port

    def port(self, signal_name: str) -> Port: ...


class GroundedMountingHolesInterface(Protocol):
    GND: Port


class Au2AssignableGpio(Port):
    """One translated SC62015 signal assignable to one safe Au2 GPIO."""

    signal = Port()


AUTO_TRANSLATOR_PREFIXES = (
    "south_translators[0]",
    "west_translator",
    "south_translators[1]",
    "e_translators[0]",
    "e_translators[1]",
)


def _validate_assignment() -> None:
    """Fail closed when the static assignment and electrical bank policy diverge."""
    if len(CONNECTIONS) != 98 or len(CONNECTION_BY_CHANNEL) != 98:
        raise AssertionError("assignment must expose exactly 98 translated signals")

    lvc_by_class: dict[tuple[int, str, str | None, str | None], set[str]] = {}
    auto_by_prefix: dict[str, set[str]] = {prefix: set() for prefix in AUTO_TRANSLATOR_PREFIXES}
    expected_lvc_references = {f"translators[{index}]" for index in range(5)}
    for row in CONNECTIONS:
        reference = row.translator
        if reference in expected_lvc_references:
            translator_index = int(reference.removeprefix("translators[").removesuffix("]"))
            translator_bank, channel = (row.bank, row.channel)
            bank_index = translator_index * 2 + translator_bank
            expected_b = f"translators[{translator_index}].B[{translator_bank}][{channel}]"
            if row.b_endpoint != expected_b:
                raise AssertionError(f"assignment B endpoint mismatch for {row.signal}")
            if row.mode != BANKS[bank_index].mode:
                raise AssertionError(f"assignment direction mismatch for {row.signal}")
            bank = BANKS[bank_index]
            key = (translator_index, bank.mode, bank.oe_control, bank.dir_control)
            lvc_by_class.setdefault(key, set()).add(row.signal)
        else:
            prefix = row.translator
            if prefix not in auto_by_prefix:
                raise AssertionError(f"unknown auto translator instance {prefix}")
            channel = row.channel
            expected_b = f"{prefix}.B[{channel}]"
            if row.b_endpoint != expected_b or row.mode != "dynamic":
                raise AssertionError(f"assignment auto endpoint/direction mismatch for {row.signal}")
            auto_by_prefix[prefix].add(row.signal)

    expected_lvc_by_class: dict[tuple[int, str, str | None, str | None], set[str]] = {}
    for index, bank in enumerate(BANKS):
        key = (index // 2, bank.mode, bank.oe_control, bank.dir_control)
        expected_lvc_by_class.setdefault(key, set()).update(signal for signal in bank.signals if signal is not None)
    if lvc_by_class != {key: signals for key, signals in expected_lvc_by_class.items() if signals}:
        raise AssertionError("assignment consumer changes an LVC electrical direction/control class")
    for prefix, bank in zip(AUTO_TRANSLATOR_PREFIXES, AUTO_BIDIRECTIONAL_BANKS, strict=True):
        expected = {signal for signal in bank.signals if signal is not None}
        if auto_by_prefix[prefix] != expected:
            raise AssertionError(f"assignment consumer changes the signal set of {prefix}")


class Sc62015Au2TesterSubstrate(Substrate):
    stackup = jlcpcb_stackup(4)
    constraints = jlcpcb_fab_constraints(4)

    class StandardVia(Via):
        start_layer = 0
        stop_layer = 3
        diameter = SIGNAL_VIA_DIAMETER_MM
        hole_diameter = SIGNAL_VIA_DRILL_MM
        type = ViaType.MechanicalDrill


class Sc62015Au2TesterCircuit(Circuit):
    def __init__(self):
        super().__init__()
        _validate_assignment()
        # The canonical Au2 holes follow the 55 x 45 mm mating outline.  This
        # larger adapter owns its mounting holes instead, at its own corners.
        self.au2 = AlchitryV2BottomElement(include_holes=False)  # ty: ignore[unknown-argument]
        au2 = cast(AlchitryV2BottomInterface, self.au2)
        self.au2_gpio_providers = Provide(Au2AssignableGpio).all_of(
            lambda bundle: [{bundle.signal: au2.port(pin)} for pin in ASSIGNABLE_AU2_GPIO_NAMES]
        )
        self.mounting_holes = ADAPTER_MOUNTING_HOLES()
        mounting_holes = cast(GroundedMountingHolesInterface, self.mounting_holes)
        self.cpu = Sc62015B02(include_body_cutout=False)
        self.translators = [Sn74Lvc16T245() for _ in LVC_TRANSLATOR_PLACEMENTS]
        self.south_translators = [Txs0108e() for _ in SOUTH_AUTO_BANKS]
        self.west_translator = Txs0108e()
        self.e_translators = [Txs0108e() for _ in E_PORT_BANKS]
        auto_translators = [
            self.south_translators[0],
            self.west_translator,
            self.south_translators[1],
            *self.e_translators,
        ]
        all_translators = [*self.translators, *auto_translators]
        translator_supply_ports = [
            *(
                [translator.VCCA[0], translator.VCCA[1], translator.VCCB[0], translator.VCCB[1]]
                for translator in self.translators
            ),
            *([translator.VCCA, translator.VCCB] for translator in auto_translators),
        ]
        self.decoupling = [
            [Capacitor0402("100nF") for _ in cluster.sites]
            for cluster in TRANSLATOR_DECOUPLING_CLUSTERS
        ]

        # Keep the previous output-cap object name so the live stable design
        # preserves its reference while it becomes the single target bulk cap.
        self.power_output_cap = Capacitor0805("10uF")
        self.tp_target_in = TestPad()

        # RESET is active high. This target-side pull keeps the CPU reset while
        # the FPGA side of its always-enabled TXS channel is high impedance.
        self.reset_pull = Resistor0402("10k")
        self.vcc_testpad = TestPad()
        self.signal_testpads = {name: TestPad() for name in ("VDD", "VDISP", "VA")}

        enable_controls = set(ENABLE_CONTROL_SIGNAL_NAMES)
        self.control_pulls = {
            name: Resistor0402("10k" if name in enable_controls else "100k") for name in CONTROL_SIGNAL_NAMES
        }

        gnd_ports: list[Port] = [
            au2.GND,
            self.cpu.GND,
            self.power_output_cap.p[1],
            mounting_holes.GND,
        ]
        v3v3_ports: list[Port] = [au2.V3V3]
        target_ports: list[Port] = [
            au2.VCC,
            self.cpu.VCC,
            self.tp_target_in.p,
            self.power_output_cap.p[0],
            self.reset_pull.p[1],
            self.vcc_testpad.p,
        ]

        control_ports: dict[str, list[Port]] = {
            name: [au2.port(AU2_PIN_BY_LOGICAL_SIGNAL[name])] for name in CONTROL_SIGNAL_NAMES
        }

        self.nets = []
        for bank_index, bank in enumerate(BANKS):
            translator = self.translators[bank_index // 2]
            translator_bank = bank_index % 2

            if bank.oe_control is None:
                gnd_ports.append(translator.OE_N[translator_bank])
            else:
                control_ports[bank.oe_control].append(translator.OE_N[translator_bank])
            if bank.mode == "cpu_to_fpga":
                gnd_ports.append(translator.DIR[translator_bank])
            elif bank.mode == "fpga_to_cpu":
                v3v3_ports.append(translator.DIR[translator_bank])
            else:
                if bank.dir_control is None:
                    raise AssertionError(f"Dynamic bank {bank.name} has no direction control")
                control_ports[bank.dir_control].append(translator.DIR[translator_bank])

            for channel in range(8):
                b_endpoint = f"translators[{bank_index // 2}].B[{translator_bank}][{channel}]"
                assignment = CONNECTION_BY_CHANNEL.get((f"translators[{bank_index // 2}]", translator_bank, channel))
                signal = assignment.signal if assignment is not None else None
                if signal is None:
                    if bank.mode == "cpu_to_fpga":
                        # B is the input in this direction. Ground it and leave
                        # the corresponding A output unconnected.
                        gnd_ports.append(translator.B[translator_bank][channel])
                    elif bank.mode == "fpga_to_cpu":
                        # A is the input in this direction. Leave the
                        # corresponding B output unconnected.
                        gnd_ports.append(translator.A[translator_bank][channel])
                    else:
                        raise AssertionError(f"Dynamic bank {bank.name} contains an unused channel")
                    continue

                if assignment is None:
                    raise AssertionError(f"missing assignment row for {b_endpoint}")
                net_signal = signal_to_net_name(signal)
                au2_port = au2.port(assignment.au2_pin)
                self.nets.append(
                    connect_ports(
                        f"FPGA-{net_signal}",
                        *[au2_port, translator.A[translator_bank][channel]],
                    )
                )
                cpu_side_ports = [translator.B[translator_bank][channel], self.cpu.port(signal)]
                if signal == "RESET":
                    cpu_side_ports.append(self.reset_pull.p[0])
                if signal in self.signal_testpads:
                    cpu_side_ports.append(self.signal_testpads[signal].p)
                self.nets.append(connect_ports(f"CPU-{net_signal}", *cpu_side_ports))

        for bank, translator, prefix in zip(
            AUTO_BIDIRECTIONAL_BANKS,
            auto_translators,
            AUTO_TRANSLATOR_PREFIXES,
            strict=True,
        ):
            if bank.enable_control is None:
                # The perimeter-ordered auto-direction banks remain enabled
                # whenever the Au2 3.3-V rail is present.
                v3v3_ports.append(translator.OE)
            else:
                control_ports[bank.enable_control].append(translator.OE)
            for channel in range(8):
                b_endpoint = f"{prefix}.B[{channel}]"
                assignment = CONNECTION_BY_CHANNEL.get((prefix, None, channel))
                signal = assignment.signal if assignment is not None else None
                if signal is None:
                    continue
                if assignment is None:
                    raise AssertionError(f"missing assignment row for {b_endpoint}")
                net_signal = signal_to_net_name(signal)
                au2_port = au2.port(assignment.au2_pin)
                self.nets.append(
                    connect_ports(
                        f"FPGA-{net_signal}",
                        *[au2_port, translator.A[channel]],
                    )
                )
                cpu_side_ports = [translator.B[channel], self.cpu.port(signal)]
                if signal == "RESET":
                    cpu_side_ports.append(self.reset_pull.p[0])
                if signal in self.signal_testpads:
                    cpu_side_ports.append(self.signal_testpads[signal].p)
                self.nets.append(connect_ports(f"CPU-{net_signal}", *cpu_side_ports))

        decoupling_rail_pairs: dict[str, list[tuple[Port, Port]]] = {"V3V3": [], "TARGET": []}
        for translator, supply_ports, cluster, capacitors in zip(
            all_translators,
            translator_supply_ports,
            TRANSLATOR_DECOUPLING_CLUSTERS,
            self.decoupling,
            strict=True,
        ):
            gnd_ports.append(translator.GND)
            for site, supply_port, capacitor in zip(cluster.sites, supply_ports, capacitors, strict=True):
                decoupling_rail_pairs[site.rail].append((supply_port, capacitor.p[0]))
                gnd_ports.append(capacitor.p[1])

        for name, ports in control_ports.items():
            pull = self.control_pulls[name]
            ports.append(pull.p[0])
            if name in ACTIVE_LOW_ENABLE_CONTROL_NAMES:
                v3v3_ports.append(pull.p[1])
            else:
                gnd_ports.append(pull.p[1])
            self.nets.append(connect_ports(name, *ports))

        self.nets.append(connect_ports("GND", *gnd_ports))
        self.nets.append(power_net("V3V3", v3v3_ports, decoupling_rail_pairs["V3V3"]))
        self.nets.append(power_net("TARGET", target_ports, decoupling_rail_pairs["TARGET"]))
        # Source-level Route requests are the JITX-native physical authority
        # for exact endpoint pairs on branched, multi-terminal power rails.
        # With no sketch, JITX owns the organic final copper geometry.
        self.pdn_supply_routes = [
            Route(owner, capacitor, 0)
            for rail in ("V3V3", "TARGET")
            for owner, capacitor in decoupling_rail_pairs[rail]
        ]

        self.place(self.au2, Placement(AU2_ELEMENT_ORIGIN, on=Side.Top))
        self.place(self.mounting_holes, Placement((BOARD_CENTER_X, 0.0), on=Side.Top))
        self.place(
            self.cpu,
            Placement(CPU_PLACEMENT.position, CPU_PLACEMENT.rotation, on=Side.Top),  # ty: ignore[no-matching-overload]
        )

        for translator, cluster, capacitors in zip(
            all_translators, TRANSLATOR_DECOUPLING_CLUSTERS, self.decoupling, strict=True
        ):
            self.place(
                translator,
                Placement(cluster.translator.position, cluster.translator.rotation, on=Side.Top),  # ty: ignore[no-matching-overload]
            )
            for site, capacitor in zip(cluster.sites, capacitors, strict=True):
                self.place(
                    capacitor,
                    Placement(site.capacitor.position, site.capacitor.rotation, on=Side.Top),  # ty: ignore[no-matching-overload]
                )

        self.place(self.power_output_cap, Placement(TARGET_BULK_CAP_PLACEMENT.position, on=Side.Top))
        self.place(self.tp_target_in, Placement(TESTPAD_PLACEMENTS["TARGET"].position, on=Side.Top))

        for signal_name, testpad in self.signal_testpads.items():
            placement = TESTPAD_PLACEMENTS[signal_name]
            self.place(testpad, Placement(placement.position, on=Side.Top))
            self += Silkscreen(silkscreen_text(signal_name).at(placement.x, placement.y + 2.5), side=FeatureSide.Top)

        vcc_testpad_placement = TESTPAD_PLACEMENTS["VCC"]
        self.place(self.vcc_testpad, Placement(vcc_testpad_placement.position, on=Side.Top))
        self.place(self.reset_pull, Placement(RESET_PULL_PLACEMENT.position, on=Side.Top))
        self += Silkscreen(
            silkscreen_text("TARGET").at(TESTPAD_PLACEMENTS["TARGET"].x, TESTPAD_PLACEMENTS["TARGET"].y + 2.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            silkscreen_text("VCC").at(vcc_testpad_placement.x, vcc_testpad_placement.y + 2.5),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            silkscreen_text("RST HOLD").at(-24.5 + TOP_ASSEMBLY_SHIFT_X, 25.5),
            side=FeatureSide.Top,
        )

        for name in CONTROL_SIGNAL_NAMES:
            placement = CONTROL_PULL_PLACEMENTS[name]
            self.place(
                self.control_pulls[name],
                Placement(placement.position, placement.rotation, on=Side.Top),  # ty: ignore[no-matching-overload]
            )

        self += Silkscreen(
            silkscreen_text("SC62015 Au2 Tester", 1.4).at(-10.0 + TOP_ASSEMBLY_SHIFT_X, 28.6),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            silkscreen_text(f"Rev A  {BOARD_DATE}").at(-10.0 + TOP_ASSEMBLY_SHIFT_X, 27.0),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            silkscreen_text("AU2 VCC = TARGET 5V ONLY").at(-6.5 + TOP_ASSEMBLY_SHIFT_X, -34.0),
            side=FeatureSide.Top,
        )
        self += Silkscreen(
            silkscreen_text("RESET HIGH = ASSERTED").at(10.0 + TOP_ASSEMBLY_SHIFT_X, 27.0),
            side=FeatureSide.Top,
        )


class Sc62015Au2TesterBoard(Board):
    shape = BOARD_SHAPE
    signal_area = SIGNAL_AREA


class Sc62015Au2TesterDesign(Design):
    substrate = Sc62015Au2TesterSubstrate()
    board = Sc62015Au2TesterBoard()
    circuit = Sc62015Au2TesterCircuit()
