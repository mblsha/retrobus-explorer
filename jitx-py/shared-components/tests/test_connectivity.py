from jitx._instantiation import instantiation
from jitx.net import Net, Port

from shared_components.connectivity import connect_ports


def test_flat_net_preserves_ports_without_nested_route_topology():
    with instantiation.activate():
        ports = [Port(), Port(), Port()]
        net = connect_ports("rail", *ports)
    assert list(net) == ports
    assert not any(isinstance(port, Net) for port in net)


def test_flat_helper_preserves_membership_of_previous_addition_pattern():
    with instantiation.activate():
        ports = [Port(), Port(), Port()]
        previous = Net(name="rail")
        for port in ports:
            previous = previous + port
        current = connect_ports("rail", *ports)
    assert {id(p) for p in previous} == {
        id(p) for p in current
    } == {id(p) for p in ports}
