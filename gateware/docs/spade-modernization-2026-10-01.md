# Spade source modernization review

Reviewed all nine Spade blog posts published between 2025-10-01 and
2026-10-01, proceeding from oldest to newest. The compiler was already pinned
to v0.20.0, so this pass applies source improvements with that compiler.
The baseline is RetroBus Explorer commit `089014c`.

## Posts in chronological order

| Date | Post | Application to this repository |
| --- | --- | --- |
| 2025-11-10 | [Quickscope](https://blog.spade-lang.org/quickscope/) | Its compositional stream example prompted a review of the USB/Ethernet connections. Six long instantiations in `server.spade` now use named arguments, making request and reply endpoint directions explicit. The existing service handshake stays in place; adding another ready/valid library offers no benefit here. |
| 2025-11-20 | [Spade 0.15.0](https://blog.spade-lang.org/v0-15-0/) | Audited lambda syntax, captures, array `zip`, pipeline methods and unsafe conversions. Lambdas already use `fn |...|`, and paired CRC/pin arrays already use `zip`. No additional pipeline stage or unsafe cast was needed. |
| 2025-12-15 | [Processor for Advent of Code](https://blog.spade-lang.org/processor-for-aoc/) | Reviewed enum exhaustiveness and array labels. UART state machines already use enums. This code has no instruction ROM with branch offsets to replace with labels; packet opcodes and packed diagnostic state codes retain their specified numeric encodings. |
| 2026-01-22 | [Spade 0.16.0](https://blog.spade-lang.org/v0-16-0/) | Replaced the arbiter's transition chain with a guarded `match`. Existing grouped imports, tuple fields and ASCII byte literals already use the release's syntax. The arbiter retains its two-bit state values and release timing. |
| 2026-03-05 | [Spade 0.17.0](https://blog.spade-lang.org/v0-17-0/) | Added a private `Connection<T>` alias for the repeated readable/driven endpoint pairs. USB baud ports reuse the shared `BitTime` alias. Inlined the two one-expression TX request constructors while retaining their public names. Wrapping arithmetic, generic defaults and `if let` were already used where appropriate. |
| 2026-04-15 | [Spade 0.18.0](https://blog.spade-lang.org/v0-18-0/) | Replaced 43 deprecated `.to_bits()`/array `.to_uint()` calls with `.as_bits()`/`.as_uint()` in 14 source files. These operations reinterpret bits. The port/value migration and ordinary struct syntax were already complete. |
| 2026-05-28 | [Spade 0.19.0](https://blog.spade-lang.org/v0-19-0/) | Added `Default` implementations for the private UART TX register and RX capture types, so reset values belong to their types. All endpoint creation already uses `port()`. No external ROM asset needed `include_bytes!`, and no new dependency was needed from Reef. |
| 2026-08-20 | [Spade 0.20.0](https://blog.spade-lang.org/v0-20-0/) | The default implementations use static `fn default()` constructors. Generic associated calls remain unsupported, so the typed registers use the standard `default()` dispatcher. All 14 compiler pins and the installed Swim already support this release. |
| 2026-09-18 | [Move to Codeberg](https://blog.spade-lang.org/moving-to-codeberg/) | Verified all 14 cached compiler origins are Codeberg and Swim is `v0.20.0-r351-c88f2f4`. No cache deletion or unpinned compiler update was needed. Historical source URLs remain historical provenance. |

## Verification

Before refactoring the control logic, the focused baseline covered serial framing,
the arbiter, the block service, message streaming and the 8- and 16-bit UART
paths. A new arbiter characterization passed against the original transition
chain: queued transports alternate, the busy owner stays selected, and the
three-cycle release/acquisition gap remains intact.

After the cleanup:

- All 14 workspaces built with zero Spade warnings.
- All 20 Cocotb/Verilator suites passed: seven focused suites and every one
  of the 13 registered projects. The runner required nonempty JUnit results
  with no failures or errors.
- `sv_module_surface.py` reported the same observable interfaces in all
  14 before/after generated HDL files.
- `sv_module_bodies.py --loose` accounted for the expected constructor,
  inline-helper, arbiter-body and generated build-metadata differences. The
  application connection rewrite and conversion spellings did not introduce
  additional body changes.
- Yosys proved before/after equivalence for `request_arbiter`, `tb_uart_tx`,
  `tb_uart_rx` and `tb_uart_rx_u16`. Compiler-generated temporary names were
  hidden before matching; state registers and output comparisons remained.

The generic default dispatcher adds constant helper modules; inlining the TX
request constructors removes two helpers. The resulting net change is two
modules in most generated designs. Formal checks confirmed the UART reset
and arbiter refactors preserve behavior; the public interfaces are unchanged.

## Maintenance notes

Deprecated methods do not reliably emit warnings in v0.20.0. After a compiler
upgrade, search explicitly for old method spellings as well as reading the
compiler warnings. Review the receiver type before replacing a `to_*` method:
numerical conversions and bit reinterpretations have different meanings.

Keep the limitations in [the compiler issue record](spade-compiler-issues.md)
in mind, particularly generic associated calls, struct-member type expressions
and array-pattern widths. This pass does not remove those workarounds.

No bitstream was rebuilt or programmed during this source cleanup. Both the
historical H700 artifact and the USB-qualified candidate retained their exact
SHA-256 identities. The [USB qualification record](hardware/arty-usb-fallback-2026-10-01.md)
continues to describe commit `089014c` and its preserved binary; it is not a
hardware qualification of a newly routed image from the cleaned-up sources.
