import importlib.util
import struct
import zlib
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts/rg35xx_boot_debug.py"
SPEC = importlib.util.spec_from_file_location("rg35xx_boot_debug", SCRIPT)
debug = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(debug)


def boot_image_fixture(path: Path) -> None:
    image = bytearray(256 * debug.SECTOR_SIZE)
    image[510:512] = b"\x55\xaa"

    def partition(index, boot, kind, start, sectors):
        offset = 446 + index * 16
        image[offset] = boot
        image[offset + 4] = kind
        image[offset + 8 : offset + 12] = start.to_bytes(4, "little")
        image[offset + 12 : offset + 16] = sectors.to_bytes(4, "little")

    partition(0, 0x80, 0x0E, 128, 64)
    partition(1, 0, 0x83, 192, 32)

    spl = bytearray(debug.SECTOR_SIZE)
    spl[4:12] = b"eGON.BT0"
    spl[16:20] = len(spl).to_bytes(4, "little")
    spl[12:16] = debug.SPL_CHECKSUM_STAMP.to_bytes(4, "little")
    checksum = sum(word[0] for word in struct.iter_unpack("<I", spl)) & 0xFFFFFFFF
    spl[12:16] = checksum.to_bytes(4, "little")
    image[debug.SPL_OFFSET : debug.SPL_OFFSET + len(spl)] = spl

    boot_start = 128 * debug.SECTOR_SIZE
    boot = memoryview(image)[boot_start : boot_start + 64 * debug.SECTOR_SIZE]
    boot[11:13] = (512).to_bytes(2, "little")
    boot[13] = 1
    boot[14:16] = (1).to_bytes(2, "little")
    boot[16] = 1
    boot[17:19] = (32).to_bytes(2, "little")
    boot[19:21] = (64).to_bytes(2, "little")
    boot[21] = 0xF8
    boot[22:24] = (1).to_bytes(2, "little")
    boot[510:512] = b"\x55\xaa"
    boot[512:516] = b"\xf8\xff\xff\xff"

    files = {
        b"BOOT    SCR": b"\x27\x05\x19\x56" + bytes(60)
        + b"mmc write x 0x1c001 1\0baredebug=/dev/mmcblk0p2\0booti x y z\0",
        b"BOOTMARK   ": (
            b"RG35DBG1\ndirection=target-to-host\nstage=0\ndetail=uboot-loaded-fat\n"
        ).ljust(512, b"\0"),
        b"KERNEL     ": bytes(56) + b"ARM\x64" + bytes(20),
        b"INITRD     ": b"\x1f\x8b" + bytes(30),
        b"DTB     IMG": b"\xd0\x0d\xfe\xed" + bytes(28),
    }
    root_offset = 2 * 512
    data_offset = 4 * 512
    for index, (name, payload) in enumerate(files.items()):
        cluster = index + 2
        entry = root_offset + index * 32
        boot[entry : entry + 11] = name
        boot[entry + 11] = 0x20
        boot[entry + 26 : entry + 28] = cluster.to_bytes(2, "little")
        boot[entry + 28 : entry + 32] = len(payload).to_bytes(4, "little")
        boot[512 + cluster * 2 : 514 + cluster * 2] = b"\xff\xff"
        offset = data_offset + (cluster - 2) * 512
        boot[offset : offset + len(payload)] = payload

    debug_start = 192 * debug.SECTOR_SIZE
    image[debug_start : debug_start + debug.SECTOR_SIZE] = debug.encode_command(
        "boot-shell"
    )
    path.write_bytes(image)


