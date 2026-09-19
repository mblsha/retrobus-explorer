"""A failed build must never retain a previous successful programming manifest."""

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
import build_ddr
import build_probe
import build_emulator
from build_common import begin_build, publish_result


class BuildManifestTests(unittest.TestCase):
    def test_preflight_failure_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = output / "result.json"
            manifest.write_text('{"bitstream_sha256": "previous"}')
            with (
                patch("sys.argv", ["build", "--output", directory]),
                patch(
                    "check_negative_edge_timing.check",
                    side_effect=RuntimeError("preflight failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    build_ddr.main()
            self.assertFalse(manifest.exists())

    def test_publication_failure_cannot_leave_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            begin_build(output)
            with patch.object(Path, "replace", side_effect=OSError("rename failed")):
                with self.assertRaises(OSError):
                    publish_result(output, '{"checked": true}')
            self.assertFalse((output / "result.json").exists())
            self.assertFalse((output / "result.json.tmp").exists())
            publish_result(output, '{"checked": true}')
            self.assertEqual((output / "result.json").read_text(), '{"checked": true}')


class ProfileTests(unittest.TestCase):
    """The shipped bitstream's options used to survive only in a build log."""

    PROFILE = "h700-rg35xx"

    def test_the_profile_expands_to_the_qualified_options(self):
        args = build_ddr.parse_arguments(["--profile", self.PROFILE])
        self.assertTrue(args.ethernet)
        self.assertTrue(args.slow_mmc)
        self.assertTrue(args.h700_mmc)
        self.assertEqual(args.seed, 19)
        self.assertEqual(args.sd_io_clock_hz, 64_000_000)
        self.assertEqual(args.sd_tran_speed, 13_000_000)
        self.assertEqual(args.trace_capture_lba, 32985)
        self.assertFalse(args.h700_early_command)
        self.assertFalse(args.mmc_only)

    def test_the_profile_keeps_the_h700_output_directory(self):
        """The profile leaves --output alone so the transport still names the
        directory, which is where the qualified bitstream already lives."""
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("sys.argv", ["build", "--profile", self.PROFILE]),
                patch.object(build_ddr, "GATEWARE", Path(directory)),
                patch(
                    "check_negative_edge_timing.check",
                    side_effect=RuntimeError("stop"),
                ) as check,
            ):
                with self.assertRaisesRegex(RuntimeError, "stop"):
                    build_ddr.main()
        self.assertEqual(
            check.call_args.args[1].parent.name, "microsd-ddr-ethernet-h700"
        )

    def test_an_explicit_flag_overrides_the_profile(self):
        args = build_ddr.parse_arguments(
            [
                "--profile",
                self.PROFILE,
                "--seed",
                "7",
                "--sd-tran-speed",
                "15000000",
                "--output",
                "build/x",
            ]
        )
        self.assertEqual(args.seed, 7)
        self.assertEqual(args.sd_tran_speed, 15_000_000)
        self.assertEqual(args.output, Path("build/x"))
        self.assertEqual(args.sd_io_clock_hz, 64_000_000, "untouched by the override")
        self.assertTrue(args.h700_mmc)

    def test_every_profile_satisfies_the_cross_flag_rules(self):
        """A profile that needed a flag the caller had to remember to add
        would be a trap, so each one has to parse on its own."""
        for name in build_ddr.PROFILES:
            with self.subTest(profile=name):
                self.assertEqual(
                    build_ddr.parse_arguments(["--profile", name]).profile, name
                )

    def test_the_manifest_records_the_profile(self):
        recorded = build_ddr.recorded_settings(
            build_ddr.parse_arguments(["--profile", self.PROFILE])
        )
        self.assertEqual(recorded["profile"], self.PROFILE)
        self.assertEqual(recorded["sd_io_clock_hz"], 64_000_000)
        self.assertEqual(recorded["trace_capture_lba"], 32985)
        self.assertTrue(recorded["h700_mmc"])
        plain = build_ddr.recorded_settings(build_ddr.parse_arguments([]))
        self.assertIsNone(plain["profile"], "an unprofiled build says so")

    def test_an_unencodable_transfer_speed_is_refused(self):
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()) as complaint:
                build_ddr.parse_arguments(["--sd-tran-speed", "24000000"])
        self.assertIn("20000000", complaint.getvalue())
        self.assertIn("25000000", complaint.getvalue())


def previous_manifests(root, folder, profiles, suffix=""):
    manifests = [
        root / "build" / folder / (profile + suffix) / "result.json"
        for profile in profiles
    ]
    for manifest in manifests:
        manifest.parent.mkdir(parents=True)
        manifest.write_text("old success")
    return manifests


class DiagnosticManifestTests(unittest.TestCase):
    def test_compile_failure_invalidates_every_requested_profile(self):
        for builder, folder, options in (
            (build_probe, "microsd-probe", []),
            (build_emulator, "microsd-emulator", []),
            (build_emulator, "microsd-emulator", ["--one-bit"]),
        ):
            with (
                self.subTest(builder=builder.__name__, options=options),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                suffix = "-one-bit" if options else ""
                manifests = previous_manifests(root, folder, builder.PROFILES, suffix)
                with (
                    patch.object(builder, "GATEWARE", root),
                    patch("sys.argv", ["build", *options]),
                    patch.object(
                        builder.subprocess,
                        "run",
                        side_effect=RuntimeError("compile failed"),
                    ),
                ):
                    with self.assertRaisesRegex(RuntimeError, "compile failed"):
                        builder.main()
                self.assertTrue(all(not path.exists() for path in manifests))

    def test_early_profile_failure_invalidates_later_profiles(self):
        for builder, folder in (
            (build_probe, "microsd-probe"),
            (build_emulator, "microsd-emulator"),
        ):
            with (
                self.subTest(builder=builder.__name__),
                tempfile.TemporaryDirectory() as directory,
            ):
                root = Path(directory)
                manifests = previous_manifests(root, folder, builder.PROFILES)
                with (
                    patch.object(builder, "GATEWARE", root),
                    patch("sys.argv", ["build", "--toolchain", str(root / "tools")]),
                    patch.object(
                        builder.subprocess,
                        "run",
                        side_effect=[None, RuntimeError("synthesis failed")],
                    ) as run,
                ):
                    with self.assertRaisesRegex(RuntimeError, "synthesis failed"):
                        builder.main()
                self.assertEqual(
                    run.call_args.args[0][0], str((root / "tools/bin/yosys").resolve())
                )
                self.assertTrue(all(not path.exists() for path in manifests))


class PackagingTests(unittest.TestCase):
    def test_packaging_preserves_artifacts_and_rejects_corruption(self):
        import build_common
        import contextlib
        import io

        for corrupt in (False, True):
            with (
                self.subTest(corrupt=corrupt),
                tempfile.TemporaryDirectory() as directory,
            ):
                output = Path(directory)
                toolchain = output / "toolchain"
                calls = []
                environment = {"TEST": "value"}

                def run(command, **kwargs):
                    calls.append(command)
                    self.assertEqual(kwargs["cwd"], output.resolve())
                    self.assertEqual(kwargs["env"], environment)
                    self.assertTrue(kwargs["check"])
                    if len(calls) == 1:
                        kwargs["stdout"].write("00000000 00000001\n")
                    elif len(calls) == 2:
                        (output / "design.bit").write_bytes(b"bitstream")
                    else:
                        (output / "decoded.bits").write_text(
                            "bit_00000000_000_01\n"
                            if corrupt
                            else "bit_00000000_000_00\n"
                        )

                with (
                    patch.object(build_common.subprocess, "run", side_effect=run),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    if corrupt:
                        with self.assertRaisesRegex(RuntimeError, "round trip failed"):
                            build_common.pack_and_verify_bitstream(
                                toolchain, output, env=environment
                            )
                    else:
                        self.assertEqual(
                            build_common.pack_and_verify_bitstream(
                                toolchain, output, env=environment
                            ),
                            1,
                        )
                self.assertEqual(
                    [Path(command[0]).name for command in calls],
                    ["python", "xc7frames2bit", "bitread"],
                )
                self.assertEqual(calls[0][-1], "design.fasm")
                self.assertEqual(calls[1][-1], "design.bit")
                self.assertEqual(calls[2][-2:], ["decoded.bits", "design.bit"])

    def test_ddr_default_and_explicit_toolchain_reach_preflight(self):
        import build_common

        for override in (None, "/tmp/custom-openxc7"):
            with (
                self.subTest(override=override),
                tempfile.TemporaryDirectory() as directory,
            ):
                argv = ["build", "--output", directory]
                if override:
                    argv += ["--toolchain", override]
                with (
                    patch("sys.argv", argv),
                    patch(
                        "check_negative_edge_timing.check",
                        side_effect=RuntimeError("stop"),
                    ) as check,
                ):
                    with self.assertRaisesRegex(RuntimeError, "stop"):
                        build_ddr.main()
                self.assertEqual(
                    check.call_args.args[0],
                    Path(override).resolve()
                    if override
                    else build_common.DEFAULT_TOOLCHAIN.resolve(),
                )


class SdPullupTests(unittest.TestCase):
    """The H700 has no working pull-up on DAT0, and the card releases the data
    lines between the blocks of a multi-block write."""

    def test_pullups_are_off_unless_asked_for(self):
        """The qualified profiles were measured without them."""
        self.assertFalse(any("PULLTYPE" in line for line in build_ddr.sd_pin_constraints(True, False)))
        self.assertFalse(build_ddr.parse_arguments([]).sd_pullups)

    def test_pullups_go_on_the_shared_lines_and_not_on_the_clock(self):
        lines = build_ddr.sd_pin_constraints(True, True)
        pulled = {i for i, line in enumerate(lines) if "PULLTYPE PULLUP" in line}
        self.assertEqual(pulled, {0, 1, 2, 3, 7})  # DAT2, DAT3, CMD, DAT0, DAT1
        self.assertNotIn("PULLTYPE", lines[6])     # the clock

    def test_the_option_is_recorded_in_the_manifest(self):
        args = build_ddr.parse_arguments(["--profile", "h700-rg35xx", "--sd-pullups"])
        self.assertTrue(build_ddr.recorded_settings(args)["sd_pullups"])

    def test_every_pin_keeps_its_slew(self):
        for slow, word in ((True, "SLEW SLOW"), (False, "SLEW FAST")):
            for line in build_ddr.sd_pin_constraints(slow, True):
                self.assertIn(word, line)
