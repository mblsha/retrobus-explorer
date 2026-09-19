import unittest

import sd_csd


# The rates the card has actually been built to advertise, and the bytes the
# hand-written table used to spell them. They lock the encoder against the
# qualified builds recorded in build/*/result.json.
QUALIFIED_CODES = {
    12_000_000: 0x12,
    13_000_000: 0x1A,
    15_000_000: 0x22,
    20_000_000: 0x2A,
    25_000_000: 0x32,
}


class TranSpeedTests(unittest.TestCase):
    def refusal(self, hertz):
        with self.assertRaises(ValueError) as refused:
            sd_csd.tran_speed_code(hertz)
        return refused.exception

    def test_the_qualified_rates_keep_their_bytes(self):
        for hertz, code in QUALIFIED_CODES.items():
            with self.subTest(hertz=hertz):
                self.assertEqual(sd_csd.tran_speed_code(hertz), code)
                self.assertEqual(sd_csd.tran_speed_hz(code), hertz)

    def test_every_encodable_rate_round_trips(self):
        rates = sorted(sd_csd.TRAN_SPEED_CODES)
        self.assertEqual(rates[0], 100_000)
        self.assertEqual(rates[-1], 800_000_000)
        self.assertEqual(len(rates), 60, "each unit names fifteen mantissas")
        for hertz in rates:
            with self.subTest(hertz=hertz):
                self.assertEqual(sd_csd.tran_speed_hz(sd_csd.tran_speed_code(hertz)), hertz)

    def test_an_unencodable_rate_names_its_neighbours(self):
        """Rounding would either lose bandwidth or advertise an unqualified
        clock, so the build has to be told which rates exist."""
        message = str(self.refusal(24_000_000))
        self.assertIn("20000000", message)
        self.assertIn("25000000", message)

    def test_rates_outside_the_encoding_still_report_one_neighbour(self):
        self.assertIn("above 100000", str(self.refusal(1_000)))
        self.assertIn("below 800000000", str(self.refusal(1_000_000_000)))

    def test_reserved_encodings_are_refused(self):
        for code in (0x00, 0x1C, 0x9A, 0x100):
            with self.subTest(code=code), self.assertRaises(ValueError):
                sd_csd.tran_speed_hz(code)


class SdCsdTests(unittest.TestCase):
    def test_the_shipped_csd_carries_a_valid_crc7(self):
        body = sd_csd.SD_CSD.to_bytes(16, "big")
        self.assertEqual(body[15], (sd_csd.csd_crc7(body[:15]) << 1) | 1)

    def test_the_default_speed_reproduces_the_qualified_csd(self):
        """The build must not change the card contract unless asked to."""
        default = sd_csd.sd_csd_with_speed(sd_csd.tran_speed_code(13_000_000))
        self.assertEqual(default, sd_csd.SD_CSD)

    def test_changing_the_speed_rewrites_the_crc7(self):
        """TRAN_SPEED shares a register with the CRC7 protecting it, so a hand
        edit of one without the other produces a card the host rejects."""
        for hertz, code in QUALIFIED_CODES.items():
            csd = sd_csd.sd_csd_with_speed(code)
            body = csd.to_bytes(16, "big")
            self.assertEqual(body[3], code, f"{hertz} did not reach TRAN_SPEED")
            self.assertEqual(
                body[15], (sd_csd.csd_crc7(body[:15]) << 1) | 1, f"{hertz} CRC7"
            )
            self.assertEqual(
                sd_csd.sd_properties(csd)["sd_max_clock_hz"], hertz,
                "the manifest disagrees with the advertised speed",
            )

    def test_only_the_speed_and_crc_change(self):
        csd = sd_csd.sd_csd_with_speed(sd_csd.tran_speed_code(25_000_000))
        original = sd_csd.SD_CSD.to_bytes(16, "big")
        changed = csd.to_bytes(16, "big")
        differing = {i for i in range(16) if original[i] != changed[i]}
        self.assertEqual(differing, {3, 15})

    def test_the_shipped_card_is_a_writable_256_mib_card(self):
        properties = sd_csd.sd_properties()
        self.assertEqual(properties["sd_csd"], "0026001a115903ffc002800002400023")
        self.assertEqual(properties["sd_capacity_bytes"], 268435456)
        self.assertEqual(properties["sd_max_clock_hz"], 13_000_000)


if __name__ == "__main__":
    unittest.main()