class BootDebugTests(unittest.TestCase):
    def test_spl_entry_loop_preserves_valid_egon_checksum(self):
        image = bytearray(debug.SPL_OFFSET + 0xA000)
        spl = memoryview(image)[debug.SPL_OFFSET :]
        spl[0:4] = (0xEA000016).to_bytes(4, "little")
        spl[4:12] = b"eGON.BT0"
        spl[16:20] = (0xA000).to_bytes(4, "little")
        spl[12:16] = debug.SPL_CHECKSUM_STAMP.to_bytes(4, "little")
        checksum = sum(
            word[0] for word in struct.iter_unpack("<I", spl)
        ) & 0xFFFFFFFF
        spl[12:16] = checksum.to_bytes(4, "little")

        diagnostic = debug.make_spl_entry_loop(bytes(image))
        patched = bytearray(diagnostic[debug.SPL_OFFSET :])
        self.assertEqual(
            int.from_bytes(patched[0x60:0x64], "little"),
            debug.SPL_LOOP_INSTRUCTION,
        )
        stored = int.from_bytes(patched[12:16], "little")
        patched[12:16] = debug.SPL_CHECKSUM_STAMP.to_bytes(4, "little")
        calculated = sum(
            word[0] for word in struct.iter_unpack("<I", patched)
        ) & 0xFFFFFFFF
        self.assertEqual(stored, calculated)

    def test_command_is_one_host_to_target_sector(self):
        encoded = debug.encode_command("continue")
        self.assertEqual(len(encoded), debug.SECTOR_SIZE)
        self.assertEqual(
            debug.decode_records(encoded),
            [{
                "sector": "0",
                "direction": "host-to-target",
                "command": "continue",
            }],
        )

    def test_decoder_keeps_sector_numbers_and_skips_unmarked_sectors(self):
        record = (
            b"RG35DBG1\ndirection=target-to-host\nmilestone=kernel-entry\n"
        ).ljust(debug.SECTOR_SIZE, b"\0")
        data = bytes(debug.SECTOR_SIZE) + record
        self.assertEqual(
            debug.decode_records(data),
            [{
                "sector": "1",
                "direction": "target-to-host",
                "milestone": "kernel-entry",
            }],
        )

    def test_decoder_rejects_partial_sector(self):
        with self.assertRaisesRegex(ValueError, "whole 512-byte sectors"):
            debug.decode_records(b"partial")

    def test_encoder_rejects_oversize_command(self):
        with self.assertRaisesRegex(ValueError, "does not fit"):
            debug.encode_command("x" * debug.SECTOR_SIZE)

    def test_verifier_checks_spl_boot_files_and_pristine_debug_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            report = debug.verify_boot_image(image)
            self.assertEqual(report["debug_command"], "boot-shell")
            self.assertEqual(report["spl"]["offset"], 8192)
            self.assertEqual(report["partitions"][1]["start_lba"], 192)
            self.assertEqual(set(report["boot_files"]), set(debug.REQUIRED_BOOT_FILES))

    def test_boot_script_carries_the_legacy_length_table(self):
        header = b"\x27\x05\x19\x56" + bytes(60)
        text = "echo hello\n"
        built = debug.build_boot_script(header, text)
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
            debug.build_boot_script(bytes(64))

    def test_repair_rewrites_boot_script_and_keeps_the_image_verifiable(self):
        script = "mmc write a 0x1c001 1\nbaredebug=/dev/mmcblk0p2\nbooti a b c\n"
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            original = debug.verify_boot_image(image)
            repaired = debug.repair_boot_script(image.read_bytes(), script)
            self.assertNotEqual(repaired, image.read_bytes())
            image.write_bytes(repaired)
            report = debug.verify_boot_image(image)
            self.assertNotEqual(
                report["boot_files"]["BOOT.SCR"], original["boot_files"]["BOOT.SCR"]
            )
            self.assertEqual(report["boot_files"]["BOOT.SCR"], 64 + 8 + len(script))
            self.assertEqual(report["debug_command"], original["debug_command"])

    def test_repair_rejects_a_script_that_outgrows_its_cluster(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            with self.assertRaises(ValueError):
                debug.repair_boot_script(image.read_bytes(), "booti\n" * 200)

    def test_verifier_rejects_corrupt_spl_checksum(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            data = bytearray(image.read_bytes())
            data[debug.SPL_OFFSET + 40] ^= 1
            image.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "SPL checksum mismatch"):
                debug.verify_boot_image(image)

    def test_verifier_rejects_nonpristine_debug_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "boot.img"
            boot_image_fixture(image)
            data = bytearray(image.read_bytes())
            debug_start = 192 * debug.SECTOR_SIZE
            data[debug_start + debug.SECTOR_SIZE : debug_start + 2 * debug.SECTOR_SIZE] = (
                b"RG35DBG1\ndirection=target-to-host\nstage=1\n".ljust(
                    debug.SECTOR_SIZE, b"\0"
                )
            )
            image.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "pristine host command"):
                debug.verify_boot_image(image)


if __name__ == "__main__":
    unittest.main()
