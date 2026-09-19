import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rg35xx import deploy

STATUS = """MDP (P906) channel 2:
  Online: YES
  Voltage: 5.001 V (target 5.000 V)
  Current: 0.000 A (target 1.500 A)
  Temperature: 31.2 °C
  Output: {state}
  Mode: CV
"""


class Client:
    """Just enough of images.Images to watch the deploy drive it."""

    def __init__(self, sha=None, verified=True):
        self.initial_upload = None
        self.sha = sha
        self.verified = verified
        self.calls = []

    def upload(self, image, window=0):
        self.calls.append(("upload", len(image), window))
        self.initial_upload = {
            "sha256": self.sha or hashlib.sha256(image).hexdigest(),
            "verified": self.verified,
        }

    def command(self, opcode, *arguments):
        self.calls.append(("command", int(opcode)))

    def trace(self):
        return {
            "armed": True, "ddr_initialized": True, "clock_edges": 12,
            "command_frames": 0, "protocol_status": {"idle_data_high": True},
        }

    def close(self):
        self.calls.append(("close",))


class ChannelTests(unittest.TestCase):
    """The bench has two supplies and only one of them powers this target."""

    def test_the_other_benchs_channel_is_refused(self):
        with self.assertRaisesRegex(ValueError, "another device"):
            deploy.checked_channel("psu1")

    def test_the_targets_channel_is_accepted(self):
        self.assertEqual(deploy.checked_channel("psu2"), "psu2")

    def test_a_status_read_of_the_other_channel_never_runs(self):
        """Even reading it starts a CLI that can switch it, so the refusal is
        in front of the subprocess rather than after it."""
        with patch("rg35xx.deploy.subprocess.run") as run:
            with self.assertRaises(ValueError):
                deploy.psu_status(Path("/cli"), "psu1")
        run.assert_not_called()


