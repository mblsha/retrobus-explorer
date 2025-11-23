# Repository Guidelines

## Project Structure & Module Organization
- `pin-tester/`, `sharp-organizer-card/`, `sharp-pc-g850-*`, and `test-minimal/` are Alchitry Lucid projects; each includes a `<project>.alp`, `source/` modules, and `constraint/*.acf` files.
- `shared-lib/` hosts reusable Lucid blocks (e.g., UART); reference them via relative paths from project files to avoid duplication.
- `shared-constraints/` holds pin maps shared across boards; keep board-specific notes there.
- `reference/spade/src/` is a Spade language book submodule; use it for language guidance and reference designs.
- Keep generated Alchitry outputs in each project's `build/` folder; do not commit them.

## Build, Test, and Development
- Open `<project>/<project>.alp` in Alchitry Designer, select the correct board, and build/flash directly from the IDE.
- For CLI workflows, use `alchitry`/`alchitry-loader` equivalents if installed, pointing to the `.alp`; export bitstreams into the project’s `build/` folder.
- Update constraint files under `constraint/` before compiling, and keep connector naming aligned with the ports in `source/`.
- Use `pin-tester` first to validate pin mappings and level shifters before running other designs on new hardware.

## Coding Style & Naming Conventions
- Lucid: four-space indentation, `snake_case` signals, `ALL_CAPS` enums/constants; default combinational outputs to avoid unintended latches; align port names with connector labels in constraint files.
- Directory names should match project targets; keep shared modules in `shared-lib/` instead of copying into project folders.

## Testing Guidelines
- Maintain lightweight Lucid testbenches alongside designs (see `test-minimal/` for structure); simulate in Alchitry Designer or an HDL simulator before synthesis.
- For hardware validation, start with `pin-tester` bitstreams to confirm pin mappings and bank selections.
- Rebuild after any constraint, clock, or I/O width change to catch timing or mapping regressions early.

## Commit & Pull Request Guidelines
- Follow existing history: short, imperative commit titles (e.g., `Fix parse thread status reporting`), one functional change per commit.
- PRs should state scope, target board/project, and rationale; link issues; include relevant build notes (log locations, bitstream names) and call out connector or voltage-domain impacts.
- Screenshots or Saleae captures help when modifying bus behavior or timing-sensitive logic.

## Security & Configuration Tips
- Do not commit generated bitstreams, build folders, or tool logs; verify `git status` is clean before pushing.
- Keep vendor tool paths and credentials out of the repo; scrub shared logs for host or serial details.
- When adding boards, copy patterns from `shared-constraints/`, document voltage domains, and double-check reset polarity and clock sources match the hardware.
