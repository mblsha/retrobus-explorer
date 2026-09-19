import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rg35xx import rocknix


def manifest(directory: Path, patches: dict, config: bytes, firmware: dict) -> Path:
    path = directory / "sources.json"
    path.write_text(json.dumps({
        "repository": "ROCKNIX/distribution",
        "commit": "5eb06fab68fa67dd3808cc8d1efec6cfb1d229a0",
        "config_sha256": hashlib.sha256(config).hexdigest(),
        "patches": {name: hashlib.sha256(body).hexdigest() for name, body in patches.items()},
        "firmware": {name: hashlib.sha256(body).hexdigest() for name, body in firmware.items()},
    }))
    return path


class Tree:
    """A stand-in for the repository: a dict of path to content."""

    def __init__(self, files: dict):
        self.files, self.requested = files, []

    def __call__(self, repository, commit, path):
        self.requested.append((commit, path))
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class FetchTests(unittest.TestCase):
    def test_patches_come_from_whichever_directory_holds_them(self):
        """Twenty-three of the pinned patches are the device's and three are
        generic, and the manifest names them without saying which."""
        device, generic = rocknix.PATCH_DIRECTORIES
        tree = Tree({
            f"{device}/0001-a.patch": b"device patch",
            f"{generic}/0900-z.patch": b"generic patch",
            rocknix.CONFIG_PATH: b"CONFIG_X=y\n",
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {"0001-a.patch": b"device patch", "0900-z.patch": b"generic patch"},
                               b"CONFIG_X=y\n", {})
            written = rocknix.fetch_kernel_sources(root / "work", sources, tree)
            self.assertEqual(written, ["0001-a.patch", "0900-z.patch", "base.config"])
            self.assertEqual((root / "work/patches/0900-z.patch").read_bytes(), b"generic patch")
            self.assertEqual((root / "work/base.config").read_bytes(), b"CONFIG_X=y\n")
        self.assertTrue(all(commit.startswith("5eb06fab") for commit, _ in tree.requested))

    def test_a_file_that_changed_upstream_is_not_written(self):
        """The pin is the commit and the hash together; a branch that was
        force-pushed must not be able to change what gets built."""
        device = rocknix.PATCH_DIRECTORIES[0]
        tree = Tree({f"{device}/0001-a.patch": b"tampered", rocknix.CONFIG_PATH: b"c"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {"0001-a.patch": b"original"}, b"c", {})
            with self.assertRaisesRegex(ValueError, "does not match its recorded hash"):
                rocknix.fetch_kernel_sources(root / "work", sources, tree)
            self.assertFalse((root / "work/patches/0001-a.patch").exists())

    def test_a_patch_in_neither_directory_is_an_error_not_a_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {"0001-a.patch": b"x"}, b"c", {})
            with self.assertRaisesRegex(FileNotFoundError, "neither patch directory"):
                rocknix.fetch_kernel_sources(root / "work", sources, Tree({}))

    def test_firmware_lands_where_lib_firmware_expects_it(self):
        name = "panels/anbernic,rg35xx-plus-panel.panel"
        tree = Tree({f"{rocknix.FIRMWARE_DIRECTORY}/{name}": b"PANEL-FIRMWARE\0"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {}, b"c", {name: b"PANEL-FIRMWARE\0"})
            self.assertEqual(rocknix.fetch_firmware(root / "fw", sources, tree), [name])
            self.assertEqual((root / "fw" / name).read_bytes(), b"PANEL-FIRMWARE\0")

    def test_the_real_manifest_names_files_the_fetcher_can_address(self):
        real = json.loads(rocknix.SOURCES.read_text())
        self.assertEqual(len(real["commit"]), 40)
        self.assertIn("panels/anbernic,rg35xx-plus-panel.panel", real["firmware"])


if __name__ == "__main__":
    unittest.main()