class PowerStateTests(unittest.TestCase):
    """The card vanishes for seconds while the bitstream loads, so a target
    powered through that sees an I/O error rather than a slow card."""

    def test_an_off_output_is_recognized(self):
        self.assertTrue(deploy.output_is_off(STATUS.format(state="OFF")))

    def test_an_on_output_is_recognized(self):
        self.assertFalse(deploy.output_is_off(STATUS.format(state="ON")))

    def test_a_status_naming_no_output_is_not_evidence_of_off(self):
        with self.assertRaisesRegex(ValueError, "exactly one output state"):
            deploy.output_is_off("Online: YES\nMode: CV\n")

    def test_a_status_naming_two_outputs_is_not_evidence_of_off(self):
        doubled = STATUS.format(state="OFF") + STATUS.format(state="ON")
        with self.assertRaisesRegex(ValueError, "exactly one output state"):
            deploy.output_is_off(doubled)

    def test_a_powered_target_stops_the_deploy(self):
        with patch("rg35xx.deploy.psu_status", return_value=STATUS.format(state="ON")):
            with self.assertRaisesRegex(RuntimeError, "output is ON"):
                deploy.require_target_off(Path("/cli"), "psu2")

    def test_an_unpowered_target_lets_it_continue(self):
        with patch("rg35xx.deploy.psu_status", return_value=STATUS.format(state="OFF")):
            self.assertIsNone(deploy.require_target_off(Path("/cli"), "psu2"))


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "card.img"
        self.image.write_bytes(b"\x5a" * 1024)
        self.digest = hashlib.sha256(self.image.read_bytes()).hexdigest()

    def test_the_card_must_report_the_shas_of_the_file_it_was_given(self):
        client = Client()
        self.assertEqual(deploy.upload_and_verify(client, self.image), self.digest)
        self.assertEqual(client.calls[0], ("upload", 1024, deploy.UPLOAD_WINDOW))

    def test_a_different_sha_stops_the_deploy(self):
        """An image that reached DDR intact but is not this image would be
        armed and booted as if it were."""
        client = Client(sha="0" * 64)
        with self.assertRaisesRegex(RuntimeError, "card verified"):
            deploy.upload_and_verify(client, self.image)

    def test_an_unverified_readback_stops_the_deploy(self):
        client = Client(verified=False)
        with self.assertRaisesRegex(RuntimeError, "not verified"):
            deploy.upload_and_verify(client, self.image)


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.build = self.root / "build"
        self.build.mkdir()
        (self.build / "result.json").write_text(
            json.dumps(
                {
                    "bitstream_sha256": "f17bb7a5", "placement_seed": 8,
                    "verified_configuration_bits": 604397,
                    "clocks_mhz": {"fclk": [106.62, "PASS", 100.0]},
                    "h700_mmc": True, "h700_early_command": False,
                }
            )
        )
        self.image = self.root / "card.img"
        self.image.write_bytes(b"\x5a" * 1024)
        self.state = self.root / "session.json"
        self.state.write_text("{}")
        self.state.with_name("session.json.lock").write_text("")
        self.client = Client()

    def run_deploy(self, **overrides):
        options = dict(
            build_dir=self.build, image=self.image, state=self.state,
            psu_cli=Path("/cli"), channel="psu2",
            client_factory=lambda: self.client,
        )
        options.update(overrides)
        self.printed = io.StringIO()
        with contextlib.redirect_stdout(self.printed):
            return deploy.deploy(**options)

    def test_a_deploy_programs_uploads_and_arms_in_that_order(self):
        with patch("rg35xx.deploy.verify_boot_image") as verify, \
                patch("rg35xx.deploy.psu_status",
                      return_value=STATUS.format(state="OFF")), \
                patch("rg35xx.deploy.program") as program, \
                patch("rg35xx.deploy.time.sleep") as sleep:
            digest = self.run_deploy()
        verify.assert_called_once_with(self.image)
        program.assert_called_once_with(self.build)
        sleep.assert_called_once_with(deploy.PROGRAM_SETTLE_SECONDS)
        self.assertEqual(
            digest, hashlib.sha256(self.image.read_bytes()).hexdigest()
        )
        self.assertEqual(
            [call[0] for call in self.client.calls],
            ["upload", "command", "close"],
        )
        printed = self.printed.getvalue()
        self.assertIn("bitstream f17bb7a5", printed)
        self.assertIn("armed True", printed)

    def test_the_session_of_the_old_bitstream_is_dropped(self):
        """The journal describes a session that died with the FPGA, and a
        client resuming it would replay a request the card never saw."""
        with patch("rg35xx.deploy.verify_boot_image"), \
                patch("rg35xx.deploy.psu_status",
                      return_value=STATUS.format(state="OFF")), \
                patch("rg35xx.deploy.program"), \
                patch("rg35xx.deploy.time.sleep"):
            self.run_deploy()
        self.assertFalse(self.state.exists())
        self.assertFalse(self.state.with_name("session.json.lock").exists())

    def test_an_image_that_fails_the_contract_is_never_programmed(self):
        with patch("rg35xx.deploy.verify_boot_image",
                   side_effect=ValueError("BOOT.SCR lacks the length table")), \
                patch("rg35xx.deploy.psu_status") as status, \
                patch("rg35xx.deploy.program") as program:
            with self.assertRaisesRegex(ValueError, "BOOT.SCR"):
                self.run_deploy()
        status.assert_not_called()
        program.assert_not_called()
        self.assertEqual(self.client.calls, [])

    def test_a_powered_target_is_never_programmed(self):
        with patch("rg35xx.deploy.verify_boot_image"), \
                patch("rg35xx.deploy.psu_status",
                      return_value=STATUS.format(state="ON")), \
                patch("rg35xx.deploy.program") as program:
            with self.assertRaises(RuntimeError):
                self.run_deploy()
        program.assert_not_called()

    def test_the_other_benchs_channel_stops_the_deploy_before_anything_runs(self):
        with patch("rg35xx.deploy.verify_boot_image"), \
                patch("rg35xx.deploy.psu_status") as status, \
                patch("rg35xx.deploy.program") as program:
            with self.assertRaisesRegex(ValueError, "another device"):
                self.run_deploy(channel="psu1")
        status.assert_not_called()
        program.assert_not_called()

    def test_the_manifest_names_the_bitstream_being_programmed(self):
        summary = "\n".join(deploy.manifest_summary(self.build))
        self.assertIn("f17bb7a5", summary)
        self.assertIn("seed 8", summary)
        self.assertIn("'fclk': 106.62", summary)
        self.assertIn("h700 True", summary)


if __name__ == "__main__":
    unittest.main()
