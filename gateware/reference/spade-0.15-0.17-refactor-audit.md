# Spade 0.15–0.17 refactor audit

This document turns the official Spade 0.15.0, 0.16.0, and 0.17.0 release notes into a practical project-audit guide.

It is **not** a changelog rewrite. It is a list of **refactors worth hunting for in an existing codebase** because they make the code cleaner, safer, more expressive, or easier to evolve.

> Notes:
> - The **before** snippets are representative patterns to search for in real code; they are not meant to be literal copies of your code.
> - The **after** snippets show the newer, cleaner style enabled by these releases.
> - I focused on **language/library ergonomics** rather than compiler-performance or packaging changes.

## Quick grep queue

If you want a fast first pass, search for these patterns:

- `tuple#`
- `Fn((`
- `trunc(`
- `match` blocks that only unwrap `Some(...)` / one enum variant
- `inst(` with duplicated literal pipeline depths
- `read_read_port`, `write_*port`, or free functions whose first argument is conceptually the receiver
- `set ` assignments where the RHS is not explicitly turned into a wire
- hard-coded instruction offsets / branch targets
- numeric byte arrays for human-readable text
- helper traits/functions with extra type parameters like `Out` that only exist to express `N + 1`
- tiny wrapper units around black boxes just to inject attributes or rename awkward ports

## Highest-value audits first

If you only do a handful of migrations, start with these:

1. Modernize lambdas and use captures
2. Replace manual validity plumbing with pipeline lambdas and `pmap`
3. Convert helper APIs into methods and use `inst(_)`
4. Add visibility boundaries and clean imports
5. Replace `trunc(...)`-heavy arithmetic with wrapping operators
6. Collapse verbose enum unwrapping into `if let` / match guards
7. Simplify generic signatures with type expressions and `impl Trait`
8. Replace magic numeric bytes / branch offsets with ASCII literals and array labels

---

## 1) Modernize lambdas and use captures (0.15)

**High-level explanation**

Spade 0.15 made lambdas more useful in real code by allowing them to **capture values from their environment**, and it also changed the lambda syntax to the more compact `fn |args|` form. This is a great excuse to audit places where you manually unwrap `Option`, manually thread local context into helper functions, or still use the older lambda syntax. [0.15]

**Before**

```spade
fn fir_filter(x: Option<uint<8>>, n: uint<8>) -> Option<uint<9>> {
  match x {
    Some(x) => Some(x + n),
    None => None
  }
}
```

**After**

```spade
fn fir_filter(x: Option<uint<8>>, n: uint<8>) -> Option<uint<9>> {
  x.map(fn |x| { x + n })
}
```

**Why this is awesome**

The transform now lives exactly where it is used. That removes boilerplate `match` blocks, avoids “one-use helper function” clutter, and makes combinator-heavy code feel much more natural. It also nudges code toward a cleaner “describe the transformation” style instead of “manually forward every case.” [0.15]

---

## 2) Replace manual validity plumbing with pipeline lambdas and `pmap` (0.15)

**High-level explanation**

Spade 0.15 lets lambdas themselves be pipelines, and the standard library gained `Option::pmap`, which behaves like `map` but for pipelines. This is a high-ROI refactor for code that manually preserves `Some`/`None` across multi-cycle transforms. [0.15]

**Before**

```spade
pipeline(3) mul_pipe(x: int<18>, y: int<18>) -> int<36> {
  let result = x * y;
reg * 3;
  result
}

pipeline(3) pipelined_multiplier(val: Option<(int<18>, int<18>)>) -> Option<int<36>> {
  match val {
    Some((x, y)) => Some(inst(3) mul_pipe(x, y)),
    None => None
  }
}
```

**After**

```spade
pipeline(3) pipelined_multiplier(val: Option<(int<18>, int<18>)>) -> Option<int<36>> {
  val
    .inst(_) pmap(pipeline(3) |(x, y)| {
      let result = x * y;
    reg * 3;
      result
    })
}
```

**Why this is awesome**

You stop writing wrapper pipelines whose only job is “preserve validity while doing work.” The valid/invalid behavior stays attached to the transformation itself, and `inst(_)` removes one more duplicated latency literal that can silently rot when the pipeline depth changes. [0.15]

---

## 3) Turn helper pipelines/functions into methods, especially around memory ports (0.15)

