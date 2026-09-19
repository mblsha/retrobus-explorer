from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

GATEWARE = Path(__file__).resolve().parents[1]

# Always importable wherever a testbench runs; deferring these hides nothing.
ALWAYS_PRESENT = sys.stdlib_module_names | {"cocotb"}


def imported_modules(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module and not node.level:
        return [node.module.split(".")[0]]
    return []


def deferred_first_imports(source: str) -> list[tuple[int, str]]:
    """Modules a testbench file first imports inside a function body.

    Cocotb imports the test module before the simulation starts, so a missing
    name at module scope stops the whole bench at once with its ImportError. The
    same import inside a coroutine raises only when that line is reached, as one
    test failing at some simulation time, and the JUnit file keeps no traceback.
    """
    tree = ast.parse(source)
    at_load: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for node in ast.walk(statement):
            at_load.update(imported_modules(node))
    deferred: list[tuple[int, str]] = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            for module in imported_modules(node):
                if module not in ALWAYS_PRESENT and module not in at_load:
                    deferred.append((node.lineno, module))
    return sorted(set(deferred))


class DeferredFirstImportsTest(unittest.TestCase):
    def test_flags_a_helper_first_imported_inside_a_coroutine(self) -> None:
        source = (
            "import cocotb\n"
            "async def init(writable):\n"
            "    if writable:\n"
            "        from sd_csd import SD_CSD\n"
        )
        self.assertEqual(deferred_first_imports(source), [(4, "sd_csd")])

    def test_accepts_what_module_scope_has_already_resolved(self) -> None:
        source = (
            "from microsd_probe import decode\n"
            "async def check():\n"
            "    import struct\n"
            "    from cocotb.triggers import Timer\n"
            "    from microsd_probe import crc8\n"
        )
        self.assertEqual(deferred_first_imports(source), [])

    def test_registered_testbenches_resolve_their_helpers_at_load(self) -> None:
        offenders = [
            f"{path.relative_to(GATEWARE)}:{line}: {module}"
            for pattern in ("projects/*/test/*.py", "lib/*/test/*.py")
            for path in sorted(GATEWARE.glob(pattern))
            for line, module in deferred_first_imports(path.read_text())
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
