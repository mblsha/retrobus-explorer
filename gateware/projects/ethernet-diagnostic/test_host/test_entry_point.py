import contextlib
import io
import unittest

from scripts import rg35xx


def run(argv):
    """Run the dispatcher, returning its exit status and what it printed.

    `--help` leaves argparse to raise SystemExit, so both ways a command line
    can finish are collapsed into one status here.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            status = rg35xx.main(argv)
        except SystemExit as exit_code:
            status = exit_code.code or 0
    return status, out.getvalue() + err.getvalue()


class DispatcherTests(unittest.TestCase):
    """The entry point is what the documented commands are written against, so
    a subcommand that cannot even be asked for its options is a broken doc."""

    def test_every_subcommand_can_describe_itself(self):
        for name in rg35xx.SUBCOMMANDS:
            with self.subTest(command=name):
                status, output = run([name, "--help"])
                self.assertEqual(status, 0)
                self.assertIn("usage:", output)

    def test_the_top_level_help_lists_every_subcommand(self):
        status, output = run(["--help"])
        self.assertEqual(status, 0)
        for name in rg35xx.SUBCOMMANDS:
            self.assertIn(name, output)

    def test_a_subcommand_is_described_by_the_module_that_implements_it(self):
        """The listing is generated rather than restated, so that a module
        whose purpose changes cannot keep advertising the old one."""
        from rg35xx import report

        self.assertEqual(
            rg35xx.describe("report"), report.__doc__.strip().splitlines()[0]
        )

    def test_no_arguments_prints_the_commands_rather_than_failing(self):
        status, output = run([])
        self.assertEqual(status, 0)
        self.assertIn("commands:", output)

    def test_an_unknown_command_is_refused(self):
        status, output = run(["measure"])
        self.assertEqual(status, 2)
        self.assertIn("measure", output)


if __name__ == "__main__":
    unittest.main()
