"""A failed build must never retain a previous successful programming manifest."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "experiments/openxc7-macos")
)
import build_ddr
from build_common import begin_build, publish_result


class BuildManifestTests(unittest.TestCase):
    def test_preflight_failure_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            manifest = output / "result.json"
            manifest.write_text('{"bitstream_sha256": "previous"}')
            with (
                patch("sys.argv", ["build", "--output", directory]),
                patch(
                    "check_negative_edge_timing.check",
                    side_effect=RuntimeError("preflight failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "preflight failed"):
                    build_ddr.main()
            self.assertFalse(manifest.exists())

    def test_publication_failure_cannot_leave_partial_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            begin_build(output)
            with patch.object(Path, "replace", side_effect=OSError("rename failed")):
                with self.assertRaises(OSError):
                    publish_result(output, '{"checked": true}')
            self.assertFalse((output / "result.json").exists())
            self.assertFalse((output / "result.json.tmp").exists())
            publish_result(output, '{"checked": true}')
            self.assertEqual((output / "result.json").read_text(), '{"checked": true}')
