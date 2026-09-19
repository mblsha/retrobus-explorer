import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rg35xx import build_kernel as builder
from rg35xx.containers import find_runner


class SourceManifestTests(unittest.TestCase):
    """The patches are prepared out of band, so nothing but this manifest says
    the kernel that comes out is the kernel that was measured."""

    def work(self, directory, patches=(("0001-a.patch", b"one"),), config=b"cfg"):
        work = Path(directory)
        (work / "patches").mkdir()
        for name, body in patches:
            (work / "patches" / name).write_bytes(body)
        (work / "base.config").write_bytes(config)
        manifest = {
            "repository": "ROCKNIX/distribution",
            "commit": "5eb06fab68fa67dd3808cc8d1efec6cfb1d229a0",
            "config_sha256": hashlib.sha256(config).hexdigest(),
            "patches": {
                name: hashlib.sha256(body).hexdigest() for name, body in patches
            },
        }
        sources = work / "sources.json"
        sources.write_text(json.dumps(manifest))
        return work, sources

    def test_a_matching_tree_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            self.assertEqual(
                builder.verify_sources(work, sources)["commit"][:12], "5eb06fab68fa"
            )

    def test_an_altered_patch_is_refused(self):
        """A re-fetch that silently picked up a newer branch tip would produce
        a different kernel under the same name."""
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "patches/0001-a.patch").write_bytes(b"two")
            with self.assertRaisesRegex(ValueError, "differ from the recorded"):
                builder.verify_sources(work, sources)

    def test_a_missing_patch_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "patches/0001-a.patch").unlink()
            with self.assertRaisesRegex(ValueError, "1 missing"):
                builder.verify_sources(work, sources)

    def test_an_extra_patch_is_refused(self):
        """An added patch changes the kernel as surely as a removed one."""
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "patches/0002-b.patch").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "1 extra"):
                builder.verify_sources(work, sources)

    def test_an_altered_configuration_is_refused(self):
        """A trim is only meaningful relative to the configuration it trims."""
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "base.config").write_bytes(b"other")
            with self.assertRaisesRegex(ValueError, "base.config"):
                builder.verify_sources(work, sources)

    def test_the_recorded_manifest_describes_the_measured_kernel(self):
        """The manifest shipped in the repository must be internally complete:
        a pinned commit and a hash for every patch."""
        manifest = json.loads(builder.SOURCES.read_text())
        self.assertEqual(len(manifest["commit"]), 40)
        self.assertTrue(manifest["patches"])
        for name, digest in manifest["patches"].items():
            self.assertTrue(name.endswith(".patch"), name)
            self.assertEqual(len(digest), 64, name)


class KernelContainerTests(unittest.TestCase):
    def command(self, **overrides):
        arguments = dict(
            runner=["docker"], work=Path("/work"), patches=Path("/work/patches"),
            config=Path("/work"), out=Path("/work/out"), image="alpine:3.20",
        )
        arguments.update(overrides)
        return builder.container_command(**arguments)

    def test_the_container_builds_natively_for_the_target(self):
        built = self.command()
        self.assertEqual(built[built.index("--platform") + 1], "linux/arm64")

    def test_the_pinned_tarball_and_the_trim_lists_reach_the_build(self):
        built = self.command(disable=["USB_SUPPORT"], enable=["EROFS_FS"])
        self.assertIn(f"VERSION={builder.KERNEL_VERSION}", built)
        self.assertIn(f"EXPECTED={builder.KERNEL_SHA256}", built)
        self.assertIn("DISABLE_LIST=USB_SUPPORT", built)
        self.assertIn("ENABLE_LIST=EROFS_FS", built)
        self.assertIn("kernel tarball does not match the hash", builder.BUILD)

    def test_the_sources_are_mounted_where_the_build_reads_them(self):
        """The patches and the configuration are inputs the build must not be
        able to rewrite, so they are mounted read-only."""
        built = self.command()
        self.assertIn("/work/patches:/patches:ro", built)
        self.assertIn("/work:/config:ro", built)
        self.assertIn("/work/out:/out", built)

    def test_thin_lto_is_only_requested_with_the_llvm_toolchain(self):
        self.assertIn("TOOLCHAIN=clang", self.command(toolchain="clang"))
        self.assertIn("TOOLCHAIN=gcc", self.command())
        self.assertIn("LTO_CLANG_THIN", builder.BUILD)


