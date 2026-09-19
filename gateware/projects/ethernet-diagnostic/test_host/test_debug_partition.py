import hashlib
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

    def test_a_sector_outside_the_partition_is_refused(self):
        with self.assertRaisesRegex(ValueError, "outside the debug partition"):
            debug_partition.absolute_lba(114688, debug_partition.PARTITION_SECTORS)

    def test_the_job_exchange_clears_the_boot_records_and_stays_inside(self):
        """The runner writes results while U-Boot's and init's records from the
        same boot are still wanted, and both are in the same partition."""
        regions = [
            (debug_partition.JOB_SECTOR, debug_partition.JOB_SECTORS),
            (debug_partition.RESULT_SECTOR, debug_partition.RESULT_SECTORS),
            (debug_partition.SCRATCH_SECTOR, debug_partition.SCRATCH_SECTORS),
        ]
        for start, length in regions:
            self.assertGreaterEqual(start, debug_partition.DEBUG_SECTORS)
            self.assertLessEqual(start + length, debug_partition.PARTITION_SECTORS)
        for (start, length), (following, _) in zip(regions, regions[1:]):
            self.assertLessEqual(start + length, following)
        self.assertIn(
            debug_partition.SLEEP_MARK_SECTOR,
            range(
                debug_partition.SCRATCH_SECTOR,
                debug_partition.SCRATCH_SECTOR + debug_partition.SCRATCH_SECTORS,
            ),
        )
        self.assertNotEqual(
            debug_partition.SLEEP_MARK_SECTOR, debug_partition.CARD_CHECK_SECTOR
        )


class JobRecordTests(unittest.TestCase):
    """A job and its result cross between a Python host and a BusyBox shell
    through raw sectors, so both ends of the format are pinned here."""

    def test_a_job_round_trips_through_whole_sectors(self):
        script = "echo hello\nexit 3\n"
        encoded = debug_partition.encode_job(7, script, "phase0")
        self.assertEqual(len(encoded) % SECTOR_SIZE, 0)
        self.assertEqual(len(encoded), 2 * SECTOR_SIZE)
        self.assertEqual(
            debug_partition.decode_job(encoded),
            {"sequence": 7, "name": "phase0", "script": script},
        )

    def test_the_header_names_the_length_and_the_digest_the_target_checks(self):
        encoded = debug_partition.encode_job(1, "echo hi\n")
        fields = decode_records(encoded[:SECTOR_SIZE])[0]
        self.assertEqual(fields["kind"], "job")
        self.assertEqual(fields["script_bytes"], "8")
        self.assertEqual(
            fields["script_md5"], hashlib.md5(b"echo hi\n").hexdigest()
        )

    def test_a_job_caught_half_written_is_not_a_job(self):
        """The host writes this region sector by sector while the runner reads
        it on its own schedule. Without the digest the runner would sooner or
        later run the first half of one script and the second half of another."""
        encoded = bytearray(debug_partition.encode_job(1, "echo one\n" * 60))
        encoded[SECTOR_SIZE:] = b"\0" * (len(encoded) - SECTOR_SIZE)
        self.assertIsNone(debug_partition.decode_job(bytes(encoded)))

    def test_an_empty_region_holds_no_job_and_no_result(self):
        self.assertIsNone(debug_partition.decode_job(bytes(2 * SECTOR_SIZE)))
        self.assertIsNone(debug_partition.decode_result(bytes(2 * SECTOR_SIZE)))

    def test_a_script_too_long_for_the_region_is_refused_before_the_bench(self):
        with self.assertRaisesRegex(ValueError, "the region holds"):
            debug_partition.encode_job(
                1, "x" * (debug_partition.JOB_SCRIPT_BYTES + 1)
            )

    def test_a_result_is_bounded_by_its_byte_count_not_by_its_padding(self):
        """A short result written over a long one leaves the tail of the long
        one behind it; reading to the padding would report the two together."""
        region = bytearray(
            debug_partition.encode_result({"sequence": "1"}, "the long previous one")
        )
        short = debug_partition.encode_result(
            {"sequence": "2", "status": "done", "exit": "0"}, "short"
        )
        region[: len(short)] = short
        decoded = debug_partition.decode_result(bytes(region))
        self.assertEqual(decoded["output"], "short")
        self.assertEqual(decoded["sequence"], 2)
        self.assertEqual(decoded["exit"], 0)
        self.assertEqual(decoded["truncated"], 0)

    def test_output_larger_than_the_region_is_cut_and_says_so(self):
        decoded = debug_partition.decode_result(
            debug_partition.encode_result(
                {"sequence": "1"}, "x" * (debug_partition.RESULT_OUTPUT_BYTES + 10)
            )
        )
        self.assertEqual(decoded["truncated"], 1)
        self.assertEqual(len(decoded["output"]), debug_partition.RESULT_OUTPUT_BYTES)


if __name__ == "__main__":
    unittest.main()



class KernelLogTests(unittest.TestCase):
    def test_the_log_page_is_read_back_without_its_padding(self):
        dump = bytearray(b"\xff" * debug_partition.DEBUG_SECTORS * debug_partition.SECTOR_SIZE)
        text = b"[    1.02] panel-mipi spi0.0: firmware loaded\n"
        start = debug_partition.KERNEL_LOG_SECTOR * debug_partition.SECTOR_SIZE
        dump[start : start + len(text)] = text
        dump[start + len(text) : start + 512] = bytes(512 - len(text))
        self.assertEqual(debug_partition.kernel_log(bytes(dump)), text.decode())

    def test_milestones_and_the_log_share_the_range_without_overlapping(self):
        self.assertEqual(
            debug_partition.USERSPACE_BASE + debug_partition.USERSPACE_STAGES,
            debug_partition.KERNEL_LOG_SECTOR,
        )
