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

    def names(self, repository, commit, directory):
        self.requested.append((commit, directory))
        return {path.rsplit("/", 1)[1] for path in self.files if path.rsplit("/", 1)[0] == directory}


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
            written = rocknix.fetch_kernel_sources(root / "work", sources, tree, tree.names)
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
                rocknix.fetch_kernel_sources(root / "work", sources, tree, tree.names)
            self.assertFalse((root / "work/patches/0001-a.patch").exists())

    def test_a_patch_in_neither_directory_is_an_error_not_a_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {"0001-a.patch": b"x"}, b"c", {})
            with self.assertRaisesRegex(FileNotFoundError, "neither patch directory"):
                rocknix.fetch_kernel_sources(root / "work", sources, Tree({}), Tree({}).names)

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


class QuotaTests(unittest.TestCase):
    def test_no_request_is_spent_on_a_file_that_is_not_there(self):
        """An anonymous address gets sixty requests an hour and a 404 costs one,
        so asking for every patch in both directories ran the quota out."""
        device, generic = rocknix.PATCH_DIRECTORIES
        tree = Tree({
            f"{device}/0001-a.patch": b"a",
            f"{generic}/0900-z.patch": b"z",
            rocknix.CONFIG_PATH: b"c",
        })
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {"0001-a.patch": b"a", "0900-z.patch": b"z"}, b"c", {})
            rocknix.fetch_kernel_sources(root / "work", sources, tree, tree.names)
        # two listings, two patches, one configuration: nothing asked for twice
        self.assertEqual(len(tree.requested), 5)

    def test_gh_is_preferred_because_it_is_authenticated(self):
        from unittest.mock import patch

        class Done:
            returncode, stdout, stderr = 0, b'{"content": "aGk="}', b""

        with (
            patch.object(rocknix.shutil, "which", return_value="/opt/homebrew/bin/gh"),
            patch.object(rocknix.subprocess, "run", return_value=Done()) as run,
        ):
            self.assertEqual(rocknix.download("o/r", "c" * 40, "a/b.patch"), b"hi")
        self.assertEqual(run.call_args.args[0][:2], ["gh", "api"])


class PinnedFirmwareTests(unittest.TestCase):
    """A dark screen says nothing about why it is dark, so the panel firmware is
    checked before it is compiled into a kernel rather than discovered on one."""

    def test_the_panel_firmware_is_pinned_like_the_kernel_sources(self):
        pinned = json.loads(rocknix.SOURCES.read_text())["firmware"]
        self.assertIn("panels/anbernic,rg35xx-plus-panel.panel", pinned)
        for name, digest in pinned.items():
            self.assertEqual(len(digest), 64, name)

    def test_altered_firmware_is_refused(self):
        """The wrong file drives one panel with another panel's register writes."""
        name = "panels/x.panel"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {}, b"c", {name: b"PANEL-FIRMWARE\0good"})
            (root / "fw/panels").mkdir(parents=True)
            (root / "fw" / name).write_bytes(b"PANEL-FIRMWARE\0evil")
            with self.assertRaisesRegex(ValueError, "does not match the pinned hash"):
                rocknix.verified_firmware(root / "fw", sources)

    def test_missing_firmware_is_refused_and_says_how_to_get_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = manifest(root, {}, b"c", {"panels/x.panel": b"x"})
            with self.assertRaisesRegex(ValueError, "is missing.*--fetch"):
                rocknix.verified_firmware(root / "fw", sources)
