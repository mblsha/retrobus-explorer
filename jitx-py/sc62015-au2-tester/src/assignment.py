"""Selected electrical connections; endpoint labels are derived, never parsed."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Connection:
    signal: str
    translator: str
    bank: int | None
    channel: int
    au2_pin: str
    mode: str

    @property
    def a_endpoint(self) -> str:
        suffix = f"[{self.bank}]" if self.bank is not None else ""
        return f"{self.translator}.A{suffix}[{self.channel}]"

    @property
    def b_endpoint(self) -> str:
        return self.a_endpoint.replace(".A[", ".B[")

CONNECTIONS = (
    Connection('A0', 'translators[3]', 1, 7, 'A77', 'cpu_to_fpga'),
    Connection('A1', 'translators[3]', 1, 5, 'A75', 'cpu_to_fpga'),
    Connection('A10', 'translators[3]', 0, 0, 'A27', 'cpu_to_fpga'),
    Connection('A11', 'translators[2]', 1, 7, 'B58', 'cpu_to_fpga'),
    Connection('A12', 'translators[2]', 1, 6, 'B60', 'cpu_to_fpga'),
    Connection('A13', 'translators[2]', 1, 5, 'B64', 'cpu_to_fpga'),
    Connection('A14', 'translators[2]', 1, 4, 'B66', 'cpu_to_fpga'),
    Connection('A15', 'translators[2]', 1, 3, 'B70', 'cpu_to_fpga'),
    Connection('A16', 'translators[2]', 1, 2, 'B72', 'cpu_to_fpga'),
    Connection('A17', 'translators[2]', 1, 1, 'B76', 'cpu_to_fpga'),
    Connection('A18', 'translators[2]', 1, 0, 'B78', 'cpu_to_fpga'),
    Connection('A2', 'translators[3]', 1, 4, 'A71', 'cpu_to_fpga'),
    Connection('A3', 'translators[3]', 1, 2, 'A69', 'cpu_to_fpga'),
    Connection('A4', 'translators[3]', 1, 1, 'A65', 'cpu_to_fpga'),
    Connection('A5', 'translators[3]', 0, 7, 'A45', 'cpu_to_fpga'),
    Connection('A6', 'translators[3]', 0, 6, 'A39', 'cpu_to_fpga'),
    Connection('A7', 'translators[3]', 0, 5, 'A35', 'cpu_to_fpga'),
    Connection('A8', 'translators[3]', 0, 3, 'A33', 'cpu_to_fpga'),
    Connection('A9', 'translators[3]', 0, 1, 'A29', 'cpu_to_fpga'),
    Connection('ACLK', 'translators[1]', 0, 0, 'B41', 'cpu_to_fpga'),
    Connection('CE0', 'translators[0]', 1, 2, 'B23', 'cpu_to_fpga'),
    Connection('CE1', 'translators[0]', 1, 3, 'B27', 'cpu_to_fpga'),
    Connection('CE2', 'translators[0]', 1, 4, 'B29', 'cpu_to_fpga'),
    Connection('CE3', 'translators[0]', 1, 6, 'B33', 'cpu_to_fpga'),
    Connection('CE4', 'translators[0]', 1, 7, 'B35', 'cpu_to_fpga'),
    Connection('CE5', 'translators[1]', 0, 1, 'B39', 'cpu_to_fpga'),
    Connection('CE6', 'translators[1]', 0, 2, 'B45', 'cpu_to_fpga'),
    Connection('CE7', 'translators[1]', 0, 3, 'B51', 'cpu_to_fpga'),
    Connection('CI', 'south_translators[1]', None, 2, 'A51', 'dynamic'),
    Connection('CO', 'south_translators[1]', None, 4, 'A53', 'dynamic'),
    Connection('D0', 'translators[4]', 0, 7, 'A54', 'dynamic'),
    Connection('D1', 'translators[4]', 0, 6, 'A60', 'dynamic'),
    Connection('D2', 'translators[4]', 0, 5, 'A64', 'dynamic'),
    Connection('D3', 'translators[4]', 0, 4, 'A66', 'dynamic'),
    Connection('D4', 'translators[4]', 0, 3, 'A70', 'dynamic'),
    Connection('D5', 'translators[4]', 0, 2, 'A72', 'dynamic'),
    Connection('D6', 'translators[4]', 0, 1, 'A76', 'dynamic'),
    Connection('D7', 'translators[4]', 0, 0, 'A78', 'dynamic'),
    Connection('DCLK', 'translators[1]', 1, 5, 'B47', 'cpu_to_fpga'),
    Connection('DIS', 'translators[0]', 1, 0, 'B21', 'cpu_to_fpga'),
    Connection('E0', 'e_translators[1]', None, 7, 'A3', 'dynamic'),
    Connection('E1', 'e_translators[1]', None, 6, 'A5', 'dynamic'),
    Connection('E10', 'e_translators[0]', None, 5, 'B42', 'dynamic'),
    Connection('E11', 'e_translators[0]', None, 4, 'B40', 'dynamic'),
    Connection('E12', 'e_translators[0]', None, 3, 'B36', 'dynamic'),
    Connection('E13', 'e_translators[0]', None, 2, 'B34', 'dynamic'),
    Connection('E14', 'e_translators[0]', None, 1, 'B30', 'dynamic'),
    Connection('E15', 'e_translators[0]', None, 0, 'B28', 'dynamic'),
    Connection('E2', 'e_translators[1]', None, 5, 'A9', 'dynamic'),
    Connection('E3', 'e_translators[1]', None, 4, 'A11', 'dynamic'),
    Connection('E4', 'e_translators[1]', None, 3, 'A15', 'dynamic'),
    Connection('E5', 'e_translators[1]', None, 2, 'A17', 'dynamic'),
    Connection('E6', 'e_translators[1]', None, 1, 'A21', 'dynamic'),
    Connection('E7', 'e_translators[1]', None, 0, 'A23', 'dynamic'),
    Connection('E8', 'e_translators[0]', None, 7, 'B54', 'dynamic'),
    Connection('E9', 'e_translators[0]', None, 6, 'B52', 'dynamic'),
    Connection('HA', 'translators[0]', 0, 7, 'B17', 'cpu_to_fpga'),
    Connection('IRQ', 'south_translators[0]', None, 3, 'A16', 'dynamic'),
    Connection('K10', 'translators[4]', 1, 7, 'A24', 'fpga_to_cpu'),
    Connection('K11', 'translators[4]', 1, 6, 'A28', 'fpga_to_cpu'),
    Connection('K12', 'translators[4]', 1, 5, 'A34', 'fpga_to_cpu'),
    Connection('K13', 'translators[4]', 1, 4, 'A36', 'fpga_to_cpu'),
    Connection('K14', 'translators[4]', 1, 3, 'A40', 'fpga_to_cpu'),
    Connection('K15', 'translators[4]', 1, 2, 'A46', 'fpga_to_cpu'),
    Connection('K16', 'translators[4]', 1, 1, 'A48', 'fpga_to_cpu'),
    Connection('K17', 'translators[4]', 1, 0, 'A52', 'fpga_to_cpu'),
    Connection('KO0', 'west_translator', None, 5, 'B18', 'dynamic'),
    Connection('KO1', 'west_translator', None, 4, 'B16', 'dynamic'),
    Connection('KO10', 'translators[1]', 0, 6, 'B57', 'cpu_to_fpga'),
    Connection('KO11', 'translators[1]', 0, 7, 'B59', 'cpu_to_fpga'),
    Connection('KO12', 'translators[1]', 1, 0, 'B63', 'cpu_to_fpga'),
    Connection('KO13', 'translators[1]', 1, 1, 'B65', 'cpu_to_fpga'),
    Connection('KO14', 'translators[1]', 1, 2, 'B69', 'cpu_to_fpga'),
    Connection('KO15', 'translators[1]', 1, 4, 'B71', 'cpu_to_fpga'),
    Connection('KO2', 'west_translator', None, 2, 'B10', 'dynamic'),
    Connection('KO3', 'west_translator', None, 1, 'B6', 'dynamic'),
    Connection('KO4', 'west_translator', None, 3, 'B12', 'dynamic'),
    Connection('KO5', 'west_translator', None, 0, 'B4', 'dynamic'),
    Connection('KO6', 'translators[0]', 0, 0, 'B3', 'cpu_to_fpga'),
    Connection('KO7', 'translators[0]', 0, 1, 'B5', 'cpu_to_fpga'),
    Connection('KO8', 'translators[0]', 0, 3, 'B9', 'cpu_to_fpga'),
    Connection('KO9', 'translators[0]', 0, 4, 'B11', 'cpu_to_fpga'),
    Connection('MRQ', 'south_translators[1]', None, 7, 'A63', 'dynamic'),
    Connection('ON', 'south_translators[1]', None, 5, 'A57', 'dynamic'),
    Connection('OUT', 'translators[1]', 0, 5, 'B53', 'cpu_to_fpga'),
    Connection('RD', 'translators[0]', 0, 5, 'B15', 'cpu_to_fpga'),
    Connection('RESET', 'south_translators[0]', None, 4, 'A18', 'dynamic'),
    Connection('RXD', 'west_translator', None, 6, 'B22', 'dynamic'),
    Connection('TEST', 'south_translators[0]', None, 5, 'A22', 'dynamic'),
    Connection('TXD', 'west_translator', None, 7, 'B24', 'dynamic'),
    Connection('VA', 'translators[1]', 1, 6, 'B75', 'cpu_to_fpga'),
    Connection('VDD', 'south_translators[0]', None, 2, 'A12', 'dynamic'),
    Connection('VDISP', 'translators[1]', 1, 7, 'B77', 'cpu_to_fpga'),
    Connection('WR', 'south_translators[1]', None, 6, 'A59', 'dynamic'),
    Connection('X1', 'south_translators[1]', None, 0, 'A41', 'dynamic'),
    Connection('X2', 'south_translators[0]', None, 0, 'A4', 'dynamic'),
    Connection('X3', 'south_translators[1]', None, 1, 'A47', 'dynamic'),
    Connection('X4', 'south_translators[0]', None, 1, 'A6', 'dynamic'),
)

CONNECTION_BY_SIGNAL = {c.signal: c for c in CONNECTIONS}
CONNECTION_BY_CHANNEL = {(c.translator, c.bank, c.channel): c for c in CONNECTIONS}