class RunnerTests(unittest.TestCase):
    """Both builders reach the same container runtime, so it is found once."""

    def test_an_explicit_runner_is_used_verbatim(self):
        self.assertEqual(
            find_runner("colima nerdctl --"), ["colima", "nerdctl", "--"]
        )

    def test_both_builders_share_one_runner(self):
        from rg35xx import build_rootfs

        self.assertIs(builder.find_runner, find_runner)
        self.assertIs(build_rootfs.find_runner, find_runner)


if __name__ == "__main__":
    unittest.main()


class FetchOptionTests(unittest.TestCase):
    def test_fetch_populates_the_work_directory_before_anything_checks_it(self):
        """The manifest could verify sources but not produce them, so a clean
        checkout could not build the kernel it pins."""
        from unittest.mock import patch

        order = []

        def fetch(work):
            order.append("fetch")
            (work / "patches").mkdir(parents=True)
            (work / "base.config").write_text("CONFIG_X=y\n")
            return ["base.config"]

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            with (
                patch.object(builder.rocknix, "fetch_kernel_sources", side_effect=fetch),
                patch.object(builder.rocknix, "fetch_firmware", return_value=[]),
                patch.object(builder.rocknix, "verified_firmware", return_value={}),
                patch.object(builder, "find_runner", return_value=["docker"]),
                patch.object(builder, "run", side_effect=lambda command: order.append("build") or 0),
                self.assertRaises(SystemExit) as finished,
            ):
                builder.main(["--work", str(work), "--fetch", "--allow-unpinned"])
        self.assertEqual(finished.exception.code, 0)
        self.assertEqual(order, ["fetch", "build"])

    def test_an_empty_work_directory_says_how_to_fill_it(self):
        import contextlib
        import io

        complaint = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(complaint):
            with self.assertRaises(SystemExit):
                builder.main(["--work", str(Path(directory) / "empty")])
        self.assertIn("--fetch", complaint.getvalue())


class BuiltInFirmwareTests(unittest.TestCase):
    """The display did not work on this kernel until the panel's init sequence
    was compiled into it, the way ROCKNIX's shipped kernel carries it."""

    def test_the_build_no_longer_clears_the_firmware_list(self):
        """Clearing it dropped the Wi-Fi blobs, which was intended, and the
        panel firmware with them, which left the screen dark: the built-in
        driver probes before any filesystem exists and nothing retries it."""
        self.assertNotIn('EXTRA_FIRMWARE ""', builder.BUILD)
        self.assertIn('--set-str EXTRA_FIRMWARE "$EXTRA_FIRMWARE"', builder.BUILD)
        self.assertIn("--set-str EXTRA_FIRMWARE_DIR /work/firmware", builder.BUILD)

    def test_the_pinned_names_reach_the_kernel_configuration(self):
        names = ["panels/anbernic,rg35xx-plus-panel.panel", "panels/anbernic,rg35xx-plus-rev6-panel.panel"]
        command = builder.container_command(
            ["docker"], Path("/w"), Path("/w/patches"), Path("/w"), Path("/w/out"),
            "alpine:3.20", firmware=names,
        )
        self.assertIn("EXTRA_FIRMWARE=" + " ".join(names), command)

    def test_missing_firmware_stops_the_build_before_the_container_starts(self):
        import contextlib
        import io
        from unittest.mock import patch

        complaint = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(complaint):
            work = Path(directory) / "work"
            (work / "patches").mkdir(parents=True)
            (work / "base.config").write_text("x")
            with (
                patch.object(builder, "run") as run,
                self.assertRaises(SystemExit),
            ):
                builder.main(["--work", str(work), "--allow-unpinned",
                              "--firmware-dir", str(Path(directory) / "none")])
        run.assert_not_called()
        self.assertIn("is missing", complaint.getvalue())
