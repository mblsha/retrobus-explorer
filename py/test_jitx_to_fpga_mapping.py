#!/usr/bin/env python3
"""Test pin mappings against expected ACF files"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

import jitx_to_fpga_mapping as jfm


@dataclass
class BoardConfig:
    """Configuration for a board's ACF generation"""
    name: str
    generator: Callable[[], str]
    expected_file: str


# Define all board configurations
BOARD_CONFIGS = [
    BoardConfig(
        name="saleae",
        generator=jfm.generate_saleae_acf,
        expected_file="gateware/shared-constraints/saleae.acf"
    ),
    BoardConfig(
        name="pin-tester",
        generator=jfm.generate_pin_tester_acf,
        expected_file="gateware/shared-constraints/pin-tester.acf"
    ),
    BoardConfig(
        name="sharp-pc-g850-bus",
        generator=jfm.generate_sharp_pc_g850_bus_acf,
        expected_file="gateware/shared-constraints/sharp-pc-g850-bus.acf"
    ),
    BoardConfig(
        name="sharp-pc-e500-bus",
        generator=jfm.generate_sharp_pc_e500_bus_acf,
        expected_file="gateware/shared-constraints/sharp-pc-e500-bus.acf"
    ),
    BoardConfig(
        name="sharp-organizer-card",
        generator=jfm.generate_sharp_organizer_card_acf,
        expected_file="gateware/shared-constraints/sharp-organizer-card.acf"
    ),
    BoardConfig(
        name="sharp-sc62015",
        generator=jfm.generate_sharp_sc62015_acf,
        expected_file="gateware/shared-constraints/sharp-sc62015.acf"
    ),
]


class TestPinMappings:
    """Test all pin mapping generators against expected ACF files"""

    @pytest.mark.parametrize("config", BOARD_CONFIGS, ids=lambda c: c.name)
    def test_acf_generation(self, config: BoardConfig):
        """Test that generated ACF matches expected file"""
        # Generate ACF content
        generated = config.generator()

        # Read expected content
        project_root = Path(__file__).parent.parent
        expected_path = project_root / config.expected_file

        if not expected_path.exists():
            pytest.skip(f"Expected file {config.expected_file} not found - run generate_all_acf_files() first")

        expected = expected_path.read_text().strip()

        # Compare
        assert generated == expected, f"ACF mismatch for {config.name}"

    def test_pin_mapping_consistency(self):
        """Test that pin mappings are internally consistent"""
        # Test that all bank pins exist in element mapping
        alchitry = jfm.get_alchitry_element_mapping()
        saleae = jfm.get_saleae_mapping()

        for pin, bank_pin in saleae.items():
            assert bank_pin in alchitry, f"Saleae pin {pin} maps to unknown bank pin {bank_pin}"

        # Test FFC mappings
        ffc = jfm.get_alchitry_ffc_mapping()
        for pin, bank_pin in ffc.items():
            assert bank_pin in alchitry, f"FFC pin {pin} maps to unknown bank pin {bank_pin}"

    def test_no_duplicate_physical_pins(self):
        """Ensure no physical pins are used twice in same board"""
        for config in BOARD_CONFIGS:
            content = config.generator()
            pins: set[str] = set()
            for line in content.split("\n"):
                if line.strip().startswith("pin"):
                    pin = line.split()[-1]
                    assert pin not in pins, f"Duplicate pin {pin} in {config.name} mapping"
                    pins.add(pin)



def generate_all_acf_files():
    """Generate all ACF files in the shared-constraints directory"""
    project_root = Path(__file__).parent.parent

    for config in BOARD_CONFIGS:
        content = config.generator()
        output_path = project_root / config.expected_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content + "\n")
        print(f"Generated: {config.expected_file}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "generate":
        generate_all_acf_files()
    else:
        pytest.main([__file__, "-v"])

