import tempfile
import unittest
import zlib
from pathlib import Path

from rg35xx import debug_partition
from rg35xx.boot_script import GZIP_MAGIC
from rg35xx.boot_script import ZSTD_MAGIC
from rg35xx.boot_script import _kernel_load
from rg35xx.boot_script import _script_body
from rg35xx.boot_script import build_boot_script
from rg35xx.boot_script import erofs_slot_script
from rg35xx.boot_script import repair_boot_script
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.fat16 import boot_volume
from rg35xx.image import SYSTEM_A_PARTITION
from rg35xx.image import SYSTEM_B_PARTITION
from rg35xx.image import verify_boot_image
from test_host.boot_image import BOOT_START
from test_host.boot_image import DEBUG_START
from test_host.boot_image import boot_image_fixture
from test_host.boot_image import erofs_image
from test_host.boot_image import gzip_kernel_image

MILESTONE_SCRIPT = (
    "mmc write a 0x1 1\nbaredebug=/dev/mmcblk0p2\nbooti a b c\n"
)


def script_of(image: bytes) -> str:
    _, fat, _ = boot_volume(image)
    return _script_body(fat.read("BOOT.SCR")).decode()


class ScriptImageTests(unittest.TestCase):
    def test_boot_script_carries_the_legacy_length_table(self):
        header = b"\x27\x05\x19\x56" + bytes(60)
        text = "echo hello\n"
        built = build_boot_script(header, text)
        payload = built[64:]
        # U-Boot reads a length word and then skips eight bytes before running.
        self.assertEqual(int.from_bytes(payload[0:4], "big"), len(text))
        self.assertEqual(payload[4:8], bytes(4))
        self.assertEqual(payload[8:].decode(), text)
        self.assertEqual(int.from_bytes(built[12:16], "big"), len(payload))
        self.assertEqual(
            int.from_bytes(built[24:28], "big"), zlib.crc32(payload) & 0xFFFFFFFF
        )
        checked = bytearray(built[:64])
        checked[4:8] = bytes(4)
        self.assertEqual(
            int.from_bytes(built[4:8], "big"), zlib.crc32(bytes(checked)) & 0xFFFFFFFF
        )

    def test_boot_script_rejects_a_foreign_header(self):
        with self.assertRaises(ValueError):
            build_boot_script(bytes(64), "echo hello\n")


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(self.image)

    def test_repair_rewrites_boot_script_and_keeps_the_image_verifiable(self):
        original = verify_boot_image(self.image)
        repaired = repair_boot_script(self.image.read_bytes(), MILESTONE_SCRIPT)
        self.assertNotEqual(repaired, self.image.read_bytes())
        self.image.write_bytes(repaired)
        report = verify_boot_image(self.image)
        self.assertEqual(
            report["boot_files"]["BOOT.SCR"], 64 + 8 + len(MILESTONE_SCRIPT)
        )
        self.assertEqual(report["debug_command"], original["debug_command"])
        # The executable body must be exactly the requested script.
        self.assertEqual(script_of(self.image.read_bytes()), MILESTONE_SCRIPT)

    def test_repair_grows_the_script_beyond_its_original_cluster(self):
        """The EROFS script no longer fits one cluster, so the repair
        reallocates rather than refusing."""
        script = MILESTONE_SCRIPT + "# padding to force a second cluster\n" * 12
        patched = repair_boot_script(self.image.read_bytes(), script)
        _, fat, _ = boot_volume(patched)
        self.assertGreater(len(list(fat.clusters("BOOT.SCR"))), 1)
        self.assertEqual(script_of(patched), script)

    def test_repair_rejects_a_script_larger_than_the_volume(self):
        with self.assertRaisesRegex(ValueError, "clusters"):
            repair_boot_script(self.image.read_bytes(), "booti\n" * 100000)


class ErofsScriptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def script(self, **kwargs):
        image = gzip_kernel_image(self.directory.name)
        return erofs_slot_script(image, SYSTEM_A_PARTITION, **kwargs)

    def test_milestones_are_addressed_from_the_real_debug_partition(self):
        """The sector map is relative to partition 2, and the script addresses
        the card, so a remembered absolute LBA would write into whatever
        happens to live there on a differently laid out image."""
        script = self.script()
        for sector in (
            debug_partition.SCRIPT_RUNNING,
            debug_partition.KERNEL_LOADED,
            debug_partition.DEVICE_TREE_LOADED,
        ):
            self.assertIn(
                f" {DEBUG_START + sector:#x} 1\n", script,
                f"milestone {sector} is not written behind partition 2",
            )
        self.assertNotIn("0x1c0", script)

    def test_the_environment_dump_lands_in_its_own_sectors(self):
        """The board has no console, so a variable U-Boot resolves at run time
        can only be read back through the card."""
        script = self.script(export_env=True)
        expected = DEBUG_START + debug_partition.ENV_EXPORT_SECTOR
        self.assertIn("env export -t ${ramdisk_addr_r}", script)
        self.assertIn(
            f"mmc write ${{ramdisk_addr_r}} {expected:#x} "
            f"{debug_partition.ENV_EXPORT_SECTORS:#x}\n",
            script,
        )
        self.assertNotIn("env export", self.script())

    def test_the_script_loads_no_initrd(self):
        """The point of the system partition is that nothing is read before the
        kernel starts, so booti must be given a dash where the ramdisk went."""
        script = script_of(erofs_image(self.directory.name))
        self.assertIn("booti ${kernel_addr_r} - ${fdt_addr_r}", script)
        self.assertNotIn("ramdisk_addr_r}:", script)
        self.assertNotIn("INITRD", script)
        self.assertIn(f"root=/dev/mmcblk0p{SYSTEM_A_PARTITION}", script)
        self.assertIn("rootfstype=erofs", script)

    def test_the_second_slot_can_be_the_root(self):
        built = erofs_image(self.directory.name, root_partition=SYSTEM_B_PARTITION)
        self.assertIn(
            f"root=/dev/mmcblk0p{SYSTEM_B_PARTITION}", script_of(built)
        )

    def test_an_uncompressed_kernel_is_refused(self):
        image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(image)
        with self.assertRaisesRegex(ValueError, "gzip or zstd"):
            erofs_slot_script(image.read_bytes(), SYSTEM_A_PARTITION)

    def test_a_fragmented_payload_is_refused(self):
        """The script reads the kernel by sector and count, so a fragmented
        file would silently be read from the wrong sectors."""
        data = bytearray(gzip_kernel_image(self.directory.name))
        boot = BOOT_START * SECTOR_SIZE
        # Point DTB.IMG's chain at a cluster that is not the next one.
        entry = boot + 2 * 512
        while data[entry : entry + 11] != b"DTB     IMG":
            entry += 32
        first = int.from_bytes(data[entry + 26 : entry + 28], "little")
        data[boot + 512 + first * 2 : boot + 512 + first * 2 + 2] = (
            (first + 4).to_bytes(2, "little")
        )
        data[boot + 512 + (first + 4) * 2 : boot + 512 + (first + 4) * 2 + 2] = b"\xff\xff"
        data[entry + 28 : entry + 32] = (1024).to_bytes(4, "little")
        with self.assertRaisesRegex(ValueError, "fragmented"):
            erofs_slot_script(bytes(data), SYSTEM_A_PARTITION)


class KernelLoadTests(unittest.TestCase):
    """How the kernel reaches kernel_addr_r depends on its compression, and
    getting it wrong produces a boot that writes every milestone and then
    stops, with no console to say why."""

    def test_gzip_is_expanded_out_of_the_scratch_area(self):
        """unzip cannot expand in place, so the stored image is read into
        kernel_comp_addr_r and expanded out of it."""
        load = _kernel_load(GZIP_MAGIC + bytes(8), (0x1000, 0x20))
        self.assertIn("mmc read ${kernel_comp_addr_r} 0x1000 0x20", load)
        self.assertIn("unzip ${kernel_comp_addr_r} ${kernel_addr_r}", load)

    def test_zstd_is_handed_to_booti_with_the_size_it_demands(self):
        """booti decompresses into kernel_comp_addr_r and refuses to start
        unless kernel_comp_size is set too. Omitting it is what made the first
        attempt look like booti ignoring the image."""
        load = _kernel_load(ZSTD_MAGIC + bytes(8), (0x1000, 0x20))
        self.assertIn("mmc read ${kernel_addr_r} 0x1000 0x20", load)
        self.assertIn("setenv kernel_comp_size", load)
        self.assertNotIn("unzip", load)


if __name__ == "__main__":
    unittest.main()
