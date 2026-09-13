from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from src.components import HeaderPthPad


class HeaderGeometryTests(unittest.TestCase):
    def test_pth_annulus_is_exposed_on_both_faces(self) -> None:
        module_source = Path(inspect.getfile(HeaderPthPad)).read_text()
        source = module_source.split("class HeaderPthPad(Pad):", 1)[1].split("\n\nclass ", 1)[0]

        self.assertIn("soldermask_top", source)
        self.assertIn("side=Side.Top", source)
        self.assertIn("soldermask_bottom", source)
        self.assertIn("side=Side.Bottom", source)
        self.assertNotIn("self.soldermask =", source)


if __name__ == "__main__":
    unittest.main()
