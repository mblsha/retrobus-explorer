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
            "entity main(\n    clk: in bool, \n    \n\n    led: out bool,\n)\n\n",
        )

    def test_preserves_double_slash_inside_quotes(self) -> None:
        source = """\
entity main {
    const url = \"https://example.com\"; // remove me
    const slash = '// keep this literal';
}
"""

        self.assertEqual(
            strip_comments(source),
            """\
entity main {
    const url = \"https://example.com\"; 
    const slash = '// keep this literal';
}
""",
        )


if __name__ == "__main__":
    unittest.main()
