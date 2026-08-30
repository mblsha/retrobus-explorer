from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "pc-e500-iocs.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pc_e500_iocs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_format_summary_falls_back_when_ui_render_is_blank():
    module = _load_module()
    response = {
        "experiment": "iocs_sequence",
        "status": "ok",
        "ui_render": {"lines": ["", "", "", ""]},
        "parsed": {
            "display_summary": {
                "lcd_write_count": 3,
                "lcd_text_lines": ["hello world", "", "", ""],
            }
        },
    }

    summary = module.format_summary(response)

    assert "render: rust-ui" not in summary
    assert "lcd_row0: hello world" in summary
