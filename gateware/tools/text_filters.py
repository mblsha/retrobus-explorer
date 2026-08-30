from __future__ import annotations


def _strip_line_comment(line: str) -> str:
    in_double_quote = False
    in_single_quote = False
    escaped = False

    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue

        if ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            continue
        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            continue

        if ch == "/" and not in_double_quote and not in_single_quote:
            if idx + 1 < len(line) and line[idx + 1] == "/":
                return line[:idx]

    return line


def strip_comments(text: str) -> str:
    out_chars: list[str] = []
    i = 0
    in_block_comment = False
    in_double_quote = False
    in_single_quote = False
    escaped = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            if ch == "\n":
                out_chars.append("\n")
            i += 1
            continue

        if escaped:
            out_chars.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            out_chars.append(ch)
            escaped = True
            i += 1
            continue

        if ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            out_chars.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            out_chars.append(ch)
            i += 1
            continue

        if not in_double_quote and not in_single_quote and ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        out_chars.append(ch)
        i += 1

    stripped_text = "".join(out_chars)
    lines: list[str] = []
    for line in stripped_text.splitlines():
        lines.append(_strip_line_comment(line))
    result = "\n".join(lines)
    if stripped_text.endswith("\n"):
        result += "\n"
    return result
