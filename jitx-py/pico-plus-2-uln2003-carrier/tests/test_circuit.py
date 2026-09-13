from jitx._instantiation import instantiation
from jitx.copper import Pour

from src.geometry import GROUND_POUR_LAYERS
from src.main import SIGNAL_AREA, PicoPlus2Uln2003CarrierCircuit, PicoPlus2Uln2003CarrierSubstrate


def test_constructed_circuit_has_bounded_ground_pours_on_both_layers():
    with instantiation.activate():
        PicoPlus2Uln2003CarrierSubstrate()
        circuit = PicoPlus2Uln2003CarrierCircuit()
    pours = [node for net in circuit.nets for node in net if isinstance(node, Pour)]
    assert len(pours) == len(GROUND_POUR_LAYERS)
    assert {pour.layer for pour in pours} == set(GROUND_POUR_LAYERS)
    assert all(pour.shape == SIGNAL_AREA for pour in pours)
