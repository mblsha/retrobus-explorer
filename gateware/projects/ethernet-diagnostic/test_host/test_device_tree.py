"""The one device tree cell a card image changes, and the builder that changes it."""

import struct
import tempfile
import unittest
from pathlib import Path

from rg35xx import device_tree
from rg35xx.fat16 import boot_volume, replace_file
from rg35xx.image import make_erofs_image, verify_boot_image
from test_host.boot_image import erofs_fixture, ext2_fixture, gzip_kernel_image


def flattened(nodes) -> bytes:
    """Build a small flattened tree from {path: {property: bytes}}."""
    strings = bytearray()
    offsets = {}

    def name_offset(name):
        if name not in offsets:
            offsets[name] = len(strings)
            strings.extend(name.encode() + b"\0")
        return offsets[name]

    def padded(data):
        return data + bytes(-len(data) % 4)

    def emit(path):
        label = path.rsplit("/", 1)[-1]
        out = struct.pack(">I", 1) + padded(label.encode() + b"\0")
        for name, value in nodes.get(path, {}).items():
            out += struct.pack(">3I", 3, len(value), name_offset(name)) + padded(value)
        children = sorted(
            child for child in nodes
            if child != path and child.rsplit("/", 1)[0] == path.rstrip("/")
            and child.count("/") == path.rstrip("/").count("/") + 1
        )
        for child in children:
            out += emit(child)
        return out + struct.pack(">I", 2)

    structure = emit("") + struct.pack(">I", 9)
    header_size = 40
    blob = struct.pack(
        ">10I", device_tree.FDT_MAGIC, header_size + len(structure) + len(strings),
        header_size, header_size + len(structure), header_size, 17, 16, 0,
        len(strings), len(structure),
    )
    return blob + structure + bytes(strings)


def card_tree(card_hz=150_000_000) -> bytes:
    cell = lambda value: struct.pack(">I", value)
    return flattened({
        "": {"model": b"fixture\0"},
        "/soc": {},
        "/soc/mmc@4020000": {"bus-width": cell(4), "max-frequency": cell(card_hz)},
        "/soc/mmc@4021000": {"max-frequency": cell(150_000_000)},
    })


class CellTests(unittest.TestCase):
    def test_a_cell_is_found_by_its_node_and_not_by_its_name_alone(self):
        tree = card_tree(card_hz=12_500_000)
        self.assertEqual(
            device_tree.get_cell(tree, "/soc/mmc@4020000", "max-frequency"), 12_500_000
        )
        self.assertEqual(
            device_tree.get_cell(tree, "/soc/mmc@4021000", "max-frequency"), 150_000_000
        )

    def test_changing_a_cell_moves_nothing_else(self):
        tree = card_tree()
        changed = device_tree.set_cell(tree, "/soc/mmc@4020000", "max-frequency", 6_000_000)
        self.assertEqual(len(changed), len(tree))
        self.assertEqual(sum(a != b for a, b in zip(tree, changed)), 3)
        self.assertEqual(
            device_tree.get_cell(changed, "/soc/mmc@4020000", "max-frequency"), 6_000_000
        )
        self.assertEqual(
            device_tree.get_cell(changed, "/soc/mmc@4021000", "max-frequency"), 150_000_000
        )

    def test_a_missing_cell_is_refused_rather_than_invented(self):
        with self.assertRaisesRegex(ValueError, "has no /soc/mmc@4020000:absent"):
            device_tree.set_cell(card_tree(), "/soc/mmc@4020000", "absent", 1)

    def test_something_that_is_not_a_tree_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not a flattened device tree"):
            device_tree.get_cell(bytes(64), "/soc", "x")


class CardClockTests(unittest.TestCase):
    """At Linux's 12.5 MHz the link failed within a second of the display
    starting; capped to U-Boot's 6 MHz it carried 2855 writes without an error."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        source = gzip_kernel_image(self.directory.name)
        self.source = replace_file(source, "DTB.IMG", card_tree())

    def build(self, **kwargs) -> Path:
        path = Path(self.directory.name) / "card.img"
        path.write_bytes(make_erofs_image(
            self.source, erofs_fixture(), ext2_fixture(), minimum_slot_sectors=8, **kwargs
        ))
        return path

    def test_an_image_says_what_clock_linux_may_give_the_card(self):
        self.assertEqual(verify_boot_image(self.build())["card_max_hz"], 150_000_000)

    def test_the_cap_reaches_the_tree_the_script_really_loads(self):
        """The file moves when it is replaced, and the script reads it by
        sector, so the cap has to be in place before the script is written."""
        path = self.build(card_max_hz=6_000_000)
        self.assertEqual(verify_boot_image(path)["card_max_hz"], 6_000_000)
        image = path.read_bytes()
        _, fat, _ = boot_volume(image)
        lba, count, size = fat.placement("DTB.IMG")
        loaded = image[lba * 512 : lba * 512 + size]
        self.assertEqual(
            device_tree.get_cell(loaded, device_tree.CARD_CONTROLLER, "max-frequency"),
            6_000_000,
        )
        script = fat.read("BOOT.SCR")
        self.assertIn(f"mmc read ${{fdt_addr_r}} {lba:#x} {count:#x}".encode(), script)

    def test_without_a_cap_the_image_is_what_it_always_was(self):
        self.assertEqual(
            self.build().read_bytes(),
            make_erofs_image(self.source, erofs_fixture(), ext2_fixture(),
                             minimum_slot_sectors=8),
        )


if __name__ == "__main__":
    unittest.main()
