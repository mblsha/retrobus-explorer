import tempfile
import unittest
from pathlib import Path

from rg35xx import build_rootfs as builder
from rg35xx import debug_partition
from rg35xx.debug_partition import DEBUG_PARTITION
from rg35xx.debug_partition import MAGIC
from rg35xx.debug_partition import USERSPACE_BASE
from rg35xx.image import DATA_PARTITION

TEMPLATE = builder.INIT_TEMPLATE.read_text()


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

    def test_only_the_rendered_payload_is_mounted(self):
        """The build reads init out of /payload, so that directory holds the
        rendered file and nothing else from the package."""
        built = command()
        self.assertIn("/payload:/payload:ro", built)

    def test_the_rendered_payload_is_written_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            init = builder.write_payload(Path(directory) / "payload")
            self.assertEqual(
                [path.name for path in init.parent.iterdir()], ["rootfs-init"]
            )
            self.assertTrue(init.stat().st_mode & 0o111)
            self.assertIn(f"MAGIC={MAGIC}", init.read_text())


class RootfsInitTests(unittest.TestCase):
    """The debug partition is the only channel this target can report through,
    so two writers sharing it must not overwrite each other, and the partitions
    init names have to be the ones the layout creates."""

    def test_the_template_states_no_layout_value_of_its_own(self):
        for placeholder in ("@DEBUG_DEVICE@", "@DATA_DEVICE@", "@MAGIC@",
                            "@USERSPACE_BASE@"):
            self.assertIn(placeholder, TEMPLATE)
        self.assertNotIn(f"DEBUG_DEVICE=/dev/mmcblk0p{DEBUG_PARTITION}", TEMPLATE)
        self.assertNotIn(MAGIC, TEMPLATE)

    def test_rendering_fills_init_from_the_layout(self):
        rendered = builder.render_init()
        self.assertIn(f"DEBUG_DEVICE=/dev/mmcblk0p{DEBUG_PARTITION}", rendered)
        self.assertIn(f"DATA_DEVICE=/dev/mmcblk0p{DATA_PARTITION}", rendered)
        self.assertIn(f"MAGIC={MAGIC}", rendered)
        self.assertIn(f"seek=$(({USERSPACE_BASE} + stage))", rendered)

    def test_userspace_milestones_do_not_collide_with_u_boots(self):
        """U-Boot and userspace both write this partition; the sector map is
        what keeps a userspace stage from landing on a U-Boot milestone."""
        self.assertGreater(
            USERSPACE_BASE,
            debug_partition.UBOOT_BASE + debug_partition.UBOOT_SECTORS - 1,
        )
        self.assertIn(f"seek=$(({USERSPACE_BASE} + stage))", builder.render_init())

    def test_an_unrendered_placeholder_stops_the_build(self):
        """A placeholder that reached the target would be a shell word, and the
        failure it produces is a boot that reports nothing at all."""
        with self.assertRaisesRegex(ValueError, "@ROOT_DEVICE@"):
            builder.render_init("DEBUG_DEVICE=@DEBUG_DEVICE@\nroot=@ROOT_DEVICE@\n")

    def test_init_reports_before_doing_anything_else(self):
        """The milestone is the boot-time measurement, so anything placed in
        front of it is counted as boot rather than as what it is."""
        first = TEMPLATE.index("write_stage 0 rootfs-init-entered")
        for later in ("/proc/cmdline", "mount -t ext2", "/proc/device-tree/model"):
            self.assertGreater(TEMPLATE.index(later), first, later)


if __name__ == "__main__":
    unittest.main()