**High-level explanation**

Spade 0.15 added **pipeline methods**, and the standard library moved memory ports toward `.read` / `.write` methods instead of older free-function helpers. Audit APIs where the first parameter is conceptually “the thing being acted on.” Those are strong candidates to become methods. [0.15]

**Before**

```spade
inst(1) read_memory(clk, read_port)
```

**After**

```spade
read_port
  .inst(1) read(clk)
```

**Why this is awesome**

Methods make call sites read left-to-right in the order you think about them: “this port, then read from it.” They also compose better in chains and make APIs feel more uniform. This is one of the easiest ways to make a hardware codebase feel less like a pile of helper functions and more like a coherent library. [0.15]

---

## 4) Make latency literals self-healing with `inst(_)` (0.15)

**High-level explanation**

Spade 0.15 can infer pipeline depth with `inst(_)`. Audit any place where the instantiation depth is repeated at the call site even though the callee already defines that latency. [0.15]

**Before**

```spade
let y = inst(3) stage3_filter(clk, x);
```

**After**

```spade
let y = inst(_) stage3_filter(clk, x);
```

**Why this is awesome**

Literal latencies duplicated at the call site are classic maintenance traps. As soon as a pipeline changes from 3 to 4 stages, the stale literal becomes a bug magnet. `inst(_)` removes a whole class of “the code compiled but the intent drifted” problems. [0.15]

---

## 5) Fence dangerous bit-level tricks with `unsafe` (0.15)

**High-level explanation**

Spade 0.15 introduced an `unsafe` keyword for units and `unsafe { ... }` blocks for calls. Audit any code that reinterprets bits, bypasses type guarantees, or previously lived in “dangerous helper” namespaces. [0.15]

**Before**

```spade
use std::unsafe::transmute;

let reinterpreted: uint<16> = transmute((a, b));
```

**After**

```spade
unsafe fn bytes_as_u16<T>(t: T) -> uint<16> {
  transmute(t)
}

let reinterpreted: uint<16> = unsafe { bytes_as_u16((a, b)) };
```

**Why this is awesome**

Unsafe behavior becomes visually loud and trivially searchable. That is exactly what you want for auditability: the scary parts are still possible, but they stop blending into ordinary code. [0.15]

---

## 6) Patch `set` to use explicit wires on the RHS (0.15)

**High-level explanation**

Spade 0.15 changed `set` so the right-hand side must be a wire. This is partly a migration item and partly an elegance win: code becomes more explicit about when a value is turned into a wire. [0.15]

**Before**

```spade
set self.addr = addr;
```

**After**

```spade
set self.addr = &addr;
```

**Why this is awesome**

The new style makes the distinction between **values** and **wires** impossible to miss. Even where this feels slightly more verbose, the resulting code is clearer about signal flow, and the release notes explicitly call out that this change enables `set` on `inv clock` as well. [0.15]

---

## 7) Add visibility boundaries with `pub` and `pub(lib)` (0.16)

**High-level explanation**

Spade 0.16 added visibility markers like `pub` and `pub(lib)`. Audit any library-style modules whose helpers, internal enums, or utility units are currently as visible as the public API. [0.16]

**Before**

```spade
struct DecoderState { ... }
fn decode_inner(...) -> ... { ... }
fn decode_step(...) -> ... { ... }
entity decoder(...) -> ... { ... }
```

**After**

```spade
pub struct DecoderState { ... }

pub entity decoder(...) -> ... { ... }

pub(lib) fn decode_inner(...) -> ... { ... }
fn decode_step(...) -> ... { ... }
```

**Why this is awesome**

It becomes much easier to tell which pieces are stable API and which are implementation detail. That reduces accidental coupling between modules and gives you freedom to refactor internals later without breaking downstream code. [0.16]

---

## 8) Collapse noisy imports and use `self` / `super` in namespaces (0.16)

**High-level explanation**

Spade 0.16 improved the import system so a single `use` statement can bring in multiple items, and namespace paths can use `self` and `super`. Audit modules with long stacks of repetitive imports or deeply repeated namespace prefixes. [0.16]

**Before**

```spade
use std::array::zip;
use std::array::interleave_arrays;
use std::conv::transmute;

use my_lib::packet::decode::Frame;
use my_lib::packet::decode::Header;
```

