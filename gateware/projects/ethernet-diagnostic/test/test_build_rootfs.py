import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "rg35xx/build_rootfs.py"
SPEC = importlib.util.spec_from_file_location("build_rootfs", SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def command(**overrides):
    arguments = dict(
        runner=["docker"], payload=Path("/payload"), out=Path("/out"),
        image="alpine:3.20", busybox="1.36.1", sha256="deadbeef",
        cluster=65536, system_name="system-c65536.erofs",
        data_name="data.ext2", data_kib=4096,
    )
    arguments.update(overrides)
    return builder.container_command(**arguments)


class BuildRootfsTests(unittest.TestCase):
    def test_the_container_builds_natively_for_the_target(self):
        """The H700 is aarch64, so anything but an arm64 container silently
        cross-builds or fails."""
        built = command()
        self.assertEqual(built[built.index("--platform") + 1], "linux/arm64")

    def test_the_cluster_size_reaches_the_build_and_names_the_image(self):
        """The cluster size is the unit the kernel reads and decompresses, so
        two of them have to be buildable and comparable side by side."""
        self.assertIn("CLUSTER=16384", command(cluster=16384))
        self.assertEqual(builder.system_image_name(16384), "system-c16384.erofs")
        self.assertNotEqual(
            builder.system_image_name(16384), builder.system_image_name(65536)
        )

    def test_the_pinned_hash_reaches_the_build(self):
        self.assertIn("BUSYBOX_SHA256=deadbeef", command())
        self.assertIn("does not match the pinned hash", builder.BUILD)

    def test_the_rootfs_is_static_and_compressed_with_lz4hc(self):
        """The system image carries no libc, and LZ4HC is chosen because its
        output is ordinary LZ4: the kernel needs only its LZ4 decompressor, and
        the extra compression effort is spent at build time, not at boot."""
        self.assertIn("CONFIG_STATIC=y", builder.BUILD)
        self.assertIn("-zlz4hc", builder.BUILD)

    def test_the_image_is_reproducible_and_independent_of_the_builder(self):
        """A rootfs whose ownership or timestamps come from the build container
        would differ run to run and could ship files owned by nobody."""
        self.assertIn("--all-root", builder.BUILD)
        self.assertIn("-T 0", builder.BUILD)

    def test_init_is_reachable_by_both_names_the_kernel_might_use(self):
        self.assertIn("cp /payload/rootfs-init sbin/init", builder.BUILD)
        self.assertIn("ln -sf sbin/init init", builder.BUILD)

    def test_the_data_volume_is_ext2_with_no_reserved_blocks(self):
        """Its only job is to be writable; reserving five percent for root on a
        partition with no root processes is pure loss."""
        self.assertIn("mke2fs", builder.BUILD)
        self.assertIn("-t ext2", builder.BUILD)
        self.assertIn("-m 0", builder.BUILD)


if __name__ == "__main__":
    unittest.main()


INIT = (Path(__file__).parents[1] / "rg35xx/rootfs-init").read_text()


class RootfsInitTests(unittest.TestCase):
    """The debug partition is the only channel this target can report through,
    so two writers sharing it must not overwrite each other."""

    def test_init_reports_before_doing_anything_else(self):
        """The milestone is the boot-time measurement, so anything placed in
        front of it is counted as boot rather than as what it is."""
        first = INIT.index("write_stage 0 rootfs-init-entered")
        for later in ("/proc/cmdline", "mount -t ext2", "/proc/device-tree/model"):
            self.assertGreater(INIT.index(later), first, later)

    def test_init_names_the_partitions_the_layout_actually_creates(self):
        self.assertIn("DEBUG_DEVICE=/dev/mmcblk0p2", INIT)
        self.assertIn("DATA_DEVICE=/dev/mmcblk0p7", INIT)
