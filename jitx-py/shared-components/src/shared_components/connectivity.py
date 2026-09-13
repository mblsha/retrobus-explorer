"""Flat electrical connectivity; physical routing remains board-specific."""
from jitx.net import Net, Port


def connect_ports(name: str | None, *ports: Port) -> Net:
    """Connect ports without prescribing a route tree or endpoint pairs."""
    return Net(ports, name=name)
