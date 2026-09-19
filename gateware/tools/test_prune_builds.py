"""A pruning tool is only as good as the things it refuses to delete."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prune_builds


def experiment(root: Path, name: str, size: int = 4096, **manifest) -> Path:
    """Write a fake finished build occupying exactly `size` bytes."""
    directory = root / name
    directory.mkdir(parents=True)
    result = json.dumps(
        {
            "bitstream_sha256": name.encode().hex().ljust(64, "0"),
            "placement_seed": 8,
            "profile": None,
            "h700_mmc": False,
            "sd_io_clock_hz": 100_000_000,
            "sd_max_clock_hz": 13_000_000,
            **manifest,
        }
    )
    (directory / "result.json").write_text(result)
    padding = size - len(result.encode())
    if padding < 0:
        raise ValueError(f"{size} bytes is smaller than {name}'s manifest")
    (directory / "design.bit").write_bytes(b"\0" * padding)
    return directory


def untouchable(root: Path) -> list[Path]:
    """Directories the tool must never remove, however it is invoked.

    The toolchain, the interpreter and the kernel trees are given a result.json
    they have no business having, so the refusal is shown to come from what the
    directory is rather than from an accident of what it contains.
    """
    directories = [
        experiment(root, name)
        for name in ("openxc7-macos", "litedram-py311", "rg35xx-kernel", "rg35xx-2025")
    ]
    plain = root / "scratch"
    plain.mkdir()
    (plain / "notes.txt").write_text("no manifest here")
    directories.append(plain)
    interrupted = root / "microsd-ddr-interrupted"
    interrupted.mkdir()
    (interrupted / "result.json").write_text("{ truncated")
    directories.append(interrupted)
    return directories


@contextlib.contextmanager
def build_tree():
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


def run(root: Path, *options):
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        code = prune_builds.main(["--build-root", str(root), *options])
    return code, printed.getvalue()


def refuse(root: Path, *options) -> str:
    complaint = io.StringIO()
    with contextlib.redirect_stderr(complaint):
        try:
            prune_builds.main(["--build-root", str(root), *options])
        except SystemExit:
            return complaint.getvalue()
    raise AssertionError("the tool ran instead of refusing")


def table(printed: str, count: int) -> dict:
    """The printed rows, by directory name."""
    rows = [line.split() for line in printed.splitlines()[1 : count + 1]]
    return {columns[1]: columns for columns in rows}


class ListingTests(unittest.TestCase):
    def test_the_table_reports_each_experiment_largest_first(self):
        with build_tree() as root:
            experiment(root, "microsd-ddr-sd", size=2048)
            experiment(
                root,
                "microsd-ddr-ethernet-h700",
                size=8192,
                placement_seed=19,
                profile="h700-rg35xx",
                h700_mmc=True,
                sd_io_clock_hz=64_000_000,
            )
            experiment(root, "microsd-ddr-ethernet", size=4096)
            code, printed = run(root, "--keep", "microsd-ddr-ethernet-h700")
        self.assertEqual(code, 0)
        rows = table(printed, 3)
        self.assertEqual(
            list(rows),
            [
                "microsd-ddr-ethernet-h700",
                "microsd-ddr-ethernet",
                "microsd-ddr-sd",
            ],
        )
        action, name, sha, seed, profile, h700, io_mhz, card_mhz, *_ = rows[
            "microsd-ddr-ethernet-h700"
        ]
        self.assertEqual(action, "keep")
        self.assertEqual(sha, "microsd-ddr-ethernet-h700".encode().hex()[:12])
        self.assertEqual(seed, "19")
        self.assertEqual(profile, "h700-rg35xx")
        self.assertEqual(h700, "yes")
        self.assertEqual(io_mhz, "64")
        self.assertEqual(card_mhz, "13")
        self.assertEqual(rows["microsd-ddr-sd"][0], "prune")
        self.assertEqual(rows["microsd-ddr-sd"][4], "-", "no profile recorded")

    def test_a_dry_run_reports_the_total_and_removes_nothing(self):
        with build_tree() as root:
            kept = experiment(root, "microsd-ddr-ethernet-h700", size=1000)
            doomed = experiment(root, "microsd-ddr-sd", size=4000)
            other = experiment(root, "microsd-ddr-ethernet", size=2000)
            code, printed = run(root, "--keep", "microsd-ddr-ethernet-h700")
            self.assertTrue(kept.exists() and doomed.exists() and other.exists())
        self.assertEqual(code, 0)
        self.assertIn("Would delete 2 of 3 experiments, 6000 bytes", printed)
        self.assertIn("Nothing was removed", printed)

    def test_keeping_everything_prunes_nothing(self):
        with build_tree() as root:
            code, printed = run(
                root, "--keep", experiment(root, "microsd-ddr-sd").name
            )
        self.assertEqual(code, 0)
        self.assertIn("Nothing to prune", printed)


class RefusalTests(unittest.TestCase):
    def test_it_will_not_run_without_keep(self):
        with build_tree() as root:
            experiment(root, "microsd-ddr-sd")
            self.assertIn("--keep", refuse(root, "--delete"))

    def test_a_mistyped_keep_name_is_refused(self):
        with build_tree() as root:
            experiment(root, "microsd-ddr-ethernet-h700")
            complaint = refuse(root, "--delete", "--keep", "microsd-ddr-ethernet-h7000")
        self.assertIn("microsd-ddr-ethernet-h7000", complaint)
        self.assertIn("names nothing", complaint)

    def test_toolchains_kernels_and_manifestless_directories_survive_deletion(self):
        """They are not bitstream experiments, so --keep does not have to
        mention them for them to be safe."""
        with build_tree() as root:
            protected = untouchable(root)
            kept = experiment(root, "microsd-ddr-ethernet-h700")
            doomed = experiment(root, "microsd-ddr-sd")
            code, printed = run(root, "--delete", "--keep", kept.name)
            for directory in protected:
                self.assertTrue(directory.exists(), f"{directory.name} was deleted")
                self.assertNotIn(directory.name, printed)
            self.assertTrue(kept.exists())
            self.assertFalse(doomed.exists())
        self.assertEqual(code, 0)

    def test_the_hard_rules_are_checked_per_directory(self):
        with build_tree() as root:
            for directory in untouchable(root):
                with self.subTest(directory=directory.name):
                    self.assertFalse(prune_builds.deletable(directory, root))
            self.assertTrue(
                prune_builds.deletable(experiment(root, "microsd-ddr-sd"), root)
            )


class DeletionTests(unittest.TestCase):
    def test_delete_frees_the_reported_bytes(self):
        with build_tree() as root:
            experiment(root, "microsd-ddr-ethernet-h700", size=1000)
            doomed = experiment(root, "microsd-ddr-sd", size=4000)
            code, printed = run(
                root, "--delete", "--keep", "microsd-ddr-ethernet-h700"
            )
            self.assertFalse(doomed.exists())
        self.assertEqual(code, 0)
        self.assertIn("Deleting 1 of 2 experiments, 4000 bytes", printed)
        self.assertIn("Freed 4000 bytes", printed)

    def test_the_rules_are_rechecked_at_deletion_time(self):
        """The listing is a snapshot. A directory that stops being a finished
        experiment between the plan and the removal must not be removed."""
        with build_tree() as root:
            smaller = experiment(root, "microsd-ddr-small", size=1000)
            experiment(root, "microsd-ddr-large", size=2000)
            kept = experiment(root, "microsd-ddr-ethernet-h700", size=500)
            removed = []

            def rmtree(path):
                removed.append(Path(path).name)
                (smaller / "result.json").unlink()

            with patch.object(prune_builds.shutil, "rmtree", side_effect=rmtree):
                code, printed = run(root, "--delete", "--keep", kept.name)
        self.assertEqual(code, 0)
        self.assertEqual(removed, ["microsd-ddr-large"], "the plan was followed blindly")
        self.assertIn("skipped microsd-ddr-small", printed)
        self.assertIn("no longer a bitstream experiment", printed)
        self.assertIn("Freed 2000 bytes", printed)


if __name__ == "__main__":
    unittest.main()
