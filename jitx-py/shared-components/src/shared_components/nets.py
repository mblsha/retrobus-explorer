from __future__ import annotations

from jitx.net import Net, Port


def connect_ports(name: str | None, *ports: Port) -> Net:
    """Create one flat net and attach each supplied port in order."""

    return Net(ports, name=name) if name is not None else Net(ports)


__all__ = ["connect_ports"]
