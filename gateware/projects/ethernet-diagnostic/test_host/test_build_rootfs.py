import json
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
            # Only what was rendered for this build, never the source directory:
            # the init and the picture it draws.
            self.assertEqual(
                sorted(path.name for path in init.parent.iterdir()),
                ["display-proof.ppm", "rootfs-init", "rootfs-job-runner"],
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


class DisplayPayloadTests(unittest.TestCase):
    """What the rootfs contributes to the display: a picture, and patience."""

    def test_the_payload_carries_the_picture(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "payload"
            builder.write_payload(payload)
            self.assertTrue((payload / "display-proof.ppm").read_bytes().startswith(b"P6\n640 480\n"))

    def test_the_image_installs_the_picture_and_no_firmware(self):
        """The panel firmware is compiled into the kernel; a second copy here
        would be a second thing to keep in step with nothing that reads it."""
        self.assertIn("usr/share/rg35xx/display-proof.ppm", builder.BUILD)
        self.assertNotIn("firmware", builder.BUILD)

    def test_init_never_asks_the_kernel_to_probe_the_panel(self):
        """Init does not manage drivers. Carrying the firmware in the rootfs and
        re-probing the panel from here was the first attempt at a display; the
        firmware is compiled into the kernel now and the panel binds there."""
        template = builder.INIT_TEMPLATE.read_text()
        code = "\n".join(line for line in template.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("drivers_probe", code)
        self.assertNotIn("/bind", code)
        self.assertNotIn("firmware_class", code)

    def test_init_reads_back_exactly_one_screen_of_pixels(self):
        """640x480 at four bytes a pixel is 300 blocks of 4096; reading more
        would checksum whatever the driver keeps behind the visible frame."""
        template = builder.INIT_TEMPLATE.read_text()
        self.assertIn("dd if=/dev/fb0 bs=4096 count=300", template)
        self.assertEqual(300 * 4096, 640 * 480 * 4)
        self.assertLess(template.index("fbsplash -s"), template.index("dd if=/dev/fb0"))

    def test_the_picture_is_drawn_after_everything_init_has_to_say(self):
        template = builder.INIT_TEMPLATE.read_text()
        self.assertIn("/usr/share/rg35xx/display-proof.ppm", template)
        self.assertLess(template.index("write_stage 7 "), template.index("fbsplash"))

class PayloadStagingTests(unittest.TestCase):
    def test_the_payload_is_staged_where_the_container_can_see_it(self):
        """colima shares the home directory with its VM and nothing else, so a
        payload staged in the system temp directory mounts empty and the build
        fails five minutes in, at the first file it tries to copy."""
        from unittest.mock import patch

        seen = {}

        def capture(command):
            seen["command"] = command
            return 1  # stop before anything is read back

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "out"
            with (
                patch.object(builder, "find_runner", return_value=["docker"]),
                patch.object(builder, "run", side_effect=capture),
                self.assertRaises(SystemExit),
            ):
                builder.main(["--out", str(out)])
            mounts = [
                argument.split(":")[0]
                for flag, argument in zip(seen["command"], seen["command"][1:])
                if flag == "-v" and argument.split(":")[1] == "/payload"
            ]
            self.assertEqual(len(mounts), 1)
            self.assertIn(out.resolve(), Path(mounts[0]).resolve().parents)


class FlightRecorderTests(unittest.TestCase):
    """The first boots with a working display stopped reporting a second into
    userspace and left nothing behind to say why."""

    def setUp(self):
        self.template = builder.INIT_TEMPLATE.read_text()
        self.rendered = builder.render_init()

    def test_recording_starts_right_after_the_first_milestone(self):
        """After it, so the boot-time figure is untouched; before anything
        else, so whatever goes wrong next is on the card."""
        order = [
            self.template.index("write_stage 0 "),
            self.template.index("record_kernel_log &"),
            self.template.index("write_stage 1 "),
        ]
        self.assertEqual(order, sorted(order))

    def test_no_milestone_lands_in_the_recorder_page(self):
        import re

        stages = {int(stage) for stage in re.findall(r"write_stage (\d+)", self.template)}
        self.assertTrue(stages)
        self.assertLess(max(stages), debug_partition.USERSPACE_STAGES)

    def test_the_recorder_writes_exactly_its_own_page(self):
        self.assertIn(f"seek={debug_partition.KERNEL_LOG_SECTOR}", self.rendered)
        self.assertIn(f"count={debug_partition.KERNEL_LOG_SECTORS}", self.rendered)
        self.assertEqual(
            debug_partition.KERNEL_LOG_SECTOR + debug_partition.KERNEL_LOG_SECTORS,
            debug_partition.DEBUG_SECTORS,
        )


class DisplaySweepTests(unittest.TestCase):
    """With a pull-up holding DAT0 the link outlived the panel's start by a few
    seconds, and its errors began within a tenth of a second of the panel coming
    up, whatever the backlight was then set to. The sweep measures which display
    state does it, with nobody watching."""

    def setUp(self):
        self.rendered = builder.render_init()
        start = self.rendered.index("display_sweep() {")
        self.sweep = self.rendered[start : self.rendered.index("\n}\n", start)]
        self.body = self.sweep[self.sweep.index("for state in") :]

    def test_the_host_asks_for_it_by_command(self):
        self.assertIn("display-sweep) display_sweep ;;", self.rendered)

    def test_the_display_sleeps_before_the_sweep_writes_anything_more(self):
        """Left running, the link died between two milestones, before the sweep
        had begun."""
        order = [
            self.rendered.index("command=\"$("),
            self.rendered.index(
                'if [ "$command" = display-sweep ] || [ "$command" = job-runner ]; then'
            ),
            self.rendered.index('initial_brightness="$($BB cat "$backlight/brightness")"'),
            self.rendered.index("    display_sleeps\nfi"),
            self.rendered.index("write_stage 2 "),
        ]
        self.assertEqual(order, sorted(order))
        self.assertIn("initial-${initial_brightness}", self.sweep)

    def test_a_sweep_is_not_followed_by_full_brightness(self):
        guard = self.rendered.index(
            'if [ "$command" != display-sweep ] && [ "$command" != job-runner ]; then'
        )
        raised = self.rendered.index('"$backlight/max_brightness" > "$backlight/brightness"')
        self.assertLess(guard, raised)

    def test_the_series_begins_and_ends_asleep(self):
        import re

        states = re.search(r"for state in ([\w\- ]+);", self.sweep).group(1).split()
        self.assertEqual(states[0], "asleep")
        self.assertEqual(states[-1], "asleep")
        self.assertIn("lit-0", states)
        self.assertIn("lit-100", states)

    def test_every_record_is_written_with_the_display_asleep(self):
        """A state that breaks the link must not take its own result with it."""
        asleep = self.body.index("        display_sleeps")
        self.assertLess(self.body.index("read_back="), asleep)
        self.assertLess(asleep, self.body.index('write_stage 6 "$results"'))
        self.assertLess(self.body.index("=entered"), self.body.index("display_wakes"))

    def test_a_state_that_kills_the_link_is_named_by_the_record_before_it(self):
        self.assertLess(
            self.body.index('write_stage 6 "$results ${state}=entered"'),
            self.body.index("before="),
        )

    def test_each_result_says_whether_the_display_was_really_on(self):
        self.assertIn("/sys/class/drm/card*-*/dpms", self.body)
        self.assertIn("/${dpms:-unknown}", self.body)

    def test_the_only_traffic_is_the_sweeps_own(self):
        stopped = self.sweep.index('kill "$recorder"')
        self.assertLess(stopped, self.sweep.index("for state in"))
        self.assertIn("recorder=$!", self.rendered)
        self.assertGreater(self.sweep.rindex("record_kernel_log &"), self.sweep.rindex("done"))

    def test_the_reads_go_past_the_page_cache(self):
        dropped = self.sweep.index("echo 3 > /proc/sys/vm/drop_caches")
        self.assertLess(dropped, self.sweep.index('dd if="$DATA_DEVICE" of=/dev/null'))


class JobRunnerTests(unittest.TestCase):
    """The runner turns a boot into a bench instrument: it reads a script out
    of the card, runs it, and writes back what it printed. It runs while the
    host takes the card away and while the target is suspended, so what it may
    touch and when is a contract rather than a style."""

    def setUp(self):
        self.template = builder.JOB_RUNNER_TEMPLATE.read_text()
        self.rendered = builder.render_job_runner()
        self.init = builder.render_init()

    def test_the_template_states_no_layout_value_of_its_own(self):
        for placeholder in ("@DEBUG_DEVICE@", "@MAGIC@", "@JOB_SECTOR@",
                            "@RESULT_SECTOR@", "@SLEEP_MARK_SECTOR@"):
            self.assertIn(placeholder, self.template)
        self.assertNotIn(MAGIC, self.template)

    def test_rendering_fills_the_runner_from_the_same_map_as_init(self):
        self.assertIn(f"JOB_SECTOR={debug_partition.JOB_SECTOR}", self.rendered)
        self.assertIn(f"RESULT_SECTOR={debug_partition.RESULT_SECTOR}", self.rendered)
        self.assertIn(
            f"SLEEP_MARK_SECTOR={debug_partition.SLEEP_MARK_SECTOR}", self.rendered
        )
        self.assertIn(
            f"RESULT_OUTPUT_BYTES={debug_partition.RESULT_OUTPUT_BYTES}",
            self.rendered,
        )
        self.assertIn(f"MAGIC={MAGIC}", self.rendered)

    def test_an_unrendered_placeholder_stops_the_build(self):
        with self.assertRaisesRegex(ValueError, "rootfs-job-runner still carries"):
            builder.render_job_runner("JOB_SECTOR=@NOT_A_VALUE@\n")

    def test_init_copies_everything_into_tmpfs_before_it_execs(self):
        """The host disarms the card frontend to exchange a job for a result.
        A runner that had to page its own shell back in from a card that is not
        answering would wedge rather than wait."""
        order = [
            self.init.index('job_runner() {'),
            self.init.index('$BB cp "$BB" /tmp/busybox'),
            self.init.index("$BB cp /usr/bin/job-runner /tmp/job-runner"),
            self.init.index("exec /tmp/busybox sh /tmp/job-runner"),
        ]
        self.assertEqual(order, sorted(order))
        self.assertIn("job-runner) job_runner ;;", self.init)
        self.assertIn("BB=/tmp/busybox", self.rendered)

    def test_the_flight_recorder_is_stopped_before_the_runner_takes_over(self):
        """Ten card writes a second leave the host no window in which it could
        disarm, and they would be most of what an idle target draws."""
        runner = self.init[self.init.index("job_runner() {"):]
        self.assertLess(
            runner.index('kill "$recorder"'),
            runner.index("exec /tmp/busybox"),
        )
        self.assertIn("snapshot_kernel_log", self.rendered)

    def test_the_job_region_is_read_past_the_page_cache(self):
        """The host rewrites that region behind the kernel's back, so a cached
        read would return the previous job for as long as the page stayed
        clean, which is forever."""
        self.assertIn("iflag=direct", self.rendered)
        self.assertIn("echo 3 > /proc/sys/vm/drop_caches", self.rendered)
        self.assertIn("direct=%s", self.rendered)

    def test_a_script_is_run_only_when_it_matches_the_digest_in_its_header(self):
        body = self.rendered[self.rendered.index("while true; do"):]
        self.assertLess(body.index("md5sum"), body.index("run_job"))
        self.assertIn('if [ "$got" = "$digest" ]; then', body)

    def test_a_job_that_has_already_run_is_not_run_again(self):
        body = self.rendered[self.rendered.index("while true; do"):]
        self.assertIn('[ "$sequence" != "$last" ]', body)
        self.assertIn('last="$sequence"', body)

    def test_a_sleep_is_marked_on_the_card_at_both_ends(self):
        """While the target is suspended the trace is all the host has, and a
        mark at each end is what tells it the window is open and then shut."""
        sleep = self.rendered[self.rendered.index("rtc_sleep() {"):]
        sleep = sleep[: sleep.index("\n}\n")]
        order = [
            sleep.index("flush_result running"),
            sleep.index("mark_sector sleep-enter"),
            sleep.index('echo "$state" > /sys/power/state'),
            sleep.index("mark_sector sleep-exit"),
            sleep.index("card_check"),
        ]
        self.assertEqual(order, sorted(order))
        self.assertIn("since_epoch", self.rendered)

    def test_the_panel_stays_dark_unless_a_job_asks_for_it(self):
        """The backlight is the largest single item on this supply, and every
        measurement made with it lit is measuring the backlight."""
        self.assertIn(
            'if [ "$command" = display-sweep ] || [ "$command" = job-runner ]; then',
            self.init,
        )
        self.assertIn(
            'if [ "$command" != display-sweep ] && [ "$command" != job-runner ]; then',
            self.init,
        )
