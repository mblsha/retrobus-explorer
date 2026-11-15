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

Re-checked against v0.21.0 (`423b451b3ed90cd004b6ebd9aae045109c62087b`) on
2026-11-15. Entries 1, 2, 3, 6 and 7 still reproduce (6 with
`[bool; 8].to_uint()`, deprecated in favour of `as_uint` and silent). Entries
4 and 5 are fixed, and their workarounds are gone. Entry 10 is new in 0.21.
Lint a reproducer with `--top-module main`: the
shared-components library brings in SystemVerilog externs that a whole-file
lint cannot find.

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

v0.21.0 still rejects it, and the new `const type { 8 - N }` expression is
rejected in the same place. What does work is a second generic that a `where`
clause ties to `N` (`fn pad<#uint N, #uint M>(…) where M == 8 - N` with
`[0; M]`), but every caller then has to spell `pad::<_, _>` or name both, which
is worse than the over-concatenation.

**When fixed.** `text.concat([0; {8 - N}])`, and the comment above it goes.

## 4. Retired in v0.21.0: a struct member could not compute a width from the struct's own generic

v0.20.0 rejected `waddr: uint<{uint::bits_for(ENTRIES - 1)}>` in a struct
("Struct members cannot have const generics in their type") and panicked on the
alias spelling. v0.21.0 accepts both. `FifoImplState<WIDTH, ENTRIES>` and
`FifoUsed<WIDTH, ENTRIES>` now compute their own widths, the `FifoState` alias
and the `FifoUsedOut<TData, TUsed>` indirection are gone, and
`BootBannerState<N>` takes the banner length instead of an `IDX_W` every caller
had to pass. That last one is not netlist-neutral: every banner caller passed
`IDX_W = 8` for an 84- to 103-byte banner, so the index register is now the
seven bits `uint::bits_for(N - 1)` asks for. Its top bit was always zero.

## 5. Retired in v0.21.0: a `where` clause could not say "power of two"

v0.21.0 adds `<<` to type expressions. The check reads as a comparison, so the
compiler quotes its message:
`ENTRIES >= 1 << uint::bits_for(ENTRIES - 1) else "... must be a power of two"`
(`1 << bits_for(N - 1)` is never below `N` and equals it exactly at a power of
two). `where N == 1 << …` also compiles but *unifies* instead of checking, and
reports a bare "Expected type 6, got 8" without the message, so use `>=`.
`guards.spade` and its `let _ = require_power_of_two::<…>()` lines are gone.

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

## 10. A local named `core` breaks the compiler's own `core::ops` paths

**Symptom.** New in v0.21.0. Any unit that binds a local called `core` fails to
compile, because the paths the compiler generates for operators and `inst`
(`core::ops::…`) resolve against the local instead of the `core` crate. The
error has no useful location:
`Use of undeclared name <module>::core::ops`, pointing at `<str>:1:1`.

```spade
#[no_mangle(all)]
entity main(a: uint<8>, y: inv uint<8>) {
    let core = a;
    set y = trunc(core + 1);
}
```

**Where we work around it.** `lib/shared-components/src/harness.spade`'s
`tb_uart_tx_tap_equiv` named its reference transmitter `core_tx`, not `core`.

**When fixed.** Nothing has to change back; the entry is here so that the
next person who sees that error knows to look for a `core` binding.

A related collision is a language change, not a bug: `memory` is a keyword in
v0.21.0 (the memory declaration), so it can name neither a module nor a local.
The shared FIFO module became `fifos`, `ethernet-diagnostic`'s frame buffers
became `frames`, and `tb_card_memory`'s instance became `card`.
