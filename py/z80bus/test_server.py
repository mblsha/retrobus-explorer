import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

from z80bus.server import ParseRenderManager


def test_parse_render_manager_initializes_on_construction():
    manager = ParseRenderManager()

    # The manager should be ready to use without requiring an explicit reset.
    assert manager.get_accumulated_events() == []

    image_bytes = manager.get_lcd_image_bytes()
    assert isinstance(image_bytes, bytes)
    assert image_bytes  # image data should not be empty

    stats = manager.stats()
    assert stats["num_errors"] == 0

    # Leave the singleton in a clean state for other tests.
    manager.reset()