**After**

```spade
use std::{array::{zip, interleave_arrays}, conv::transmute};
use super::decode::{Frame, Header};
```

**Why this is awesome**

The namespace structure becomes visible at a glance. You spend less time scanning duplicated prefixes and more time seeing the handful of things the module actually depends on. [0.16]

---

## 9) Use match guards and `Self::...` to flatten impl code (0.16)

**High-level explanation**

Spade 0.16 added **match conditionals** and broadened where `Self` can be used inside impl blocks. Audit impls that repeat the type name in every branch or use nested `if` expressions inside `match` arms. [0.16]

**Before**

```spade
impl Option<uint<8>> {
  fn inner_is_even(self) -> bool {
    match self {
      Some(val) => if val & 1 == 1 { true } else { false },
      None => false
    }
  }
}

impl Thing<uint<8>> {
  fn inner_eq(self, val: uint<8>) -> bool {
    match self {
      Thing::A => false,
      Thing::B(inner) => inner == val
    }
  }
}
```

**After**

```spade
impl Option<uint<8>> {
  fn inner_is_even(self) -> bool {
    match self {
      Some(val) if val & 1 == 1 => true,
      Some(_) => false,
      None => false
    }
  }
}

impl Thing<uint<8>> {
  fn inner_eq(self, val: uint<8>) -> bool {
    match self {
      Self::A => false,
      Self::B(inner) => inner == val
    }
  }
}
```

**Why this is awesome**

Control flow gets flatter, branches say exactly when they apply, and `Self::...` removes a bunch of repetitive type noise. The result reads more like the logic you meant and less like syntax you had to appease. [0.16]

---

## 10) Let computed widths appear directly in signatures (0.16)

**High-level explanation**

Spade 0.16 lifted a restriction that previously forced extra type variables just to describe type-level expressions like `N + 1`. Audit array helpers and generic APIs that carry “helper” generics whose only purpose is expressing a computed output size. [0.16]

**Before**

```spade
impl<T, #uint N> [T; N] {
  fn append<#uint Out>(self, new: T) -> [T; Out]
  where Out: {N + 1}
  {
    self.concat([new])
  }
}
```

**After**

```spade
impl<T, #uint N> [T; N] {
  fn append(self, new: T) -> [T; {N + 1}] {
    self.concat([new])
  }
}
```

**Why this is awesome**

The signature finally says the real contract directly: appending to `[T; N]` returns `[T; N + 1]`. Removing “administrative generics” is one of the best ways to make generic code stop feeling ceremonial. [0.16]

---

## 11) Do the syntax cleanup pass: modern `Fn(...) -> ...` and dot-style tuple indexing (0.16)

**High-level explanation**

Spade 0.16 introduced cleaner function-trait syntax and moved tuple indexing to `tuple.0`-style access. The release notes describe these as migration-friendly syntax changes, so this is a perfect low-risk cleanup pass. [0.16]

**Before**

```spade
type Mapper = Fn((uint<8>, bool), uint<9>);
let left = pair#0;
```

**After**

```spade
type Mapper = Fn(uint<8>, bool) -> uint<9>;
let left = pair.0;
```

**Why this is awesome**

These are small changes, but they remove “legacy syntax smell” from a codebase. Signatures become easier to read, tuple access looks more familiar, and future contributors have fewer oddities to mentally translate. [0.16]

---

## 12) Replace `trunc(...)`-heavy arithmetic with wrapping operators (0.17)

**High-level explanation**

Spade 0.17 added wrapping operators like `+.` that keep the existing width instead of growing it. Audit counters, address arithmetic, hash-style mixing, and other places where you currently write `trunc(x + y)` just to get wrapping behavior. [0.17]

**Before**

```spade
reg(clk) value = trunc(value + 1);
```

**After**

```spade
reg(clk) value = value +. 1;
```

**Why this is awesome**

This is one of the clearest readability wins in the whole set of releases. The code now states the intended arithmetic mode directly instead of encoding it as “do normal arithmetic, then throw bits away.” [0.17]

---

## 13) Overload operators for genuinely algebraic domain types (0.17)

**High-level explanation**

Spade 0.17 added operator overloading for many operators. Audit domain types that already behave like numbers, vectors, masks, bitsets, or ordered values. Those are the sweet spot. [0.17]

