import tempfile
import unittest
from pathlib import Path

from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.fat16 import boot_volume
from rg35xx.fat16 import read_at
from rg35xx.fat16 import replace_file
from test_host.boot_image import BOOT_START
from test_host.boot_image import boot_image_fixture


class ReplaceFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(self.image)

    def test_replace_file_reallocates_and_updates_both_fat_copies(self):
        """A rewritten file rarely fits the chain its directory entry points
        at, and a volume whose FAT copies disagree is what fsck repairs by
        guessing."""
        payload = bytes(range(256)) * 6  # 1536 bytes, three 512B clusters
        patched = replace_file(self.image.read_bytes(), "INITRD", payload)

        stream, fat, _ = boot_volume(patched)
        self.assertEqual(fat.read("INITRD"), payload)
        chain = [cluster for cluster, _ in fat.clusters("INITRD")]
        self.assertEqual(len(chain), 3)
        # U-Boot re-reads the FAT per cluster, so a scattered file costs far
        # more than its size; take a contiguous run when one exists.
        self.assertEqual(chain, list(range(chain[0], chain[0] + 3)))
        # Every other file must survive the reallocation untouched.
        self.assertEqual(fat.read("KERNEL")[56:60], b"ARM\x64")
        self.assertTrue(fat.read("BOOT.SCR").startswith(b"\x27\x05\x19\x56"))

        boot = read_at(stream, fat.start, SECTOR_SIZE)
        table_bytes = int.from_bytes(boot[22:24], "little") * SECTOR_SIZE
        copies = boot[16]
        tables = {
            read_at(stream, fat.fat_offset + index * table_bytes, table_bytes)
            for index in range(copies)
        }
        self.assertEqual(len(tables), 1, "FAT copies disagree")

    def test_replace_file_refuses_a_payload_that_does_not_fit(self):
        with self.assertRaisesRegex(ValueError, "clusters"):
            replace_file(self.image.read_bytes(), "INITRD", b"\0" * (1 << 20))

    def test_replace_file_rejects_an_unknown_name(self):
        with self.assertRaises(ValueError):
            replace_file(self.image.read_bytes(), "ABSENT", b"x")


class PlacementTests(unittest.TestCase):
    """A raw read states its own block count, so it assumes contiguity."""

    def test_a_contiguous_file_reports_its_first_sector_and_length(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            _, fat, _ = boot_volume(image.read_bytes())
            cluster, size = fat.files["KERNEL"]
            data_lba = fat.data_offset // SECTOR_SIZE
            sectors_per_cluster = fat.cluster_size // SECTOR_SIZE
            self.assertEqual(
                fat.placement("KERNEL"),
                (
                    data_lba + (cluster - 2) * sectors_per_cluster,
                    (size + SECTOR_SIZE - 1) // SECTOR_SIZE,
                    size,
                ),
            )

    def test_a_fragmented_file_is_refused(self):
        """A fragmented file read by sector and count would silently read the
        wrong sectors."""
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            data = bytearray(image.read_bytes())
            boot = BOOT_START * SECTOR_SIZE
            # Point KERNEL's cluster 4 at a chain that jumps to cluster 9.
            data[boot + 512 + 4 * 2 : boot + 512 + 4 * 2 + 2] = (9).to_bytes(2, "little")
            data[boot + 512 + 9 * 2 : boot + 512 + 9 * 2 + 2] = b"\xff\xff"
            entry = boot + 2 * 512
            while data[entry : entry + 11] != b"KERNEL     ":
                entry += 32
            data[entry + 28 : entry + 32] = (1024).to_bytes(4, "little")
            _, fat, _ = boot_volume(bytes(data))
            with self.assertRaisesRegex(ValueError, "fragmented"):
                fat.placement("KERNEL")


if __name__ == "__main__":
    unittest.main()
