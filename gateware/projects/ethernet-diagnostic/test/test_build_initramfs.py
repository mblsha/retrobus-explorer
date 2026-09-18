import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "rg35xx/build_initramfs.py"
SPEC = importlib.util.spec_from_file_location("build_initramfs", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildInitramfsTests(unittest.TestCase):
    def test_an_explicit_runner_is_used_verbatim(self):
        self.assertEqual(builder.find_runner("colima nerdctl --"),
                         ["colima", "nerdctl", "--"])

    def test_the_container_builds_natively_for_the_target(self):
        """The H700 is aarch64 and the builder runs on Apple silicon, so the
        container must be arm64; anything else silently cross-builds or fails."""
        command = builder.container_command(
            ["docker"], Path("/payload"), Path("/out"), "alpine:3.20",
            "1.36.1", "abc", "initramfs.cpio.gz",
        )
        self.assertIn("--platform", command)
        self.assertEqual(command[command.index("--platform") + 1], "linux/arm64")

    def test_the_pinned_hash_and_version_reach_the_build(self):
        command = builder.container_command(
            ["docker"], Path("/payload"), Path("/out"), "alpine:3.20",
            "1.36.1", "deadbeef", "out.gz",
        )
        self.assertIn("VERSION=1.36.1", command)
        self.assertIn("EXPECTED=deadbeef", command)
        self.assertIn("OUTPUT_NAME=out.gz", command)

    def test_the_build_verifies_the_tarball_and_links_statically(self):
        """A mismatched tarball must stop the build, and the initramfs carries
        no libc, so a dynamic BusyBox would not run."""
        self.assertIn("does not match the pinned hash", builder.BUILD)
        self.assertIn("CONFIG_STATIC=y", builder.BUILD)


if __name__ == "__main__":
    unittest.main()
