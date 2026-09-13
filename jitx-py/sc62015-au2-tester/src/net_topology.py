from collections.abc import Sequence

from jitx.net import Net, Port


def power_net(
    name: str,
    backbone_ports: Sequence[Port],
    local_pairs: Sequence[tuple[Port, Port]],
) -> Net:
    """Connect rail ports; explicit Route objects define local routing."""
    if not backbone_ports:
        raise ValueError("a power rail requires at least one backbone port")
    local_ports = [port for pair in local_pairs for port in pair]
    return Net((*backbone_ports, *local_ports), name=name)
