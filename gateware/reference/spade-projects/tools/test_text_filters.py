from __future__ import annotations

import unittest

from text_filters import strip_comments


class StripCommentsTest(unittest.TestCase):
    def test_removes_block_and_line_comments(self) -> None:
        source = """\
entity main(
    clk: in bool, // keep port
    /* remove this whole
       block comment */
    led: out bool,
)
// remove trailing comment line
"""

        self.assertEqual(
            strip_comments(source),
            """\
entity main(
    clk: in bool, 
    
    led: out bool,
)
""",
        )


if __name__ == "__main__":
    unittest.main()
