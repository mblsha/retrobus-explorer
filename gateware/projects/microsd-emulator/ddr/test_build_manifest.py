"""A failed build must never retain a previous successful programming manifest."""

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
