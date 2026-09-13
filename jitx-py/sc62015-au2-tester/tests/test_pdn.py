import math
from typing import cast

from jitx.net import Port

from src import net_topology
from src.components import Capacitor0201, Capacitor0402, Capacitor0603, Capacitor0805, Sn74Lvc16T245
from src.physical import (
    LVC_TRANSLATOR_PLACEMENTS,
    TRANSLATOR_DECOUPLING_CLUSTERS,
    TXS_TRANSLATOR_PLACEMENTS,
    DecouplingSite,
    _place,
    _tssop20_pad_position,
    _tssop48_pad_position,
)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _capacitor_pad(site: DecouplingSite, local_x: float) -> tuple[float, float]:
    capacitor = site.capacitor
    return _place((local_x, 0.0), capacitor)


def test_capacitor_family_exposes_small_decoupling_and_larger_bulk_packages() -> None:
    assert Capacitor0201.mpn == "0201-capacitor"
    assert Capacitor0402.mpn == "0402-capacitor"
    assert Capacitor0603.mpn == "0603-capacitor"
    assert Capacitor0805.mpn == "0805-capacitor"


def test_power_net_stays_flat_when_source_routes_own_local_pairs(monkeypatch) -> None:
    class FakePort:
        def __init__(self, name):
            self.name = name

    class FakeNet:
        def __init__(self, ports, *, name=None):
            self.ports = list(ports)
            self.name = name
            net_calls.append(self)

    net_calls: list[FakeNet] = []

    monkeypatch.setattr(net_topology, "Net", FakeNet)
    backbone = cast(list[Port], [FakePort("root"), FakePort("source")])
    pairs = cast(list[tuple[Port, Port]], [
        (FakePort("owner-1"), FakePort("cap-1")),
        (FakePort("owner-2"), FakePort("cap-2")),
    ])
    result = net_topology.power_net("POWER", backbone, pairs)
    assert len(net_calls) == 1
    assert net_calls[0].ports == [*backbone, *pairs[0], *pairs[1]]
    assert net_calls[0].name == "POWER"
    assert result is net_calls[0]


def test_every_physical_supply_pin_gets_one_owner_relative_0402() -> None:
    assert len(TRANSLATOR_DECOUPLING_CLUSTERS) == 10
    assert [len(cluster.sites) for cluster in TRANSLATOR_DECOUPLING_CLUSTERS] == [4] * 5 + [2] * 5
    assert sum(site.rail == "V3V3" for cluster in TRANSLATOR_DECOUPLING_CLUSTERS for site in cluster.sites) == 15
    assert sum(site.rail == "TARGET" for cluster in TRANSLATOR_DECOUPLING_CLUSTERS for site in cluster.sites) == 15


def test_capacitor_supply_pad_faces_its_owner_pin_and_loop_is_bounded() -> None:
    for index, cluster in enumerate(TRANSLATOR_DECOUPLING_CLUSTERS):
        is_lvc = index < len(LVC_TRANSLATOR_PLACEMENTS)
        pad_position = _tssop48_pad_position if is_lvc else _tssop20_pad_position
        maximum = 1.11 if is_lvc else 1.56
        for site in cluster.sites:
            owner_pad = _place(pad_position(site.owner_pin), cluster.translator)
            supply_pad = _capacitor_pad(site, -0.5)
            ground_pad = _capacitor_pad(site, 0.5)
            assert _distance(owner_pad, supply_pad) <= maximum
            owner_to_supply = (supply_pad[0] - owner_pad[0], supply_pad[1] - owner_pad[1])
            supply_to_ground = (ground_pad[0] - supply_pad[0], ground_pad[1] - supply_pad[1])
            assert owner_to_supply[0] * supply_to_ground[0] + owner_to_supply[1] * supply_to_ground[1] > 0


def test_lvc_supply_pins_are_distinct_stable_route_endpoints() -> None:
    ports = [*Sn74Lvc16T245.VCCA, *Sn74Lvc16T245.VCCB]
    assert len(ports) == 4
    assert len({id(port) for port in ports}) == 4


def test_translator_and_cluster_placement_authorities_cannot_diverge() -> None:
    assert tuple(cluster.translator for cluster in TRANSLATOR_DECOUPLING_CLUSTERS) == (
        *LVC_TRANSLATOR_PLACEMENTS,
        *TXS_TRANSLATOR_PLACEMENTS,
    )
