from pathlib import Path
import types
import sys
import unittest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

if "serial" not in sys.modules:
    sys.modules["serial"] = types.SimpleNamespace(Serial=object, SerialException=Exception)

from pc_e500_experiment_common import parse_hex_or_int


class ParseHexOrIntTests(unittest.TestCase):
    def test_parses_prefixed_hex_in_mixed_case(self) -> None:
        self.assertEqual(parse_hex_or_int("0x1f"), 0x1F)
        self.assertEqual(parse_hex_or_int("0X2A"), 0x2A)

    def test_parses_hex_without_prefix_if_alpha_digits_present(self) -> None:
        self.assertEqual(parse_hex_or_int("ABCD"), 0xABCD)
        self.assertEqual(parse_hex_or_int("1f"), 0x1F)

    def test_rejects_empty_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_hex_or_int("   ")


if __name__ == "__main__":
    unittest.main()
