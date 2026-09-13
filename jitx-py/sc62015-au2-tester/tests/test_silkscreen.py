"""Every silkscreen label must stay printable at the fab's minimum height.

KiCad reports sub-minimum lettering as a `text_height` finding only once a
board has been exported and DRC'd, which is far too late. These tests pin the
rule at the source instead.
"""

import ast
from pathlib import Path

import pytest
from shared_components.fabrication import MIN_SILKSCREEN_TEXT_HEIGHT_MM, silkscreen_text

from src.main import Sc62015Au2TesterSubstrate

SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"


def test_substrate_keeps_the_shared_silkscreen_minimum() -> None:
    # This board claims no exception, so its constraint must equal the shared
    # default. Lowering one without the other is the bug this test catches.
    assert Sc62015Au2TesterSubstrate.constraints.min_silkscreen_text_height == pytest.approx(
        MIN_SILKSCREEN_TEXT_HEIGHT_MM
    )


def test_silkscreen_helper_rejects_illegible_text() -> None:
    with pytest.raises(ValueError, match="minimum legible cap height"):
        silkscreen_text("TOO SMALL", MIN_SILKSCREEN_TEXT_HEIGHT_MM - 0.05)


def test_helper_defaults_to_the_minimum() -> None:
    assert silkscreen_text("OK").size == pytest.approx(MIN_SILKSCREEN_TEXT_HEIGHT_MM)


def test_board_sources_build_silkscreen_only_through_the_checked_helper() -> None:
    """No raw `Text(...)` may reach a Silkscreen feature in this project.

    `silkscreen_text` validates its height; a bare `Text` does not. Scanning
    the AST keeps a future edit from quietly reintroducing one.
    """
    offenders = []
    for path in sorted(SOURCE_DIR.glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "Silkscreen":
                continue
            for argument in ast.walk(node):
                if (
                    isinstance(argument, ast.Call)
                    and isinstance(argument.func, ast.Name)
                    and argument.func.id == "Text"
                ):
                    offenders.append(f"{path.name}:{argument.lineno}")
    assert offenders == [], (
        "use shared_components.fabrication.silkscreen_text for silkscreen lettering: " + ", ".join(offenders)
    )
