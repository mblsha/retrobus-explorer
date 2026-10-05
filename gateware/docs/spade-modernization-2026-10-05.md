# Spade modernization follow-up: organizer tooling and reusable FT600 blocks

The [2026-10-01 review](spade-modernization-2026-10-01.md) is the year-of-Spade
release checklist. It maps nine posts to the syntax and library changes already
applied across the workspace. This follow-up covers the organizer projects
added since that review and the FT UART bridge that shares their transport.

The pre-cleanup snapshot is commit **`4f896e7`**. All compiler pins remain at
Spade v0.20.0 (`7e0bf7883d8a23dff89b5e38ce5c5f24761fafe5`). Associated
constructors and their generic limitation are described in the
[0.20 release notes](https://blog.spade-lang.org/v0-20-0/); the existing
[compiler issue record](spade-compiler-issues.md) tracks the workarounds.

## Audit and applied changes

- [x] Search every Spade source for retired conversion methods, width helpers,
  `concat_arrays`, and `struct port`. None remain. Existing `to_*` operations
  that preserve numeric values are distinct from bit reinterpretations.
- [x] Keep the modern `port()`, `inv`, `.as_bits()` / `.as_uint()`, typed
  defaults, and generic `where` constraints already in use.
- [x] Give the organizer emulator's memory, bus, UART and FT600 connections
  named arguments, exposing the direction and meaning of long endpoint lists.
- [x] Express its UART parser transitions with a guarded `match`. Its numeric
  phases, dispatch/reply wait cycles and timeout priority retain their meaning.
- [x] Spell the UART's ASCII command opcodes as byte literals (`b'R'`, `b'W'`,
  etc.), matching the documented protocol directly.
- [x] Extract FT600 word packing and byte consumption into `ft_rx.spade`.
  Both the FT UART bridge and organizer emulator use the same 18-bit packing.
- [x] Extract the emulator's complete-record serializer into `ft_records.spade`.
  Its word count has a literal default, width expressions and a checked lower
  bound; a 96-bit test exercises a non-power-of-two count alongside 128 bits.

## Reusable interfaces

| Module | Interface | Responsibility |
| --- | --- | --- |
| [ft_rx.spade](../lib/shared-components/src/ft_rx.spade) | `PackedFtWord`, `pack_ft_word`, `unpack_ft_word`, `unpack_ft_be` | Retain 16 data bits and both physical byte enables through a FIFO |
| [ft_rx.spade](../lib/shared-components/src/ft_rx.spade) | `ft_rx_byte_step(high, packed, empty, consume)` | Present enabled bytes low-first; return the next cursor and a FIFO pop |
| [ft_records.spade](../lib/shared-components/src/ft_records.spade) | `ft_record_stream<WORDS = 4>` | Serialize a held multiword FIFO record as 16-bit FT600 transfers |

`consume` must be a one-clock event. A held processor read must be qualified
by the application before it reaches the byte cursor. Empty input produces
zero; BE=00 requests a discard. The caller holds the cursor register and owns
FIFO fullness and underflow accounting.

The record serializer expects the current FIFO head to remain available until
`pop_record`. It pops on acceptance of the final 32-bit word's low half, then
the existing `ft_word_stream_step` retains its high half through any stall.
`valid` is an accepted-transfer pulse when the sink is ready. WORDS must be
at least two; a one-word stream uses `ft_word_stream_step` directly. Record
layout, capture/drop policy and clock crossing belong to the application.

The small packing/cursor helpers and record composition are `#[inline]`.
The extraction uses the existing shared word serializer, synchronizers, FIFOs,
UART and FT245 boundary rather than adding another transport protocol.

## Verification

Before source changes, the existing organizer emulator suite passed all seven
tests and the FT UART bridge passed all five tests. Generated HDL was retained
for interface and body comparisons.

Focused shared cases:

```sh
uv run --frozen --no-sync python lib/shared-components/scripts/test_component.py ft_rx_bytes
uv run --frozen --no-sync python lib/shared-components/scripts/test_component.py ft_records128
uv run --frozen --no-sync python lib/shared-components/scripts/test_component.py ft_records96
```

These cover enabled-byte order, paused consumption, BE=00, empty reads,
mid-word reset, record ordering, the exact FIFO-pop boundary, stalls between
halfwords, and mid-record reset. An invalid `WORDS = 1` instantiation is
rejected with the intended generic-constraint message.

After the cleanup:

- All 15 registered projects and the shared library built sequentially with
  zero Spade warnings. All 16 compiler locks retain the same release pin.
- All three focused shared tests passed.
- All seven organizer emulator tests and five FT UART bridge tests passed
  again, including UART timeout, held bus reads, bidirectional traffic,
  buffering/drop counters, SRAM writes and guarded runtime uploads.
- Inventory tests (3) and CI matrix/discovery tests (6) passed. The new shared
  cases are discovered automatically by the CI planner.
- `sv_module_surface.py` showed identical existing interfaces and external
  HDL parameters. Its only additions were the three new focused test tops.
- `sv_module_bodies.py --loose` confined existing-body changes to the
  emulator's command link, transport and main integration, and the bridge's
  message selection and main integration. These account for the guarded
  parser transition logic, record cursor and inlined FT word packing. The
  bridge's three former packing/unpacking modules were removed.

Run the affected integration suites from `gateware/`:

```sh
uv run --frozen --no-sync python tools/run_tb.py --project projects/sharp-organizer-emulator
uv run --frozen --no-sync python tools/run_tb.py --project projects/ft-uart-hex-bridge
```

The binary image identified in the emulator's
[initial qualification record](../projects/sharp-organizer-emulator/QUALIFICATION.md)
predates this cleanup. Verification here compiles and simulates the updated
source; it does not establish post-route timing for a new bitstream.

## Remaining compiler-dependent simplifications

Use [spade-compiler-issues.md](spade-compiler-issues.md) as the remaining list:
generic associated constructors, widths derived from a struct's own generic,
array-pattern index widths, array-repeat type expressions, and power-of-two
constraints still limit some simplifications. The standard library's helper
module costs also remain relevant when a block is instantiated many times.

The next compiler bump should repeat the explicit deprecated-method search,
the issue reproducers and affected tests. A newly routed image needs its own
timing and hardware qualification; this cleanup does not change the retained
qualified hardware artifacts.
