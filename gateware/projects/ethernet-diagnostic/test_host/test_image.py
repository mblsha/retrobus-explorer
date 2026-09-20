import gzip
import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from rg35xx import image as image_module
from rg35xx.boot_script import _script_body
from rg35xx.boot_script import build_boot_script
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.fat16 import boot_volume
from rg35xx.fat16 import mbr_partition
from rg35xx.fat16 import read_at
from rg35xx.fat16 import replace_file
from rg35xx.image import DATA_PARTITION
from rg35xx.image import EROFS_MAGIC
from rg35xx.image import EROFS_SUPERBLOCK_OFFSET
from rg35xx.image import REQUIRED_BOOT_FILES
from rg35xx.image import SPL_CHECKSUM_STAMP
from rg35xx.image import SPL_LOOP_INSTRUCTION
from rg35xx.image import SPL_OFFSET
from rg35xx.image import SYSTEM_A_PARTITION
from rg35xx.image import SYSTEM_B_PARTITION
from rg35xx.image import compress_kernel
from rg35xx.image import describe_lba
from rg35xx.image import erofs_layout
from rg35xx.image import install_bootloader
from rg35xx.image import logical_partitions
from rg35xx.image import make_erofs_image
from rg35xx.image import make_spl_entry_loop
from rg35xx.image import verify_boot_image
from test_host.boot_image import BOOT_START
from test_host.boot_image import DEBUG_START
from test_host.boot_image import boot_image_fixture
from test_host.boot_image import erofs_fixture
from test_host.boot_image import erofs_image
from test_host.boot_image import ext2_fixture
from test_host.boot_image import gzip_kernel_image


