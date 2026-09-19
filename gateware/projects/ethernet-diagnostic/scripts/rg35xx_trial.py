#!/usr/bin/env python3
"""Documented entry point for one standardized RG35XX Plus cold start.

The trial itself lives in `rg35xx/trial.py`; this file only makes the project
importable so the documented command line keeps working from a checkout with
nothing installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rg35xx.trial import main  # noqa: E402

if __name__ == "__main__":
    main()
