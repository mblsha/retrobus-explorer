from __future__ import annotations

import re


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines: list[str] = []
    for line in text.splitlines():
        lines.append(line.split("//", 1)[0])
    return "\n".join(lines)
