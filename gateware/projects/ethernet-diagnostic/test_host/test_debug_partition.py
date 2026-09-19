import unittest

from rg35xx import debug_partition
from rg35xx.debug_partition import SECTOR_SIZE
from rg35xx.debug_partition import decode_records
from rg35xx.debug_partition import encode_command


class RecordTests(unittest.TestCase):
    def test_command_is_one_host_to_target_sector(self):
        encoded = encode_command("continue")
        self.assertEqual(len(encoded), SECTOR_SIZE)
        self.assertEqual(
            decode_records(encoded),
            [{
                "sector": "0",
                "direction": "host-to-target",
                "command": "continue",
            }],
        )

    def test_decoder_keeps_sector_numbers_and_skips_unmarked_sectors(self):
        record = (
            b"RG35DBG1\ndirection=target-to-host\nmilestone=kernel-entry\n"
        ).ljust(SECTOR_SIZE, b"\0")
        data = bytes(SECTOR_SIZE) + record
        self.assertEqual(
            decode_records(data),
            [{
                "sector": "1",
                "direction": "target-to-host",
                "milestone": "kernel-entry",
            }],
        )

    def test_decoder_rejects_partial_sector(self):
        with self.assertRaisesRegex(ValueError, "whole 512-byte sectors"):
            decode_records(b"partial")

    def test_encoder_rejects_oversize_command(self):
        with self.assertRaisesRegex(ValueError, "does not fit"):
            encode_command("x" * SECTOR_SIZE)


class SectorMapTests(unittest.TestCase):
    """Three parties write this partition and nothing but the map keeps them
    apart, so the map is asserted rather than assumed."""

    def test_u_boots_milestones_never_reach_the_userspace_range(self):
        uboot = range(
            debug_partition.UBOOT_BASE,
            debug_partition.UBOOT_BASE + debug_partition.UBOOT_SECTORS,
        )
        for milestone in (
            debug_partition.SCRIPT_RUNNING,
            debug_partition.KERNEL_LOADED,
            debug_partition.DEVICE_TREE_LOADED,
        ):
            self.assertIn(milestone, uboot)
        self.assertGreater(debug_partition.USERSPACE_BASE, max(uboot))

    def test_the_environment_dump_sits_between_the_two_milestone_ranges(self):
        """It is eight sectors of text, so it has to fit in the gap rather than
        run into either set of milestones."""
        last_uboot = debug_partition.UBOOT_BASE + debug_partition.UBOOT_SECTORS - 1
        self.assertGreater(debug_partition.ENV_EXPORT_SECTOR, last_uboot)
        self.assertLessEqual(
            debug_partition.ENV_EXPORT_SECTOR + debug_partition.ENV_EXPORT_SECTORS,
            debug_partition.USERSPACE_BASE,
        )

    def test_the_map_covers_the_sectors_a_host_reads_back(self):
        self.assertEqual(
            debug_partition.DEBUG_SECTORS,
            debug_partition.USERSPACE_BASE + debug_partition.USERSPACE_SECTORS,
        )

    def test_an_absolute_lba_is_the_partition_start_plus_the_sector(self):
        """The generated boot script addresses the card, not the partition, so
        this translation is what keeps a milestone inside the volume that has
        no filesystem to damage."""
        self.assertEqual(
            debug_partition.absolute_lba(114688, debug_partition.KERNEL_LOADED),
            0x1C003,
        )

    def test_a_sector_outside_the_map_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside the debug partition"):
            debug_partition.absolute_lba(114688, debug_partition.DEBUG_SECTORS)


if __name__ == "__main__":
    unittest.main()