class SplTests(unittest.TestCase):
    def test_spl_entry_loop_preserves_valid_egon_checksum(self):
        image = bytearray(SPL_OFFSET + 0xA000)
        spl = memoryview(image)[SPL_OFFSET:]
        spl[0:4] = (0xEA000016).to_bytes(4, "little")
        spl[4:12] = b"eGON.BT0"
        spl[16:20] = (0xA000).to_bytes(4, "little")
        spl[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
        checksum = sum(
            word[0] for word in struct.iter_unpack("<I", spl)
        ) & 0xFFFFFFFF
        spl[12:16] = checksum.to_bytes(4, "little")

        diagnostic = make_spl_entry_loop(bytes(image))
        patched = bytearray(diagnostic[SPL_OFFSET:])
        self.assertEqual(
            int.from_bytes(patched[0x60:0x64], "little"), SPL_LOOP_INSTRUCTION
        )
        stored = int.from_bytes(patched[12:16], "little")
        patched[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
        calculated = sum(
            word[0] for word in struct.iter_unpack("<I", patched)
        ) & 0xFFFFFFFF
        self.assertEqual(stored, calculated)


class InstallBootloaderTests(unittest.TestCase):
    """The bootloader is the one part of the card the boot ROM reads before
    anything this bench wrote can check it, so the checks happen here."""

    def bootloader(self, length=1024, tail=b""):
        spl = bytearray(length)
        spl[4:12] = b"eGON.BT0"
        spl[16:20] = length.to_bytes(4, "little")
        spl[12:16] = SPL_CHECKSUM_STAMP.to_bytes(4, "little")
        checksum = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
        spl[12:16] = checksum.to_bytes(4, "little")
        return bytes(spl) + tail

    def image(self, sectors=256, first_partition=128):
        blob = bytearray(sectors * SECTOR_SIZE)
        blob[510:512] = b"\x55\xaa"
        blob[446 + 4] = 0x0E
        blob[446 + 8 : 446 + 12] = first_partition.to_bytes(4, "little")
        blob[446 + 12 : 446 + 16] = (64).to_bytes(4, "little")
        return bytes(blob)

    def test_the_bootloader_lands_at_byte_8192(self):
        bootloader = self.bootloader(tail=b"FIT" * 100)
        built = install_bootloader(self.image(), bootloader, 96)
        self.assertEqual(built[SPL_OFFSET : SPL_OFFSET + len(bootloader)], bootloader)
        self.assertEqual(len(built), len(self.image()))

    def test_a_longer_predecessor_leaves_nothing_behind(self):
        """A shorter bootloader over a longer one would leave the old tail
        where the SPL would go on reading it as part of the FIT."""
        base = bytearray(self.image())
        base[SPL_OFFSET : SPL_OFFSET + 40000] = b"\xa5" * 40000
        built = install_bootloader(bytes(base), self.bootloader(), 96)
        self.assertEqual(set(built[SPL_OFFSET + 1024 : 96 * SECTOR_SIZE]), {0})

    def test_a_bootloader_that_would_reach_the_job_sector_is_refused(self):
        """The job runner replays the sectors in front of the first partition,
        so a bootloader that grew into them would be overwritten every run."""
        with self.assertRaisesRegex(ValueError, "past the 96"):
            install_bootloader(self.image(), self.bootloader(tail=bytes(48000)), 96)

    def test_a_bootloader_that_would_reach_the_first_partition_is_refused(self):
        with self.assertRaisesRegex(ValueError, "past the 32"):
            install_bootloader(
                self.image(first_partition=32), self.bootloader(tail=bytes(48000)), 2048
            )

    def test_something_that_is_not_an_egon_spl_is_refused(self):
        with self.assertRaisesRegex(ValueError, "eGON"):
            install_bootloader(self.image(), b"\x00" * 1024, 96)

    def test_a_corrupt_checksum_is_refused(self):
        broken = bytearray(self.bootloader())
        broken[64] ^= 0xFF
        with self.assertRaisesRegex(ValueError, "checksum"):
            install_bootloader(self.image(), bytes(broken), 96)

    def test_the_result_still_verifies_as_a_boot_image(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "card.img"
            boot_image_fixture(path)
            original = verify_boot_image(path)["spl"]
            replacement = self.bootloader(length=SECTOR_SIZE, tail=b"more")
            path.write_bytes(
                install_bootloader(path.read_bytes(), replacement, BOOT_START)
            )
            report = verify_boot_image(path)
            self.assertEqual(report["spl"]["length"], original["length"])
            self.assertEqual(report["boot_files"].keys(), {"BOOT.SCR", "BOOTMARK", "KERNEL", "DTB.IMG"})


class VerifierTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(self.image)

    def test_verifier_checks_spl_boot_files_and_pristine_debug_volume(self):
        report = verify_boot_image(self.image)
        self.assertEqual(report["debug_command"], "boot-shell")
        self.assertEqual(report["spl"]["offset"], 8192)
        self.assertEqual(report["partitions"][1]["start_lba"], DEBUG_START)
        self.assertEqual(set(report["boot_files"]), set(REQUIRED_BOOT_FILES))

    def test_the_initramfs_is_no_longer_part_of_the_contract(self):
        """Nothing in the delivered boot reads INITRD: U-Boot does not load one
        and the kernel mounts the system partition directly. The file is left
        in the volume because there is no reason to spend a FAT delete on it,
        but neither its presence nor its contents are required any more."""
        self.assertNotIn("INITRD", REQUIRED_BOOT_FILES)
        corrupted = replace_file(self.image.read_bytes(), "INITRD", b"not gzip")
        self.image.write_bytes(corrupted)
        self.assertEqual(verify_boot_image(self.image)["debug_command"], "boot-shell")

    def test_verifier_rejects_a_script_without_the_length_table(self):
        """The shipped image framed BOOT.SCR this way and could never run it."""
        data = bytearray(self.image.read_bytes())
        script = build_boot_script(b"\x27\x05\x19\x56" + bytes(60), "booti a b c\n")
        text = script[72:]
        unframed = bytearray(script[:64])
        unframed[12:16] = struct.pack(">I", len(text))
        unframed[24:28] = struct.pack(">I", zlib.crc32(text) & 0xFFFFFFFF)
        unframed[4:8] = bytes(4)
        unframed[4:8] = struct.pack(">I", zlib.crc32(bytes(unframed)) & 0xFFFFFFFF)
        offset = (BOOT_START + 4) * SECTOR_SIZE
        data[offset : offset + 512] = bytes(unframed) + text.ljust(
            512 - len(unframed), b"\0"
        )
        root = (BOOT_START + 2) * SECTOR_SIZE
        data[root + 28 : root + 32] = struct.pack("<I", len(unframed) + len(text))
        self.image.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "length table"):
            verify_boot_image(self.image)

    def test_verifier_rejects_a_script_with_a_stale_payload_crc(self):
        data = bytearray(self.image.read_bytes())
        offset = (BOOT_START + 4) * SECTOR_SIZE
        data[offset + 80] ^= 0xFF
        self.image.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "uImage CRC"):
            verify_boot_image(self.image)

    def test_verifier_rejects_corrupt_spl_checksum(self):
        data = bytearray(self.image.read_bytes())
        data[SPL_OFFSET + 40] ^= 1
        self.image.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "SPL checksum mismatch"):
            verify_boot_image(self.image)

    def test_verifier_rejects_nonpristine_debug_volume(self):
        data = bytearray(self.image.read_bytes())
        debug_start = DEBUG_START * SECTOR_SIZE
        data[debug_start + SECTOR_SIZE : debug_start + 2 * SECTOR_SIZE] = (
            b"RG35DBG1\ndirection=target-to-host\nstage=1\n".ljust(SECTOR_SIZE, b"\0")
        )
        self.image.write_bytes(bytes(data))
        with self.assertRaisesRegex(ValueError, "pristine host command"):
            verify_boot_image(self.image)

    def test_verifier_rejects_a_compressed_kernel_the_script_cannot_expand(self):
        _, fat, _ = boot_volume(self.image.read_bytes())
        squeezed = gzip.compress(fat.read("KERNEL"), 9, mtime=0)
        self.image.write_bytes(
            replace_file(self.image.read_bytes(), "KERNEL", squeezed)
        )
        with self.assertRaisesRegex(ValueError, "milestone write or bare Linux"):
            verify_boot_image(self.image)