**Before**

```spade
impl Vec2<uint<8>> {
  fn add(self, other: Self) -> Self {
    Vec2(
      self.x +. other.x,
      self.y +. other.y
    )
  }
}

let out = a.add(b);
```

**After**

```spade
struct Vec2<T> {
  x: T,
  y: T,
}

impl<T: WrappingAdd> WrappingAdd for Vec2<T> {
  fn wrapping_add(self, other: Self) -> Self {
    Vec2(
      self.x +. other.x,
      self.y +. other.y
    )
  }
}

let out = a +. b;
```

**Why this is awesome**

Good operator overloading makes APIs read like the math they model. It is especially compelling for tiny value types where method names add noise without adding meaning. The key is restraint: use it for truly operator-shaped semantics, not arbitrary business logic. [0.17]

---

## 14) Replace extra generic plumbing with `impl Trait`, return-position type expressions, and default type parameters (0.17)

**High-level explanation**

Spade 0.17 lets you write `impl Trait` in parameter position, use type expressions directly in return position, and define default type parameters. Audit generic functions whose signatures are bloated by helper parameters like `Op`, `Out`, or “default-valued but always written” generics. [0.17]

**Before**

```spade
fn growing_op<#uint N, #uint Out, Op>(x: int<8>, op: Op) -> int<Out>
where Out: {N + 1},
      Op: Fn(int<N>) -> int<Out>
{
  // ...
}

fn two_type_params<#uint N, #uint M>()
// ...
two_type_params::<10, 0>()
```

**After**

```spade
fn growing_op<#uint N>(x: int<8>, op: impl Fn(int<N>) -> int<{N + 1}>) -> int<{N + 1}> {
  // ...
}

fn two_type_params<#uint N, #uint M: 0>()
// ...
two_type_params::<10>()
```

**Why this is awesome**

This is a direct attack on generic boilerplate. The function surface becomes shorter while preserving the exact type-level meaning, and call sites become less noisy when a generic almost always has the same default. [0.17]

---

## 15) Replace single-variant `match` blocks with `if let`, and use `name @ pattern` when you need both the whole value and its parts (0.17)

**High-level explanation**

Spade 0.17 added `if let` and `name @ pattern`. Audit any enum-heavy code where `match` is only unwrapping one case, or where you destructure a value and then rebuild it because you also needed the original whole thing. [0.17]

**Before**

```spade
let unwrapped = match value {
  Some(val) => {
    compute(val)
  },
  _ => 0
};

match maybe_tuple {
  Some((left, right)) => if left == right { Some((left, right)) } else { None },
  None => None
}
```

**After**

```spade
let unwrapped = if let Some(val) = value {
  compute(val)
} else {
  0
};

match maybe_tuple {
  Some(tuple @ (left, right)) => if left == right { Some(tuple) } else { None },
  None => None
}
```

**Why this is awesome**

`if let` cuts a lot of vertical noise out of simple unwrap logic, and `name @ pattern` avoids wasteful “take it apart, then rebuild it” code. Together they make pattern-heavy code much more elegant. [0.17]

---

## 16) Introduce type aliases and super traits to clean up API vocabulary (0.17)

**High-level explanation**

Spade 0.17 added **type aliases** and **super traits**. Audit code that repeats the same bit-width-heavy type names or defines traits whose relationships are obvious but implicit. [0.17]

**Before**

```spade
fn mix(a: int<32>, b: int<32>) -> int<32> {
  // ...
}

trait Eq {}
trait Ord {}
```

**After**

```spade
type i32 = int<32>;

fn mix(a: i32, b: i32) -> i32 {
  // ...
}

trait Eq: PartialEq {}
trait Ord: Eq {}
```

**Why this is awesome**

Aliases let your code talk in the project’s domain vocabulary instead of repeating raw type machinery everywhere, and super traits make trait relationships explicit instead of tribal knowledge. [0.17]

---

## 17) Clean up Verilog interop: type-level strings, raw identifiers, and `#[verilog_attrs]` on declarations/calls (0.15–0.17)

**High-level explanation**

Across these releases, Spade got much better at interfacing with awkward external Verilog: 0.15 added type-level strings, 0.16 added `#[verilog_attrs(...)]` and raw identifiers like `r#ident`, and 0.17 made `verilog_attrs` usable on calls/instantiations. Audit wrapper units that exist only to rename ports, thread string configuration, or attach instance attributes. [0.15] [0.16] [0.17]

