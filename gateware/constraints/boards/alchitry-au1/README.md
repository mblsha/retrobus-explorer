# Alchitry Au1 constraint inputs

These are the minimal repository-owned inputs used to generate the Spade
projects' Xilinx constraints without checking out Alchitry Labs V2.

- `alchitry.acf` and `ft_v1.acf` are exact copies from Alchitry Labs V2 commit
  `d17afd919742e0aa2364ed08dce7734274ec73cc`.
- `pins.toml` contains only the Au symbolic pins referenced by those files and
  this repository's active target/interface constraints. The values match
  `AuPin.kt` at the same upstream commit.

The [upstream source and GPL-3.0 license](https://github.com/alchitry/Alchitry-Labs-V2/tree/d17afd919742e0aa2364ed08dce7734274ec73cc)
remain available at the pinned commit.
