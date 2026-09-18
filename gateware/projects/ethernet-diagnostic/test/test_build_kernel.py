import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "rg35xx/build_kernel.py"
SPEC = importlib.util.spec_from_file_location("build_kernel", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


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


if __name__ == "__main__":
    unittest.main()
