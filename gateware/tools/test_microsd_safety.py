"""Operational checks must work identically under normal Python and python -O."""

import contextlib
import io
import tempfile
import os
import stat
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import patch

import microsd_verify_linux_rw as rw
import microsd_host as host_tools


class TargetSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        host = self.root / "devices/2a310000.mmc/mmc_host/mmc1"
        self.card = host / "mmc1:0001"
        self.card.mkdir(parents=True)
        (self.card / "name").write_text("SPADE")
        (self.card / "cid").write_text(rw.CID)
        alias = self.root / "sys/class/mmc_host/mmc1"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(host)
        self.disk = self.root / "sys/class/block/mmcblk1"
        self.disk.mkdir(parents=True)
        (self.disk / "device").symlink_to(self.card)
        (self.disk / "ro").write_text("0")
        (self.disk / "size").write_text(str((256 << 20) // 512))
        (self.disk / "holders").mkdir()
        (self.disk / "dev").write_text("179:8")
        self.partition = self.disk / "mmcblk1p1"
        self.partition.mkdir()
        (self.partition / "partition").write_text("1")
        (self.partition / "dev").write_text("179:9")
        (self.partition / "holders").mkdir()
        (self.root / "proc").mkdir()
        (self.root / "proc/mounts").write_text("")
        (self.root / "proc/self").mkdir()
        (self.root / "proc/self/mountinfo").write_text("")
        self.swap_stats = {}
        original_stat = Path.stat

        def fixture_stat(path, *args, **kwargs):
            if str(path) in self.swap_stats:
                value = self.swap_stats[str(path)]
                if isinstance(value, Exception):
                    raise value
                return value
            return original_stat(path, *args, **kwargs)

        self.stat_patch = patch.object(Path, "stat", fixture_stat)
        self.stat_patch.start()
        self.addCleanup(self.stat_patch.stop)
        (self.root / "proc/swaps").write_text("Filename Type Size Used Priority\n")
        self.ios = self.root / "sys/kernel/debug/mmc1/ios"
        self.ios.parent.mkdir(parents=True)
        self.ios.write_text(
            "clock: 13000000 Hz\nactual clock: 12913043 Hz\nbus width: 2 (4 bits)\n"
        )
        self.path_patch = patch.object(
            host_tools, "Path", lambda value: self.root / str(value).lstrip("/")
        )
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def validate(self):
        return rw.validate_target(4, 256 << 20, 13_000_000, 12_913_043)

    def test_verified_target_passes(self):
        self.assertEqual(
            self.validate()[1], self.root / "sys/class/mmc_host/mmc1/mmc1:0001"
        )

    def test_wrong_identity_capacity_mount_swap_holder_or_clock_fails(self):
        changes = [
            (self.card / "cid", "wrong"),
            (self.card / "name", "OTHER"),
            (self.disk / "size", "1"),
            (self.disk / "ro", "1"),
            (
                self.root / "proc/self/mountinfo",
                "21 1 179:9 / /mnt rw - vfat /dev/mmcblk1p1 rw\n",
            ),
            (
                self.root / "proc/swaps",
                "Filename Type Size Used Priority\n/dev/mmcblk1p1 partition 1 0 -2\n",
            ),
            (self.ios, self.ios.read_text().replace("12913043", "12000000")),
        ]
        for path, invalid in changes:
            with self.subTest(path=path):
                original = path.read_text()
                path.write_text(invalid)
                try:
                    with self.assertRaises(RuntimeError):
                        self.validate()
                finally:
                    path.write_text(original)
        (self.disk / "holders/dm-0").touch()
        with self.assertRaises(RuntimeError):
            self.validate()

    def test_mount_identity_rejects_aliases_and_partitions(self):
        info = self.root / "proc/self/mountinfo"
        for number in ("179:8", "179:9"):
            for source in ("/dev/mmcblk1p1", "/dev/disk/by-label/SPADE", "UUID=abc"):
                with self.subTest(number=number, source=source):
                    info.write_text(f"21 1 {number} / /mnt rw - vfat {source} rw\n")
                    with self.assertRaises(RuntimeError):
                        self.validate()
        info.write_text("21 1 8:1 / /mnt rw - ext4 /dev/other rw\n")
        self.validate()

    def test_partition_holder_is_rejected(self):
        (self.partition / "holders/dm-0").touch()
        with self.assertRaises(RuntimeError):
            self.validate()

    def test_swap_identity_rejects_aliases_and_files(self):
        swaps = self.root / "proc/swaps"
        for mode, device, number in (
            (stat.S_IFBLK, "st_rdev", 8),
            (stat.S_IFBLK, "st_rdev", 9),
            (stat.S_IFREG, "st_dev", 9),
        ):
            alias = "/dev/disk/by-label/SPADE"
            self.swap_stats[str(self.root / alias.lstrip("/"))] = SimpleNamespace(
                st_mode=mode, st_dev=0, st_rdev=0
            )
            setattr(
                self.swap_stats[str(self.root / alias.lstrip("/"))],
                device,
                os.makedev(179, number),
            )
            swaps.write_text(
                f"Filename Type Size Used Priority\n{alias} partition 1 0 -2\n"
            )
            with (
                self.subTest(mode=mode, number=number),
                self.assertRaises(RuntimeError),
            ):
                self.validate()

    def test_escaped_swap_path_uses_file_device_identity(self):
        alias = self.root / "swap file"
        self.swap_stats[str(alias)] = SimpleNamespace(
            st_mode=stat.S_IFREG, st_dev=os.makedev(179, 9)
        )
        (self.root / "proc/swaps").write_text(
            "Filename Type Size Used Priority\n/swap\\040file file 1 0 -2\n"
        )
        with self.assertRaisesRegex(RuntimeError, "active swap"):
            self.validate()

    def test_unrelated_swap_is_allowed_but_unresolvable_swap_fails_closed(self):
        alias = self.root / "dev/other"
        swaps = self.root / "proc/swaps"
        swaps.write_text(
            "Filename Type Size Used Priority\n/dev/other partition 1 0 -2\n"
        )
        self.swap_stats[str(alias)] = SimpleNamespace(
            st_mode=stat.S_IFBLK, st_rdev=os.makedev(8, 2)
        )
        self.validate()
        self.swap_stats[str(alias)] = FileNotFoundError("missing swap")
        with self.assertRaises(RuntimeError):
            self.validate()


class DirectIOTests(unittest.TestCase):
    def run_checker(self, failure=None):
        memory = bytearray([0xA5] * 4096)
        cursor = [0]
        calls = {"read": 0, "write": 0}

        def seek(_fd, offset, _whence):
            cursor[0] = offset
            return offset

        def read(_fd, buffers):
            calls["read"] += 1
            buf = buffers[0]
            buf[:] = memory[cursor[0] : cursor[0] + len(buf)]
            if failure == "corrupt_read":
                buf[0] = buf[0] ^ 1
            return len(buf) - (failure == "short_read")

        def write(_fd, buffers):
            calls["write"] += 1
            buf = buffers[0]
            memory[cursor[0] : cursor[0] + len(buf)] = buf[:]
            if failure == "neighbor_corruption":
                memory[0] ^= 1
            return len(buf) - (failure == "short_write")

        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.ExitStack() as stack,
        ):
            card = Path(directory)
            (card / "csd").write_text("test-csd")
            stack.enter_context(
                patch.object(rw, "qualification", return_value=contextlib.nullcontext())
            )
            stack.enter_context(
                patch.object(rw, "validate_target", return_value=("", card))
            )
            stack.enter_context(
                patch.object(rw, "write_cases", return_value=[(512, 512)])
            )
            stack.enter_context(patch("sys.argv", ["check", "--bus-width", "4"]))
            stack.enter_context(patch.object(rw.os, "O_DIRECT", 0, create=True))
            for name, value in [
                ("open", lambda *a: 123),
                ("close", lambda *a: None),
                ("fsync", lambda *a: None),
                ("lseek", seek),
                ("readv", read),
                ("writev", write),
            ]:
                stack.enter_context(patch.object(rw.os, name, value))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            rw.main()
        return calls, memory

    def test_actual_io_and_readback_are_not_optimized_away(self):
        calls, memory = self.run_checker()
        self.assertEqual(calls, {"read": 10, "write": 2})
        self.assertEqual(memory[512:1024], rw.expected_bytes(512, 512, 1))

    def test_short_io_corruption_and_neighbor_damage_fail(self):
        for failure in (
            "short_read",
            "short_write",
            "corrupt_read",
            "neighbor_corruption",
        ):
            with self.subTest(failure=failure):
                with self.assertRaises(RuntimeError):
                    self.run_checker(failure)


class ReadOnlyModesTests(unittest.TestCase):
    def test_cross_width_windows_use_prior_generations_and_never_write(self):
        import random
        from types import SimpleNamespace
        import microsd_stress_linux as stress

        args = SimpleNamespace(seed=20260908, passes=2, random_writes=1024)
        capacity = 256 << 20
        versions = [0] * (capacity // stress.BLOCK)
        rng = random.Random(args.seed)
        for _ in range(args.passes * args.random_writes):
            versions[rng.randrange(len(versions))] += 1
        windows = []

        def read(fd, offset, size):
            windows.append((offset, size))
            return b"".join(
                stress.payload(i, versions[i], args.seed)
                for i in range(offset // stress.BLOCK, (offset + size) // stress.BLOCK)
            )

        with (
            patch.object(stress.os, "O_DIRECT", 0, create=True),
            patch.object(stress.os, "open", return_value=42) as opened,
            patch.object(stress.os, "close"),
            patch.object(stress, "direct_read", side_effect=read),
            patch.object(
                stress.os, "writev", side_effect=AssertionError("unexpected write")
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            stress.verify_windows(args, capacity)
        self.assertEqual(opened.call_args.args[1], stress.os.O_RDONLY)
        self.assertEqual(
            windows, [(0, 1 << 20), (127 << 20, 1 << 20), (255 << 20, 1 << 20)]
        )

    def test_read_only_filesystem_never_formats_and_unmounts_on_corruption(self):
        import subprocess
        import microsd_verify_linux_fs as fs

        for corrupt in (False, True):
            with (
                self.subTest(corrupt=corrupt),
                tempfile.TemporaryDirectory() as directory,
            ):
                point = Path(directory) / "mount"
                point.mkdir()
                (point / "TESTDIR").mkdir()
                (point / "CHECK.TXT").write_bytes(
                    b"SPADE Arty A7 DDR-backed native SD filesystem test\n"
                )
                (point / "TESTDIR/RENAMED.BIN").write_bytes(
                    bytes((i * 29 + (i >> 8) * 13 + 5) & 255 for i in range(65536))
                )
                (point / "TESTDIR/SMALL.BIN").write_bytes(
                    b"bad"
                    if corrupt
                    else bytes((i * 11 + 17) & 255 for i in range(4096))
                )
                card = Path(directory) / "card"
                card.mkdir()
                (card / "csd").write_text("test")
                commands = []

                def run(argv, **kwargs):
                    commands.append(tuple(argv))
                    if argv[0] == "mkfs.fat" or "rw,sync,nodev,nosuid,noexec" in argv:
                        raise AssertionError("read-only mode attempted a write")
                    return subprocess.CompletedProcess(argv, 0, "", "")

                with (
                    patch.object(
                        fs, "qualification", return_value=contextlib.nullcontext()
                    ),
                    patch.object(fs, "validate_target", return_value=("", card)),
                    patch.object(fs.tempfile, "mkdtemp", return_value=str(point)),
                    patch.object(fs.subprocess, "run", side_effect=run),
                    patch.object(Path, "rmdir"),
                    patch("sys.argv", ["fs", "--bus-width", "4", "--read-only"]),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    if corrupt:
                        with self.assertRaisesRegex(
                            RuntimeError, "filesystem readback mismatch"
                        ):
                            fs.main()
                    else:
                        fs.main()
                self.assertTrue(
                    any(
                        c[0] == "mount" and "ro,nodev,nosuid,noexec" in c
                        for c in commands
                    )
                )
                self.assertTrue(any(c[0] == "umount" for c in commands))
