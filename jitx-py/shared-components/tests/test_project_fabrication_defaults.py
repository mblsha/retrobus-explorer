from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

JITX_PY_ROOT = Path(__file__).resolve().parents[2]
RIGID_PROJECT_DEFAULTS = {
    "alchitry-au1-level-shifter/src/main.py": 4,
    "alchitry-au2-level-shifter/src/main.py": 4,
    "alchitry-v2-elements/alchitry_v2_elements/main.py": 4,
    "espi-debug-breakout/src/main.py": 2,
    "pin-tester/src/main.py": 4,
    "rpi-pico-40-pin-adapter/src/main.py": 4,
    "saleae-dslab-adapter/src/main.py": 4,
    "sd-ffc-breakout/src/main.py": 2,
    "sd-glasgow-breakout/src/main.py": 2,
    "sharp-organizer-host/src/main.py": 4,
    "sharp-pc-e500-ram-card/src/main.py": 4,
    "sharp-pc-g850-bus/src/main.py": 4,
}
FLEX_PROJECT_DEFAULTS = {
    "sharp-organizer-card/src/main.py": 2,
    "sharp-sc61860-interposer/src/main.py": 2,
    "sharp-sc62015-interposer/src/main.py": 2,
}
PROJECT_DEFAULTS = RIGID_PROJECT_DEFAULTS | FLEX_PROJECT_DEFAULTS


def test_dependency_declarations():
    for relative_path in PROJECT_DEFAULTS:
        project_dir = JITX_PY_ROOT / relative_path.split("/", 1)[0]
        config = tomllib.loads((project_dir / "pyproject.toml").read_text())
        assert any(Requirement(dep).name == "shared-components" for dep in config["project"]["dependencies"])
        source = config["tool"]["uv"]["sources"]["shared-components"]
        assert (project_dir / source["path"]).resolve() == JITX_PY_ROOT / "shared-components"


def test_constructed_substrate_defaults():
    # Isolate each project's `src` package; inspect runtime objects, not Python spelling.
    code = """
import importlib, sys
from jitx._instantiation import instantiation
from jitx.substrate import Substrate
module = importlib.import_module(sys.argv[1])
classes = [c for c in vars(module).values() if isinstance(c, type) and issubclass(c, Substrate) and c is not Substrate]
assert len(classes) == 1
with instantiation.activate():
    substrate = classes[0]()
assert len(substrate.stackup.conductors) == int(sys.argv[2])
assert substrate.constraints.min_drill_diameter == (0.30 if sys.argv[3] == "flex" else 0.15)
assert substrate.constraints.min_copper_edge_space == (0.30 if sys.argv[3] == 'flex' else 0.20)
"""
    for path, count in PROJECT_DEFAULTS.items():
        project, module = path.split("/", 1)
        env = dict(os.environ, PYTHONPATH=os.pathsep.join((str(JITX_PY_ROOT / project), str(JITX_PY_ROOT / "shared-components/src"), str(JITX_PY_ROOT / "alchitry-v2-elements"))))
        result = subprocess.run([sys.executable, "-c", code, module[:-3].replace("/", "."), str(count), "flex" if path in FLEX_PROJECT_DEFAULTS else "rigid"], env=env, cwd=JITX_PY_ROOT / project, capture_output=True, text=True)
        assert result.returncode == 0, f"{project}: {result.stderr}"
