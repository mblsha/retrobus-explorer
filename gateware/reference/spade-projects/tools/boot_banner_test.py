from __future__ import annotations


def assert_boot_banner(line: bytes | str, project_name: str) -> None:
    if isinstance(line, bytes):
        text = line.decode("ascii", errors="replace")
    else:
        text = line

    assert text.startswith(f"RBXBOOT project={project_name} git="), f"unexpected boot banner: {text!r}"
    assert " dirty=" in text and " built=" in text and text.endswith("\r\n"), f"malformed boot banner: {text!r}"
