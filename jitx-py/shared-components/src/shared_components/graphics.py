from __future__ import annotations

from jitx.shapes import Shape
from jitx.shapes.primitive import Anchor, Text
from jitx.transform import Transform


def bottom_side_text(
    value: str,
    size: float,
    x: float,
    y: float,
    *,
    anchor: Anchor = Anchor.C,
    rotate: float = 0.0,
) -> Shape[Text]:
    """Place text mirrored for legible bottom-side PCB silkscreen."""

    return Text(value, size, anchor).at(Transform((x, y), rotate=rotate, scale=(-1.0, 1.0)))


__all__ = ["bottom_side_text"]
