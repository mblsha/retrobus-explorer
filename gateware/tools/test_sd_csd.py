import importlib.util
import sys
import unittest
from pathlib import Path


EXPERIMENTS = Path(__file__).parents[1] / "experiments/openxc7-macos"
# build_ddr imports its siblings by bare name, as the build runs it.
sys.path.insert(0, str(EXPERIMENTS))
SCRIPT = EXPERIMENTS / "build_ddr.py"
SPEC = importlib.util.spec_from_file_location("build_ddr", SCRIPT)
build = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build)


class SdCsdTests(unittest.TestCase):
    def test_the_shipped_csd_carries_a_valid_crc7(self):
        body = build.SD_CSD.to_bytes(16, "big")
        self.assertEqual(body[15], (build.csd_crc7(body[:15]) << 1) | 1)

    def test_the_default_speed_reproduces_the_qualified_csd(self):
        """The build must not change the card contract unless asked to."""
        default = build.sd_csd_with_speed(build.SD_TRAN_SPEED_CODES[13_000_000])
        self.assertEqual(default, build.SD_CSD)

    def test_changing_the_speed_rewrites_the_crc7(self):
        """TRAN_SPEED shares a register with the CRC7 protecting it, so a hand
        edit of one without the other produces a card the host rejects."""
        for hertz, code in build.SD_TRAN_SPEED_CODES.items():
            csd = build.sd_csd_with_speed(code)
            body = csd.to_bytes(16, "big")
            self.assertEqual(body[3], code, f"{hertz} did not reach TRAN_SPEED")
            self.assertEqual(
                body[15], (build.csd_crc7(body[:15]) << 1) | 1, f"{hertz} CRC7"
            )
            self.assertEqual(
                build.sd_properties(csd)["sd_max_clock_hz"], hertz,
                "the manifest disagrees with the advertised speed",
            )

    def test_only_the_speed_and_crc_change(self):
        csd = build.sd_csd_with_speed(build.SD_TRAN_SPEED_CODES[25_000_000])
        original = build.SD_CSD.to_bytes(16, "big")
        changed = csd.to_bytes(16, "big")
        differing = {i for i in range(16) if original[i] != changed[i]}
        self.assertEqual(differing, {3, 15})


if __name__ == "__main__":
    unittest.main()
