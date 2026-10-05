"""Direct UART access reuses the existing backend and requires interface B."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ftdi_uart import open_ftdi_uart, parse_uart_uri


class FtdiUartTest(unittest.TestCase):
    def test_only_explicit_serial_and_interface_b_are_accepted(self):
        self.assertEqual(parse_uart_uri("ftdi://TEST123/B"), "TEST123")
        for uri in ("ftdi:///B", "ftdi://TEST/A", "ftdi://TEST", "ftdi://TEST/B/extra"):
            with self.assertRaises(ValueError):
                parse_uart_uri(uri)

    def test_existing_backend_receives_the_exact_serial_and_baud(self):
        implementation = Mock()
        with patch("ftdi_uart._implementation", return_value=implementation):
            port = open_ftdi_uart("ftdi://TEST123/B", 4000000)
        implementation.assert_called_once_with("TEST123", baud=4000000, timeout=0.5)
        self.assertEqual(port.baudrate, 4000000)
        self.assertEqual(port.transport, "libftdi1")


if __name__ == "__main__":
    unittest.main()
