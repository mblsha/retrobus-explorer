from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ft_uart_hex_bridge.py"
SPEC = importlib.util.spec_from_file_location("ft_uart_hex_bridge_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ParseWordTokenTests(unittest.TestCase):
    def test_accepts_single_digit_be(self) -> None:
        self.assertEqual(MODULE.parse_word_token("1234/1"), (0x1234, 0x1))

    def test_rejects_multi_digit_be(self) -> None:
        with self.assertRaisesRegex(ValueError, "single byte-enable digit"):
            MODULE.parse_word_token("1234/01")


if __name__ == "__main__":
    unittest.main()
