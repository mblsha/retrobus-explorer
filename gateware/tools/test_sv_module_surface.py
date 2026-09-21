"""The surface is what the testbenches and the constraints bind to.

A compiler upgrade is allowed to rewrite the netlist. It is not allowed to
rename a `#[no_mangle]` module, reorder a top-level port list, or change how an
extern SystemVerilog block is parameterised, because a Cocotb test reaches for
`dut.<port>` by name and an ACF/XDC file binds to the top-level ports. These
tests pin down that the extractor sees exactly those things and ignores the
rest.
"""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sv_module_surface as surface


# A generated file in miniature: one no_mangle top, one mangled internal unit,
# and one extern instantiation with parameters.
GENERATED = """\
module \\std::cdc::sync2[2693]  (
        input clk_i,
        input input_i,
        output output__
    );
    `COCOTB_CODE( std::cdc::sync2[2693] )
    reg \\sync1 ;
    assign output__ = \\sync1 ;
endmodule

module main (
        input clk,
        input rst_n,
        output[7:0] led,
        input usb_rx,
        output usb_tx
    );
    logic _e_12;
    \\std::cdc::sync2[2693]  \\sync2_0 (.clk_i(\\clk ), .input_i(\\usb_rx ), .output__(_e_12));
    sync_fifo_v#(.WIDTH(32), .ENTRIES(32768)) \\sync_fifo_v_0 (.clk(\\clk ), .rst(_e_12));
    assign \\usb_tx  = _e_12;
endmodule
"""


class ModuleHeaders(unittest.TestCase):
    def test_keeps_unmangled_modules_with_their_ports(self):
        self.assertEqual(
            surface.module_headers(GENERATED),
            ["module main (input clk input rst_n output[7:0] led input usb_rx output usb_tx)"],
        )

    def test_a_mangled_name_is_an_implementation_detail(self):
        self.assertNotIn("sync2", "".join(surface.module_headers(GENERATED)))

    def test_port_order_is_part_of_the_surface(self):
        swapped = GENERATED.replace(
            "        input clk,\n        input rst_n,", "        input rst_n,\n        input clk,"
        )
        self.assertNotEqual(surface.module_headers(GENERATED), surface.module_headers(swapped))

    def test_a_port_width_is_part_of_the_surface(self):
        narrowed = GENERATED.replace("output[7:0] led", "output[3:0] led")
        self.assertNotEqual(surface.module_headers(GENERATED), surface.module_headers(narrowed))

    def test_an_unterminated_port_list_is_an_error(self):
        with self.assertRaises(ValueError):
            surface.module_headers("module main (\n        input clk\n")


class ExternalInstances(unittest.TestCase):
    def test_reports_extern_modules_with_their_parameters(self):
        self.assertEqual(
            surface.external_instances(GENERATED),
            ["sync_fifo_v#(.WIDTH(32), .ENTRIES(32768))"],
        )

    def test_a_changed_parameter_is_a_changed_surface(self):
        resized = GENERATED.replace(".ENTRIES(32768)", ".ENTRIES(4096)")
        self.assertNotEqual(
            surface.external_instances(GENERATED), surface.external_instances(resized)
        )

    def test_a_module_defined_here_is_not_reported_as_extern(self):
        self.assertNotIn("main", surface.external_instances(GENERATED))

    def test_body_keywords_are_not_mistaken_for_instances(self):
        body = (
            "module main (\n        input clk\n    );\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (clk) begin\n"
            "        end\n"
            "    end\n"
            "endmodule\n"
        )
        self.assertEqual(surface.external_instances(body), [])


class Diff(unittest.TestCase):
    def _written(self, root: Path, name: str, text: str) -> Path:
        path = root / name
        path.write_text(text)
        return path

    def test_identical_files_do_not_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._written(root, "a.sv", GENERATED)
            b = self._written(root, "b.sv", GENERATED)
            out = io.StringIO()
            self.assertEqual(surface.diff(a, b, out=out), 0)
            self.assertIn("same", out.getvalue())

    def test_a_renamed_no_mangle_module_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = self._written(root, "a.sv", GENERATED)
            b = self._written(root, "b.sv", GENERATED.replace("module main (", "module top ("))
            out = io.StringIO()
            self.assertEqual(surface.diff(a, b, out=out), 1)
            text = out.getvalue()
            self.assertIn("DIFFER", text)
            self.assertIn("-module main", text)
            self.assertIn("+module top", text)

    def test_renaming_an_internal_unit_is_not_a_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            renumbered = GENERATED.replace("[2693]", "[7001]")
            a = self._written(root, "a.sv", GENERATED)
            b = self._written(root, "b.sv", renumbered)
            out = io.StringIO()
            self.assertEqual(surface.diff(a, b, out=out), 0)

    def test_directories_are_compared_by_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before", Path(tmp) / "after"
            before.mkdir()
            after.mkdir()
            self._written(before, "p.sv", GENERATED)
            self._written(after, "p.sv", GENERATED)
            self._written(before, "gone.sv", GENERATED)
            out = io.StringIO()
            self.assertEqual(surface.diff(before, after, out=out), 1)
            self.assertIn("MISSING gone.sv", out.getvalue())


class Cli(unittest.TestCase):
    def test_printing_a_file_lists_modules_then_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spade.sv"
            path.write_text(GENERATED)
            out = io.StringIO()
            with patch.object(sys, "argv", ["sv_module_surface.py", str(path)]):
                with contextlib.redirect_stdout(out):
                    self.assertEqual(surface.main(), 0)
            self.assertEqual(
                out.getvalue().splitlines(),
                [
                    "### spade.sv",
                    "module main (input clk input rst_n output[7:0] led input usb_rx output usb_tx)",
                    "instantiates sync_fifo_v#(.WIDTH(32), .ENTRIES(32768))",
                ],
            )

    def test_diff_exits_non_zero_when_the_surface_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.sv").write_text(GENERATED)
            (root / "b.sv").write_text(GENERATED.replace("module main (", "module top ("))
            argv = ["sv_module_surface.py", "--diff", str(root / "a.sv"), str(root / "b.sv")]
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(surface.main(), 1)

    def test_no_arguments_is_a_usage_error(self):
        with patch.object(sys, "argv", ["sv_module_surface.py"]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    surface.main()


if __name__ == "__main__":
    unittest.main()