**Before**

```spade
extern entity vendor_pll(clk: clock, reset_n: bool) -> PllOut;

// Wrapper only exists to massage names or instance metadata
entity sys_pll(clk: clock, rst: bool) -> PllOut {
  inst vendor_pll(clk, !rst)
}
```

**After**

```spade
extern entity vendor_pll<#str DEVICE>(clk: clock, r#reset: bool) -> PllOut;

#[verilog_attrs(...)]
let pll = inst vendor_pll::<"LFE5U-25F">(clk, rst);
```

**Why this is awesome**

Interop code gets much closer to the vendor documentation instead of being buried under Spade-side shims. That usually means fewer tiny wrappers, less duplicated configuration, and less “why does this wrapper even exist?” archaeology later. [0.15] [0.16] [0.17]

---

## 18) Replace magic bytes and hard-coded branch targets with ASCII literals and array labels (0.16)

**High-level explanation**

Spade 0.16 added ASCII literals like `b'a'` and `b"..."`, and it also added array labels with label-based indexing. Audit protocol/UART code full of numeric byte constants, and instruction/data tables that use hard-coded offsets. [0.16]

**Before**

```spade
let msg = [72u8, 69u8, 76u8, 76u8, 79u8];

let program = [
  Insn::Set(0, 0),
  Insn::Addi(0, 1),
  Insn::Branchi(0, Cond::Eq, 255, 1)
];
```

**After**

```spade
let msg = b"HELLO";

let program = [
  Insn::Set(0, 0),
'loop_start
  Insn::Addi(0, 1),
  Insn::Branchi(0, Cond::Eq, 255, @loop_start.index)
];
```

**Why this is awesome**

The code stops hiding meaning in magic numbers. Human-readable text becomes actually human-readable, and branch targets become reorder-safe instead of “remember to manually update the offset if you insert an instruction.” [0.16]

---

## 19) Use `#[inline]` for tiny adapter/operator units, and `#[deprecated]` for staged migrations (0.17)

**High-level explanation**

Spade 0.17 added `#[inline]` for units and deprecation attributes. Audit small wrapper units that add no useful hierarchy, and internal APIs you want to retire gradually instead of with one big breaking rename. [0.17]

**Before**

```spade
fn old_add(a: i32, b: i32) -> i32 {
  new_add(a, b)
}

fn passthrough(x: i32) -> i32 {
  x
}
```

**After**

```spade
#[deprecated = "Use new_add"]
fn old_add(a: i32, b: i32) -> i32 {
  new_add(a, b)
}

#[inline]
fn passthrough(x: i32) -> i32 {
  x
}
```

**Why this is awesome**

You get cleaner generated hierarchy for tiny “glue” units and a much nicer migration story for library cleanup. Both reduce friction for future refactors. [0.17]

---

## Suggested audit order for a mature codebase

If I were auditing a real project, I would usually do the passes in this order:

1. **Mandatory / near-mandatory cleanup**
   - `set x = y` → `set x = &y`
   - modern lambda syntax
   - modern `Fn(...) -> ...` syntax
   - tuple `#` indexing → dot indexing

2. **Ergonomics wins that reduce boilerplate**
   - lambda captures
   - `if let`
   - match guards
   - `name @ pattern`
   - type aliases
   - visibility markers
   - import consolidation

3. **Bug-prevention refactors**
   - `inst(_)`
   - array labels instead of numeric offsets
   - `unsafe` fencing
   - default type parameters for “almost always defaulted” generics

4. **API redesign / deeper cleanup**
   - pipeline methods
   - `impl Trait`
   - type-expression-heavy generic cleanup
   - wrapping operators
   - operator overloading
   - Verilog interop cleanup
   - `#[inline]` / `#[deprecated]`

---

## Sources

- [0.15]: [Spade 0.15.0 — posted 2025-11-20](https://blog.spade-lang.org/v0-15-0/)
- [0.16]: [Spade 0.16.0 — posted 2026-01-22](https://blog.spade-lang.org/v0-16-0/)
- [0.17]: [Spade 0.17.0 — posted 2026-03-05](https://blog.spade-lang.org/v0-17-0/)
