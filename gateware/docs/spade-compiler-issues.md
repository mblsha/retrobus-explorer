# Spade compiler issues we work around, and what to simplify when they are fixed

Found against Spade v0.20.0 (`7e0bf7883d8a23dff89b5e38ce5c5f24761fafe5`) during the
0.17 → 0.20 upgrade and the elegance pass of 2026-09-22. Each entry has a
reproducer that fits in one entity, the place in our sources that carries the
workaround, and the simplification that becomes possible once the compiler no
longer does this. Nothing here has been reported upstream; that is a separate
decision. After every compiler bump, re-run the reproducers (drop each one into
`projects/test-minimal/src/main.spade`, `swim build`, then lint the output with
`verilator --lint-only build/spade.sv`) and retire the entries that no longer
fail.

## 1. Array-pattern destructuring emits an index one bit too wide

**Symptom.** `let [a, b, c, d] = arr;` on a `[T; 4]` generates
`localparam[2:0]` index constants where a four-element array wants two bits.
`swim build` is silent; Verilator reports
`Bit extraction of var[3:0] requires 2 bit index, not 3 bits` (`WIDTHTRUNC`) on
every extraction, and the Cocotb builds treat that as fatal. The width is
`uint::bits_for(N)` where `uint::bits_for(N - 1)` is needed, so it bites
exactly when `N` is a power of two. A seven-element pattern is generated
correctly, and plain `arr[3]` indexing is fine.

```spade
#[no_mangle(all)]
entity main(a: [bool; 4], b: [bool; 7], x: inv bool, y: inv bool) {
    let [a0, a1, a2, a3] = a;           // [2:0] indices into a [3:0] array
    let [b0, b1, b2, b3, b4, b5, b6] = b; // correct
    set x = a0 && a3;
    set y = b0 && b6;
}
```

**Where we work around it.** `projects/sharp-organizer-card/src/main.spade`
reads `conn_core_sync[0]` … `conn_core_sync[3]` into four named `let`s (the
`conn_aux_sync` block below it has seven elements and could already be a
pattern, but the two blocks are kept alike on purpose).

**When fixed.** Both blocks become one `let [conn_rw_sync, conn_oe_sync,
conn_ci_sync, conn_e2_sync] = conn_core_sync;` each, and the eleven
`conn_*_sync` signals are then a short step from a struct that travels through
`misc_word`, `organizer_board_outputs` and `BoardRenderInputs` as one value
(~44 occurrences today).

## 2. `bits[N - 1]` inside a `gen if` recursion is typed for half the array

**Symptom.** In a recursive `gen if` over a length generic, indexing with
`N - 1` infers the index type as `uint<bits_for(N / 2 - 1)>`, so a 40-element
array fails with `Integer value does not fit in int<5> -- 40 does not fit in an
uint<5>` and an 8-element one with `uint<2>`.

```spade
#[inline]
fn walk<#uint N>(acc: bool, bits: [bool; N]) -> bool {
    gen if N == 0 { acc } else { walk(acc ^^ bits[N - 1], bits[..N - 1]) }
}
#[no_mangle(all)]
entity main(x: uint<40>, y: inv bool) {
    set y = walk(false, x.as_bits());
}
```

**Where we work around it.** `lib/shared-components/src/sd.spade`'s CRC helpers
(`crc7_over`, `crc16_over`, the `crc32` step) take the last element with
`bits.last()` and recurse on `bits[..N - 1]`.

**When fixed.** `bits.last()` is arguably the better spelling anyway, so
nothing has to change; the entry exists so nobody "simplifies" it to an index
and loses an afternoon. What does become possible is `[T; N]::fold` for the
MSB-first CRCs without the `.reversed()` that today drags eleven
`split_at`/`concat` modules into every consumer -- if `reversed` is ever made
`#[inline]` upstream, which is a separate wish.

## 3. An array repeat count cannot be a type expression

**Symptom.** `[0; {8 - N}]` is rejected with `This expression is not supported
in a type expression`; only a literal or a bare generic is accepted as the
count.

**Where we work around it.** `projects/sharp-organizer-card/src/msg.spade`,
`ChannelName` construction: `text.concat([0; 8])[..8]` pads a name to eight
bytes by over-concatenating and slicing.

**When fixed.** `text.concat([0; {8 - N}])`, and the comment above it goes.

## 4. A struct member cannot compute a width from the struct's own generic

**Symptom.** `waddr: uint<{uint::bits_for(ENTRIES - 1)}>` in a struct
declaration fails with `Struct members cannot have const generics in their
type`. Routing the same expression through a type alias
(`FifoAddr<ENTRIES>`) instead panics the compiler:
`internal error: entered unreachable code: Const generic in
type_expr_to_concrete` at `spade-typeinference/src/mir_type_lowering.rs:201`.
The same alias works in a `let` or `reg` annotation.

**Where we work around it.** `lib/shared-components/src/memory.spade`:
`FifoImplState<ADDR_W, COUNT_W, WIDTH, ENTRIES>` carries two size-only generics
that are functions of `ENTRIES`, and the `FifoState<WIDTH, ENTRIES>` alias ties
them back together at the one `reg` that holds the state.
`lib/shared-components/src/boot_banner.spade`: `BootBannerState<IDX_W>` likewise.

