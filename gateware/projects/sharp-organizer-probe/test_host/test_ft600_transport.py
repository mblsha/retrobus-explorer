"""FT600 marker and byte-count checks prevent publishing misframed reads."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ft600_transport import Ft600, decode_payload


class Ft600Test(unittest.TestCase):
    def test_every_word_has_a_marker_and_exact_count(self):
        self.assertEqual(decode_payload(b"\x00\xa5\xff\xa5", 2), b"\x00\xff")
        for raw in (b"\x00\xa5", b"\x00\xa5\xff\x00", b"\x00\xa5\xff\xa5\x00"):
            with self.assertRaises(OSError):
                decode_payload(raw, 2)

    def test_partial_usb_reads_are_joined_before_decode(self):
        port = Ft600.__new__(Ft600)
        port.read = Mock(side_effect=[b"\x00\xa5\xff", b"\xa5"])
        self.assertEqual(port.read_payload(2, 1000), b"\x00\xff")
        self.assertEqual([call.args[0] for call in port.read.call_args_list], [4, 1])


if __name__ == "__main__":
    unittest.main()
