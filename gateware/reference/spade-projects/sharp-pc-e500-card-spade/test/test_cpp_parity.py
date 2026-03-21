from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden.ft16"
CE6_FIXTURE_PATH = PROJECT_ROOT / "testdata" / "ft_golden_ce6.ft16"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cpp_tooling import cpp_binary_path, ensure_cpp_tools_built  # noqa: E402
from e500_ft import pack_ft_record, pack_ft_words, read_ft_records  # noqa: E402
from ft_to_vcd import build_vcd  # noqa: E402


class CppParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_cpp_tools_built()

    def test_ft_to_vcd_cpp_matches_python_on_fixtures(self) -> None:
        for fixture in (FIXTURE_PATH, CE6_FIXTURE_PATH):
            with self.subTest(fixture=fixture.name), tempfile.TemporaryDirectory() as tmpdir:
                out = Path(tmpdir) / "cpp.vcd"
                subprocess.run([str(cpp_binary_path("ft_to_vcd_cpp")), str(fixture), "-o", str(out)], check=True)
                self.assertEqual(out.read_text(), build_vcd(read_ft_records(fixture)))

    def test_ft_to_vcd_cpp_matches_python_for_unknown_kind_and_zero_delta(self) -> None:
        sync = pack_ft_record(0xF0, 0, 0, 1, 0)
        config = pack_ft_record(0xF2, 1, 50, 0, 1)
        unknown = pack_ft_record(0x05, 5, 0x123, 0x5A, 0x79)
        same_time = pack_ft_record(0x03, 0, 0x123, 0x5A, 0x79)

        raw = bytearray()
        for record in (sync, config, unknown, same_time):
            for word in pack_ft_words(record):
                raw.extend(word.to_bytes(2, "little"))

        with tempfile.TemporaryDirectory() as tmpdir:
            raw_path = Path(tmpdir) / "unknown.ft16"
            raw_path.write_bytes(raw)
            out = Path(tmpdir) / "cpp.vcd"
            subprocess.run([str(cpp_binary_path("ft_to_vcd_cpp")), str(raw_path), "-o", str(out)], check=True)
            self.assertEqual(out.read_text(), build_vcd(read_ft_records(raw_path)))

    def test_capture_ft_wrapper_help_uses_cpp_binary(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "capture_ft.py"), "--help"],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("Capture PC-E500 FT600 stream to .ft16 and optional .vcd", result.stdout)
        self.assertIn("--chunk-size CHUNK_SIZE", result.stdout)

    def test_ft_to_vcd_wrapper_uses_cpp_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "wrapper.vcd"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "ft_to_vcd.py"),
                    str(FIXTURE_PATH),
                    "-o",
                    str(out),
                ],
                check=True,
            )
            self.assertEqual(out.read_text(), build_vcd(read_ft_records(FIXTURE_PATH)))


if __name__ == "__main__":
    unittest.main()