class RawReadTests(unittest.TestCase):
    """A device tree replaced to cap the card's clock changed nothing: the file
    had moved, and the script went on reading the sectors the old one lay in."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "card.img"
        self.image.write_bytes(erofs_image(self.directory.name))

    def test_a_built_image_reads_its_files_where_they_lie(self):
        verify_boot_image(self.image)

    def test_a_file_replaced_behind_the_scripts_back_is_refused(self):
        built = self.image.read_bytes()
        _, fat, _ = boot_volume(built)
        moved = replace_file(built, "DTB.IMG", fat.read("DTB.IMG") + bytes(4096))
        _, after, _ = boot_volume(moved)
        self.assertNotEqual(fat.placement("DTB.IMG")[:2], after.placement("DTB.IMG")[:2])
        self.image.write_bytes(moved)
        with self.assertRaisesRegex(ValueError, "where DTB.IMG lies now"):
            verify_boot_image(self.image)


class DescribeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(self.image)

    def test_describe_lba_names_each_region_of_the_image(self):
        """Card traces report backend LBAs; a boot is only legible once those
        map onto the SPL, filesystem metadata and named boot files."""
        self.assertEqual(describe_lba(self.image, 0), "partition table")
        self.assertEqual(describe_lba(self.image, 16), "SPL+0")
        self.assertEqual(
            describe_lba(self.image, BOOT_START + 1), "boot partition FAT table"
        )
        self.assertEqual(
            describe_lba(self.image, BOOT_START + 2), "boot partition root directory"
        )
        self.assertEqual(describe_lba(self.image, BOOT_START + 6), "KERNEL+0")
        self.assertEqual(describe_lba(self.image, DEBUG_START), "partition 2 sector 0")
        self.assertEqual(describe_lba(self.image, 9999), "beyond the image")

    def test_describe_lba_follows_the_fat_chain(self):
        """A fragmented file must report its real offset, not a contiguous
        guess from its first cluster."""
        data = bytearray(self.image.read_bytes())
        boot = BOOT_START * SECTOR_SIZE
        # Chain KERNEL's cluster 4 onward to cluster 9 instead of ending.
        data[boot + 512 + 4 * 2 : boot + 512 + 4 * 2 + 2] = (9).to_bytes(2, "little")
        data[boot + 512 + 9 * 2 : boot + 512 + 9 * 2 + 2] = b"\xff\xff"
        entry = boot + 2 * 512
        while data[entry : entry + 11] != b"KERNEL     ":
            entry += 32
        data[entry + 28 : entry + 32] = (1024).to_bytes(4, "little")
        self.image.write_bytes(bytes(data))
        self.assertEqual(describe_lba(self.image, BOOT_START + 6), "KERNEL+0")
        self.assertEqual(describe_lba(self.image, BOOT_START + 11), "KERNEL+512")


class CompressKernelTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "boot.img"
        boot_image_fixture(self.image)

    def test_compress_kernel_stores_gzip_and_leaves_the_script_alone(self):
        """The card reads about 2.6 MB/s, so the uncompressed Image dominates
        the boot. The script that expands the result is written by
        make_erofs_image, which owns it and knows the kernel's sectors."""
        before = self.image.read_bytes()
        patched = compress_kernel(before)
        _, original, _ = boot_volume(before)
        _, fat, _ = boot_volume(patched)
        stored = fat.read("KERNEL")
        self.assertEqual(stored[:2], b"\x1f\x8b")
        self.assertEqual(gzip.decompress(stored)[56:60], b"ARM\x64")
        self.assertEqual(fat.read("BOOT.SCR"), original.read("BOOT.SCR"))

    def test_compress_kernel_refuses_to_run_twice(self):
        once = compress_kernel(self.image.read_bytes())
        with self.assertRaisesRegex(ValueError, "already compressed"):
            compress_kernel(once)


class ErofsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def build(self, **kwargs):
        return erofs_image(self.directory.name, **kwargs)

    def test_layout_gives_the_slots_the_same_size(self):
        """An update stages into the inactive slot, so a slot that cannot hold
        what its partner holds makes the pair useless."""
        layout = erofs_layout(224, 64, 100)
        self.assertEqual(layout["system_a"]["sectors"], layout["system_b"]["sectors"])
        self.assertEqual(
            layout["extended_sectors"],
            sum(
                layout[name]["slice_sectors"]
                for name in ("system_a", "system_b", "data")
            ),
        )
        self.assertEqual(layout["image_sectors"], 224 + layout["extended_sectors"])

    def test_layout_leaves_the_qualified_regions_untouched(self):
        """Everything new sits behind the debug partition. The boot volume, the
        sectors the kernel is read from and the debug partition all keep the
        addresses they were qualified at."""
        layout = erofs_layout(224, 64, 100)
        self.assertEqual(layout["extended_lba"], 224)
        self.assertGreater(layout["system_a"]["start_lba"], 224)

    def test_built_image_preserves_the_original_regions_byte_for_byte(self):
        source = gzip_kernel_image(self.directory.name)
        built = make_erofs_image(
            source, erofs_fixture(), ext2_fixture(), minimum_slot_sectors=8
        )
        # The boot script is deliberately rewritten; the SPL, the kernel bytes
        # and the whole debug partition are not.
        spl = slice(SPL_OFFSET, SPL_OFFSET + SECTOR_SIZE)
        self.assertEqual(built[spl], source[spl])
        volume = slice(
            DEBUG_START * SECTOR_SIZE, (DEBUG_START + 32) * SECTOR_SIZE
        )
        self.assertEqual(built[volume], source[volume])
        self.assertGreater(len(built), len(source))

    def test_chain_is_walkable_and_names_three_partitions(self):
        built = self.build()
        with io.BytesIO(built) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        self.assertEqual(
            [entry["index"] for entry in chain],
            [SYSTEM_A_PARTITION, SYSTEM_B_PARTITION, DATA_PARTITION],
        )
        self.assertEqual(chain[0]["sectors"], chain[1]["sectors"])
        for entry in chain[:2]:
            start = entry["start_lba"] * SECTOR_SIZE
            magic = start + EROFS_SUPERBLOCK_OFFSET
            self.assertEqual(built[magic : magic + 4], EROFS_MAGIC)

    def test_link_entries_are_relative_to_the_extended_partition(self):
        """The payload entry is addressed from its own record and the link from
        the extended partition. Writing the link from the record instead leaves
        a chain that still parses and silently loses the partitions after the
        first, which is the failure this checks for."""
        built = self.build()
        with io.BytesIO(built) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
            extended = mbr_partition(mbr[478:494])
            record = read_at(
                stream, chain[0]["ebr_lba"] * SECTOR_SIZE, SECTOR_SIZE
            )
        link = mbr_partition(record[462:478])
        self.assertEqual(
            extended["start_lba"] + link["start_lba"], chain[1]["ebr_lba"]
        )

    def test_the_built_image_still_verifies(self):
        path = Path(self.directory.name) / "erofs.img"
        path.write_bytes(self.build())
        report = verify_boot_image(path)
        self.assertEqual(len(report["logical_partitions"]), 3)

    def test_verifier_rejects_slots_of_different_sizes(self):
        built = bytearray(self.build())
        with io.BytesIO(bytes(built)) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        entry = chain[1]["ebr_lba"] * SECTOR_SIZE + 446
        built[entry + 12 : entry + 16] = (chain[1]["sectors"] - 2).to_bytes(4, "little")
        path = Path(self.directory.name) / "erofs.img"
        path.write_bytes(bytes(built))
        with self.assertRaisesRegex(ValueError, "same size"):
            verify_boot_image(path)

    def test_verifier_rejects_a_root_naming_a_slot_without_a_filesystem(self):
        """A boot script can name a slot that holds nothing and still look
        complete; the kernel only finds out when it fails to mount."""
        built = bytearray(self.build())
        with io.BytesIO(bytes(built)) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        start = chain[0]["start_lba"] * SECTOR_SIZE + EROFS_SUPERBLOCK_OFFSET
        built[start : start + 4] = bytes(4)
        path = Path(self.directory.name) / "erofs.img"
        path.write_bytes(bytes(built))
        with self.assertRaisesRegex(ValueError, "not EROFS"):
            verify_boot_image(path)

    def test_describe_lba_names_the_system_and_data_regions(self):
        built = self.build()
        with io.BytesIO(built) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        path = Path(self.directory.name) / "erofs.img"
        path.write_bytes(built)
        self.assertEqual(
            describe_lba(path, chain[0]["ebr_lba"]),
            f"extended boot record for partition {SYSTEM_A_PARTITION}",
        )
        self.assertEqual(
            describe_lba(path, chain[0]["start_lba"] + 1), "system A+512"
        )
        self.assertEqual(describe_lba(path, chain[1]["start_lba"]), "system B+0")
        self.assertEqual(describe_lba(path, chain[2]["start_lba"]), "data+0")

    def test_a_payload_that_is_not_erofs_is_refused(self):
        source = gzip_kernel_image(self.directory.name)
        with self.assertRaisesRegex(ValueError, "not EROFS"):
            make_erofs_image(source, bytes(4096), ext2_fixture())
        with self.assertRaisesRegex(ValueError, "not ext2"):
            make_erofs_image(source, erofs_fixture(), bytes(4096))

    def test_the_partition_numbering_follows_the_chain(self):
        """Nothing picks these numbers: Linux numbers logical partitions from
        five, and the root argument and the data mount must agree with it."""
        self.assertEqual(
            (SYSTEM_A_PARTITION, SYSTEM_B_PARTITION, DATA_PARTITION),
            (
                image_module.FIRST_LOGICAL_PARTITION,
                image_module.FIRST_LOGICAL_PARTITION + 1,
                image_module.FIRST_LOGICAL_PARTITION + 2,
            ),
        )
        built = self.build()
        with io.BytesIO(built) as stream:
            mbr = read_at(stream, 0, SECTOR_SIZE)
            chain = logical_partitions(stream, mbr)
        script = _script_body(
            boot_volume(built)[1].read("BOOT.SCR")
        ).decode()
        self.assertIn(f"root=/dev/mmcblk0p{chain[0]['index']}", script)


if __name__ == "__main__":
    unittest.main()
