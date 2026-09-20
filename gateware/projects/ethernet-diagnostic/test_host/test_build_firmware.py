import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rg35xx import build_firmware as builder
from rg35xx.containers import find_runner


def _manifest(directory: Path, files) -> Path:
    recorded = {
        "repository": "ROCKNIX/distribution",
        "commit": "7f1b3abece2c7d263cebd16b5a2ba4268d6ddaa5",
        "tarballs": {
            "u-boot": {
                "version": "v2026.01",
                "url": "https://example.invalid/u-boot.tar.gz",
                "directory": "u-boot-2026.01",
                "sha256": "u" * 64,
            },
            "tf-a": {
                "version": "v2.12.0",
                "url": "https://example.invalid/tf-a.tar.gz",
                "directory": "arm-trusted-firmware-2.12.0",
                "sha256": "t" * 64,
            },
        },
        "rocknix_files": {
            name: {"path": f"projects/{name}", "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in files
        },
        "defconfig": "a_defconfig",
        "tf_a_platform": "sun50i_h616",
        "our_patches": {
            "0001-suspend.patch": {"applies_to": "tf-a", "suspend": ["wfi", "wfi32", "sr"]},
            "0002-dram.patch": {"applies_to": "tf-a", "suspend": ["sr"]},
        },
    }
    sources = directory / "sources.json"
    sources.write_text(json.dumps(recorded))
    return sources


class SourceManifestTests(unittest.TestCase):
    """Two cards whose firmware came from different sources cannot be
    compared, so the inputs are pinned and a mismatch stops the build."""

    FILES = (("patches/0001-dram.patch", b"dram"), ("configs/a_defconfig", b"cfg"))

    def work(self, directory, files=FILES):
        work = Path(directory)
        for name, body in files:
            target = work / "rocknix" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        return work, _manifest(work, files)

    def test_a_matching_tree_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            self.assertEqual(
                builder.verify_sources(work, sources)["commit"][:12], "7f1b3abece2c"
            )

    def test_an_altered_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "rocknix/configs/a_defconfig").write_bytes(b"other")
            with self.assertRaisesRegex(ValueError, "differ from the manifest"):
                builder.verify_sources(work, sources)

    def test_a_missing_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "rocknix/patches/0001-dram.patch").unlink()
            with self.assertRaisesRegex(ValueError, "1 missing"):
                builder.verify_sources(work, sources)

    def test_an_extra_file_is_refused(self):
        """An added patch changes the bootloader as surely as a removed one."""
        with tempfile.TemporaryDirectory() as directory:
            work, sources = self.work(directory)
            (work / "rocknix/patches/0002-extra.patch").write_bytes(b"extra")
            with self.assertRaisesRegex(ValueError, "1 extra"):
                builder.verify_sources(work, sources)

    def test_a_fetch_writes_only_what_the_manifest_describes(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            sources = _manifest(work, self.FILES)
            bodies = dict(self.FILES)

            def download(repository, commit, path):
                return bodies[path.removeprefix("projects/")]

            written = builder.fetch_sources(work, sources, download=download)
            self.assertEqual(written, sorted(bodies))
            builder.verify_sources(work, sources)

    def test_a_fetch_that_does_not_match_writes_nothing_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            sources = _manifest(work, self.FILES)
            with self.assertRaisesRegex(ValueError, "does not match its recorded hash"):
                builder.fetch_sources(work, sources, download=lambda *_: b"wrong")

    def test_the_recorded_manifest_is_internally_complete(self):
        recorded = builder.manifest()
        self.assertEqual(len(recorded["commit"]), 40)
        for kind in ("u-boot", "tf-a"):
            self.assertEqual(len(recorded["tarballs"][kind]["sha256"]), 64)
        self.assertTrue(recorded["rocknix_files"])
        for name, entry in recorded["rocknix_files"].items():
            self.assertEqual(len(entry["sha256"]), 64, name)
            self.assertTrue(entry["path"].endswith(name.split("/")[-1]), name)

    def test_every_patch_the_manifest_names_is_in_the_repository(self):
        for name in builder.manifest()["our_patches"]:
            self.assertTrue((builder.PATCHES / name).is_file(), name)


class SuspendModeTests(unittest.TestCase):
    """The point of the option is that the parity build is the upstream one."""

    def test_the_parity_build_applies_nothing_of_ours(self):
        self.assertEqual(builder.patches_for("none"), [])
        self.assertEqual(builder.SUSPEND_MODES["none"], {})

    def test_the_suspend_builds_apply_our_patch_and_ask_for_the_feature(self):
        self.assertEqual(
            builder.patches_for("wfi"),
            ["0001-allwinner-h616-minimal-psci-system-suspend.patch"],
        )
        self.assertEqual(
            builder.SUSPEND_MODES["wfi"], {"SUNXI_SYSTEM_SUSPEND": "1"}
        )
        self.assertEqual(
            builder.SUSPEND_MODES["wfi32"],
            {"SUNXI_SYSTEM_SUSPEND": "1", "SUNXI_SUSPEND_CPU_32K": "1"},
        )

    def test_the_self_refresh_builds_add_the_stub_patch_on_top(self):
        """The stub patch applies over the DRAM-less one, so the two earlier
        bootloaders stay the bootloaders they were measured as."""
        for mode in ("sr", "sr-gate", "sr-pll"):
            self.assertEqual(
                builder.patches_for(mode),
                [
                    "0001-allwinner-h616-minimal-psci-system-suspend.patch",
                    "0002-allwinner-h616-dram-self-refresh-from-an-sram-stub.patch",
                ],
                mode,
            )

    def test_each_rung_of_the_dram_ladder_asks_for_its_own_level(self):
        """One patch, three builds: the level is the whole difference between
        a card that only self-refreshes and one that also stops PLL_DDR0."""
        levels = {
            mode: builder.SUSPEND_MODES[mode]["SUNXI_SUSPEND_DRAM_LEVEL"]
            for mode in ("sr", "sr-gate", "sr-pll")
        }
        self.assertEqual(levels, {"sr": "1", "sr-gate": "2", "sr-pll": "3"})
        for mode, options in builder.SUSPEND_MODES.items():
            if mode.startswith("sr"):
                self.assertEqual(options["SUNXI_SYSTEM_SUSPEND"], "1", mode)
            else:
                self.assertNotIn("SUNXI_SUSPEND_DRAM_LEVEL", options, mode)

    def test_an_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            builder.patches_for("deep")


class FirmwareContainerTests(unittest.TestCase):
    def command(self, **overrides):
        arguments = dict(
            runner=["docker"], work=Path("/work"), patches=Path("/repo/firmware"),
            out=Path("/work/none"), image="alpine:3.20",
        )
        arguments.update(overrides)
        return builder.container_command(**arguments)

    def test_the_container_builds_natively_for_the_target(self):
        built = self.command()
        self.assertEqual(built[built.index("--platform") + 1], "linux/arm64")

    def test_our_patches_are_an_input_the_build_cannot_rewrite(self):
        built = self.command()
        self.assertIn("/repo/firmware:/patches:ro", built)
        self.assertIn("/work:/work", built)
        self.assertIn("/work/none:/out", built)

    def test_both_tarballs_reach_the_build_with_their_hashes(self):
        built = self.command()
        recorded = builder.manifest()
        self.assertIn(f"TFA_SHA256={recorded['tarballs']['tf-a']['sha256']}", built)
        self.assertIn(f"UBOOT_SHA256={recorded['tarballs']['u-boot']['sha256']}", built)
        self.assertIn("does not match the pinned hash", builder.BUILD)

    def test_the_mode_decides_the_patches_and_the_make_options(self):
        self.assertIn("TFA_PATCHES=", self.command(mode="none"))
        self.assertIn("TFA_OPTIONS=", self.command(mode="none"))
        self.assertIn(
            "TFA_PATCHES=0001-allwinner-h616-minimal-psci-system-suspend.patch",
            self.command(mode="wfi"),
        )
        self.assertIn("TFA_OPTIONS=SUNXI_SYSTEM_SUSPEND=1", self.command(mode="wfi"))

    def test_the_native_compiler_is_named_rather_than_left_to_the_default(self):
        """TF-A reads an empty CROSS_COMPILE as a request for the
        aarch64-none-elf- prefix, which does not exist in this container."""
        self.assertIn("CC=gcc", builder.BUILD)

    def test_the_build_is_dated_from_the_manifest_rather_than_from_the_clock(self):
        """U-Boot stamps its version string and its FIT with the build time, so
        two builds of the same sources would otherwise never match."""
        built = self.command()
        self.assertIn(f"SOURCE_DATE_EPOCH={builder.SOURCE_DATE_EPOCH}", built)
        self.assertIn("BUILD_MESSAGE_TIMESTAMP", builder.BUILD)

    def test_the_firmware_builder_shares_the_one_runner(self):
        self.assertIs(builder.find_runner, find_runner)


class EntryPointTests(unittest.TestCase):
    def test_an_unfetched_work_directory_says_how_to_fill_it(self):
        complaint = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(complaint):
            with self.assertRaises(SystemExit):
                builder.main(["--work", str(Path(directory) / "empty")])
        self.assertIn("--fetch", complaint.getvalue())

    def test_a_fetch_happens_before_anything_checks_the_sources(self):
        order = []

        def fetch(work):
            order.append("fetch")
            return []

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            with (
                patch.object(builder, "fetch_sources", side_effect=fetch),
                patch.object(builder, "verify_sources", side_effect=lambda w: order.append("verify")),
                patch.object(builder, "find_runner", return_value=["docker"]),
                patch.object(builder, "run", side_effect=lambda command: order.append("build") or 1),
            ):
                self.assertEqual(builder.main(["--work", str(work), "--fetch"]), 1)
        self.assertEqual(order, ["fetch", "verify", "build"])

    def test_each_mode_gets_its_own_output_directory(self):
        seen = {}

        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            with (
                patch.object(builder, "verify_sources", return_value={}),
                patch.object(builder, "find_runner", return_value=["docker"]),
                patch.object(builder, "container_command",
                             side_effect=lambda *a, **k: seen.update(k) or ["true"]),
                patch.object(builder, "run", return_value=1),
            ):
                builder.main(["--work", str(work), "--suspend", "wfi"])
            self.assertTrue((work.resolve() / "wfi").is_dir())
        self.assertEqual(seen["mode"], "wfi")


if __name__ == "__main__":
    unittest.main()
