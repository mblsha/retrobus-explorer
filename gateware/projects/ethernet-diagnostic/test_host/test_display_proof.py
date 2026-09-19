import unittest

from rg35xx import display_proof


def pixel(ppm: bytes, x: int, y: int) -> tuple:
    header = b"P6\n640 480\n255\n"
    offset = len(header) + 3 * (y * 640 + x)
    return tuple(ppm[offset : offset + 3])


class DisplayProofTests(unittest.TestCase):
    def setUp(self):
        self.ppm = display_proof.render(["RG35XX PLUS", "DISPLAY OK"])

    def test_it_is_a_binary_ppm_of_exactly_the_panel_size(self):
        """fbsplash reads P6 and nothing else, and a picture of any other size
        would be cropped or leave stale framebuffer around it."""
        header = b"P6\n640 480\n255\n"
        self.assertTrue(self.ppm.startswith(header))
        self.assertEqual(len(self.ppm), len(header) + 640 * 480 * 3)

    def test_every_colour_channel_appears_alone_and_combined(self):
        """Swapped or missing colour lanes are the commonest way for a panel to
        show a picture and still be wrong; the bars make that visible."""
        seen = {pixel(self.ppm, 40 + 80 * bar, 100) for bar in range(8)}
        self.assertEqual(seen, set(display_proof.BARS))

    def test_the_ramp_runs_from_black_to_white(self):
        self.assertEqual(pixel(self.ppm, 1, 290), (0, 0, 0))
        self.assertEqual(pixel(self.ppm, 638, 290), (254, 254, 254))
        self.assertLess(pixel(self.ppm, 200, 290)[0], pixel(self.ppm, 400, 290)[0])

    def test_all_four_edges_carry_the_border(self):
        for x, y in ((0, 0), (639, 0), (0, 479), (639, 479), (320, 0), (320, 479), (0, 240), (639, 240)):
            self.assertEqual(pixel(self.ppm, x, y), (255, 255, 255), (x, y))

    def test_the_text_is_actually_drawn(self):
        band = [pixel(self.ppm, x, y) for y in range(320, 470) for x in range(8, 632)]
        self.assertIn((255, 255, 255), band)
        blank = display_proof.render([" ", " "])
        self.assertNotEqual(blank, self.ppm)

    def test_the_picture_is_reproducible(self):
        self.assertEqual(self.ppm, display_proof.render(["RG35XX PLUS", "DISPLAY OK"]))

    def test_text_that_cannot_be_drawn_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no glyph"):
            display_proof.render(["HELLO_WORLD"])
        with self.assertRaisesRegex(ValueError, "too wide"):
            display_proof.render(["X" * 40])
        with self.assertRaisesRegex(ValueError, "do not fit"):
            display_proof.render(["A"] * 9)


if __name__ == "__main__":
    unittest.main()