**When fixed.** `FifoImplState<WIDTH, ENTRIES>` with `uint<FifoAddr<ENTRIES>>`
members, `BootBannerState<N>` computing its own index width, the `FifoState`
alias deleted, and every `impl` and call site that spells out `ADDR_W`/`COUNT_W`
loses two arguments.

## 5. A `where` clause cannot say "power of two"

**Symptom.** Not a bug, a limit: a constraint takes a bare generic on the left
and the type-expression language has no shift or exponentiation
(`Operator '<<' is not supported in a type expression`; braced
`{1 << …}` → `This expression is not supported in a type expression`;
`uint::bits_for(N - 1) < …` on the left → `Unexpected '('`).

**Where we work around it.** `lib/shared-components/src/guards.spade`:
`require_power_of_two::<N>()`, an `#[inline]` unit whose body fails to
monomorphise for a non-power-of-two, called from `memory.spade` and
`serial.spade` as `let _ = require_power_of_two::<ENTRIES>();`.

**When fixed.** `where N == {1 << uint::bits_for(N - 1)} else "… must be a
power of two"` beside the generic, `guards.spade` deleted, and the `let _ =`
lines with it. A private extra generic on `fifo_impl` could carry the check
today, but `async_fifo`, `sync_fifo` and `ft` are public and cannot, so it
would only make the library inconsistent; wait for the language.

## 6. Deprecated methods do not warn

**Symptom.** `#[deprecated]` on a free unit prints a warning with a fix-it;
the same attribute on a method (`uint<N>::to_bits`, `[bool; N]::to_uint`)
prints nothing. Forty-nine `to_bits()` calls outlived the 0.18 bump in a tree
that requires zero warnings and were found by grep in the elegance pass.

**Where we work around it.** `AGENTS.md`'s bump procedure: after the warnings
are at zero, grep for every method the changelog retires.

**When fixed.** Drop that sentence; the warnings are the list again.

## 7. `msb`, `lsb`, `unwrap_or`, `concat`, `shift_front`, `push_front`, `reversed`, `default` are not `#[inline]`

**Symptom.** Each is a one-line forwarding call or a transmute in the standard
library, and each monomorphisation is a module in every project that reaches
it. That is the whole of the module-count growth the elegance pass reports
(`ethernet-diagnostic` 266 → 281, `sharp-pc-e500-card` 351 → 355).
`std::default::default` is the same shape (`T::default()`) and is the only way
to reach a `Default` impl on a generic type, because naming that type's
associated function is rejected ("Use of undeclared name
...BootBannerState::default"); the seven projects with a boot banner each carry
a module for it; the impl it forwards to is `#[inline]`, so the count is the
same as the free constructor it replaced rather than one higher.

**Where we work around it.** We use `msb()`/`lsb()`/`unwrap_or()` where the
name is worth a module and index by hand where it is not (see AGENTS.md); the
reset conditioner keeps `[false].concat(stages[..STAGES - 1])` instead of
`shift_front`; the CRCs are hand-written `gen if` recursions instead of
`fold` over `reversed()`. `boot_banner_core` pays the `default` module to let
`BootBannerState` carry its own reset value like every other state record, and
keeps its own `Default` impl `#[inline]` so that is the only module it pays.

**When fixed.** `reset_conditioner` uses `shift_front`; the CRC helpers become
`bits.reversed().fold(…)` one-liners; the module counts fall back to where
they were, and the "not worth it inside something instantiated many times"
caveat in AGENTS.md can go.

## 8. Editing one file renames a register in another module's SystemVerilog

**Symptom.** A change confined to `projects/microsd-emulator/src/storage.spade`
turned `sd_write_response`'s `state` register into `\_` with an
`assign \state = \_;` beside it, although `write_response.spade` was untouched.
Reverting `storage.spade` undoes it. It is the alias-flattening pass choosing
which of two aliased nets holds the `reg`, sensitive to global expression
numbering. Harmless: both nets exist and the value is right.

**Where we work around it.** `tools/sv_module_bodies.py --loose` alpha-renames
nets before comparing, so the accounting is not fooled. Its `--loose` does not
rename module *port* names, so a free function moved into an `impl`
(`state_i` → `self_i`) still shows as a difference and has to be read by hand.

**When fixed.** Nothing in the sources changes; a cross-module body comparison
stops needing `--loose` for this case. Teaching `--loose` to rename ports is
our own tooling gap and is independent of the compiler.

## 9. `swim build` rewrites `src/build_info.spade` on every build

**Symptom.** Not a compiler issue but the trap that costs the most wall-clock:
every project's `preprocessing` step regenerates `src/build_info.spade` with a
fresh timestamp, and the project's Cocotb suite compares the boot banner
against that file at import time. Building anything in a project while its
suite runs fails every test after the first on the banner, with no hint why.

**Where we work around it.** Never build in a checkout while its suites run;
the elegance pass gave each agent its own worktree for that reason.

**When fixed.** If swim ever gains a way to run preprocessing only when a source
changed, or the banner test learns to read the timestamp it was built with,
concurrent build-and-test in one checkout becomes safe again.
