"""FFC data-to-level-shifter-to-Au2 pin assignment.

This module deliberately has no JITX imports.  The complete end-to-end
assignment can therefore be validated with ordinary unit tests even when the
proprietary runtime is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DataConnection:
    """Connect one FFC data number through one shifter channel to one Au2 pin."""

    shifter_index: int
    shifter_pin: int
    fpga_pin: str

    @property
    def channel(self) -> tuple[int, int]:
        return (self.shifter_index, self.shifter_pin)


# Preserve the selected electrical connections; copper routing is generated locally.
DATA_CONNECTIONS: tuple[DataConnection, ...] = (
    DataConnection(0, 0, "B4"),  # DATA0
    DataConnection(0, 1, "B6"),  # DATA1
    DataConnection(0, 2, "B10"),  # DATA2
    DataConnection(0, 3, "B12"),  # DATA3
    DataConnection(0, 4, "B16"),  # DATA4
    DataConnection(4, 7, "A40"),  # DATA5
    DataConnection(0, 5, "B18"),  # DATA6
    DataConnection(0, 6, "B22"),  # DATA7
    DataConnection(0, 7, "B24"),  # DATA8
    DataConnection(4, 6, "A42"),  # DATA9
    DataConnection(4, 5, "A46"),  # DATA10
    DataConnection(4, 4, "A48"),  # DATA11
    DataConnection(4, 3, "A52"),  # DATA12
    DataConnection(4, 2, "A54"),  # DATA13
    DataConnection(4, 1, "A45"),  # DATA14
    DataConnection(1, 0, "B28"),  # DATA15
    DataConnection(4, 0, "A47"),  # DATA16
    DataConnection(1, 1, "B30"),  # DATA17
    DataConnection(1, 2, "B34"),  # DATA18
    DataConnection(1, 3, "B36"),  # DATA19
    DataConnection(1, 4, "B40"),  # DATA20
    DataConnection(1, 5, "B42"),  # DATA21
    DataConnection(1, 6, "B46"),  # DATA22
    DataConnection(1, 7, "B48"),  # DATA23
    DataConnection(2, 7, "A51"),  # DATA24
    DataConnection(2, 6, "A53"),  # DATA25
    DataConnection(2, 5, "A58"),  # DATA26
    DataConnection(2, 4, "A60"),  # DATA27
    DataConnection(2, 3, "A57"),  # DATA28
    DataConnection(2, 2, "A59"),  # DATA29
    DataConnection(5, 0, "B58"),  # DATA30
    DataConnection(2, 1, "A63"),  # DATA31
    DataConnection(5, 1, "B60"),  # DATA32
    DataConnection(5, 2, "B64"),  # DATA33
    DataConnection(5, 3, "B66"),  # DATA34
    DataConnection(2, 0, "A65"),  # DATA35
    DataConnection(5, 4, "B70"),  # DATA36
    DataConnection(5, 5, "B72"),  # DATA37
    DataConnection(5, 6, "B76"),  # DATA38
    DataConnection(5, 7, "B78"),  # DATA39
    DataConnection(3, 7, "A69"),  # DATA40
    DataConnection(3, 6, "A70"),  # DATA41
    DataConnection(3, 5, "A71"),  # DATA42
    DataConnection(3, 4, "A72"),  # DATA43
    DataConnection(3, 3, "A75"),  # DATA44
    DataConnection(3, 2, "A77"),  # DATA45
    DataConnection(3, 1, "A76"),  # DATA46
    DataConnection(3, 0, "A78"),  # DATA47
)

