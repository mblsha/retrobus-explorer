"""A behaviour-preserving refactor must not change the hardware.

The compiler renames things freely between builds -- monomorphisation ids,
`impl#N` indices, `src` attributes, its own temporaries, declaration order, and
which half of an alias pair carries the logic. A comparison that reads those as
differences reports noise on every edit and is therefore useless as a safety
check. These tests pin down that the canonicaliser sees through each of those,
and still notices a real change: a different expression, a lost module, a
gained one.
"""

import contextlib
import io
import unittest

import sv_module_bodies as bodies


# One counter, built twice. `\value`, `__n2` and `__n5` are the same net, and
# which of them the consumers are written against depends on an ordering that
# shifts whenever an expression is added anywhere in the unit.
BEFORE = """\
module \\lib::counter[2693]  (
        input clk_i,
        input rst_i,
        output[7:0] output__
    );
    (* src = "counter.spade:5,1" *)
    reg[7:0] \\value ;
    logic[7:0] __n2;
    assign __n2 = \\value ;
    logic[7:0] __n5;
    assign __n5 = __n2;
    logic[7:0] _e_14;
    assign _e_14 = __n5 + 8'd1;
    always @(posedge clk_i) begin
        if (rst_i) begin
            \\value <= 8'd0;
        end
        else begin
            \\value <= _e_14;
        end
    end
    assign output__ = __n5;
endmodule

module \\lib::build_info::stamp[7]  (
        output[31:0] output__
    );
    assign output__ = 32'd1700000000;
endmodule
"""

# The same hardware: different monomorphisation id, different `src` line, the
# alias chain shortened to one hop against a differently numbered temporary,
# declarations in another order, and the adder's temporary renumbered.
AFTER_SAME = """\
module \\lib::counter[9001]  (
        input clk_i,
        input rst_i,
        output[7:0] output__
    );
    (* src = "counter.spade:9,1" *)
    logic[7:0] _e_3;
    assign _e_3 = \\value ;
    logic[7:0] _e_77;
    reg[7:0] \\value ;
    assign _e_77 = _e_3 + 8'd1;
    always @(posedge clk_i) begin
        if (rst_i) begin
            \\value <= 8'd0;
        end
        else begin
            \\value <= _e_77;
        end
    end
    assign output__ = _e_3;
endmodule

module \\lib::build_info::stamp[7]  (
        output[31:0] output__
    );
    assign output__ = 32'd1799999999;
endmodule
"""

# A real change: the increment became 2.
AFTER_CHANGED = AFTER_SAME.replace("+ 8'd1", "+ 8'd2")

# A deliberate rename: `init_value` became `impl#3::default`.
NAMED = """\
module \\lib::init_value[5]  (
        output[7:0] output__
    );
    assign output__ = 8'd0;
endmodule
"""
RENAMED = """\
module \\lib::impl#9::default[6]  (
        output[7:0] output__
    );
    assign output__ = 8'd0;
endmodule
"""


class Canonicalisation(unittest.TestCase):
    def test_sees_through_everything_the_compiler_may_rename(self):
        self.assertEqual(
            bodies.canonical_modules(BEFORE), bodies.canonical_modules(AFTER_SAME)
        )

    def test_notices_a_changed_expression(self):
        self.assertNotEqual(
            bodies.canonical_modules(BEFORE), bodies.canonical_modules(AFTER_CHANGED)
        )

    def test_drops_build_info_whose_timestamp_always_differs(self):
        modules = bodies.canonical_modules(BEFORE)
        self.assertEqual(len(modules), 1)
        self.assertNotIn("build_info", "".join(modules))

    def test_keeps_build_info_when_asked(self):
        self.assertEqual(len(bodies.canonical_modules(BEFORE, drop_build_info=False)), 2)

    def test_notices_a_lost_module(self):
        one = bodies.canonical_modules(BEFORE + NAMED)
        self.assertNotEqual(one, bodies.canonical_modules(BEFORE))

    def test_module_names_are_part_of_the_comparison(self):
        self.assertNotEqual(
            bodies.canonical_modules(NAMED), bodies.canonical_modules(RENAMED)
        )

    def test_rename_lets_a_deliberate_rename_be_compared_body_to_body(self):
        self.assertEqual(
            bodies.canonical_modules(NAMED, {"init_value": "impl#9::default"}),
            bodies.canonical_modules(RENAMED),
        )

    def test_port_names_survive_canonicalisation(self):
        self.assertIn("input clk_i", "".join(bodies.canonical_modules(BEFORE)))


class Diff(unittest.TestCase):
    def _diff(self, before: str, after: str, **kwargs) -> tuple[int, str]:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.sv", Path(tmp) / "b.sv"
            a.write_text(before)
            b.write_text(after)
            out = io.StringIO()
            return bodies.diff(a, b, out=out, **kwargs), out.getvalue()

    def test_identical_hardware_reports_same(self):
        differing, text = self._diff(BEFORE, AFTER_SAME)
        self.assertEqual(differing, 0)
        self.assertIn("same", text)

    def test_changed_hardware_reports_the_module(self):
        differing, text = self._diff(BEFORE, AFTER_CHANGED)
        self.assertEqual(differing, 1)
        self.assertIn("DIFFER", text)
        self.assertIn("lib::counter", text)

    def test_rename_is_accepted_through_the_cli_path(self):
        differing, text = self._diff(NAMED, RENAMED, renames={"init_value": "impl#9::default"})
        self.assertEqual(differing, 0)
        self.assertIn("same", text)

    def test_missing_file_is_reported_not_crashed(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a.sv"
            a.write_text(BEFORE)
            out = io.StringIO()
            self.assertEqual(bodies.diff(a, Path(tmp) / "gone.sv", out=out), 1)
            self.assertIn("MISSING", out.getvalue())


class Cli(unittest.TestCase):
    def test_rename_without_equals_is_rejected(self):
        import sys
        from unittest.mock import patch

        with patch.object(sys, "argv", ["sv_module_bodies.py", "--rename", "nope", "x.sv"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    bodies.main()


if __name__ == "__main__":
    unittest.main()
