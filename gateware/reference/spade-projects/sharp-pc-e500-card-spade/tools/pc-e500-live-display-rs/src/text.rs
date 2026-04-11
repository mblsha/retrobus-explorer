use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

const DISPLAY_WIDTH: usize = 240;
const DISPLAY_HEIGHT: usize = 32;
const GLYPH_WIDTH: usize = 5;
const GLYPH_STRIDE: usize = 6;
const GLYPH_COUNT: usize = 96;
const ROWS_PER_CELL: usize = 8;
const COLS_PER_CELL: usize = 6;
const ROM_WINDOW_START: u32 = 0x0F000;
const ROM_ENGLISH_FONT_BASE_ADDR: u32 = 0x00F3E09;
const ROM_JP_FONT_ATLAS_BASE_ADDR: u32 = 0x00F21A5;
const PCE500_JP_SENTINEL_A_ADDR: u32 = 0x00F232B;
const PCE500_JP_SENTINEL_A: [u8; GLYPH_WIDTH] = [0x7C, 0x12, 0x11, 0x12, 0x7C];
const PCE500_JP_SENTINEL_WO_ADDR: u32 = 0x00F2589;
const PCE500_JP_SENTINEL_WO: [u8; GLYPH_WIDTH] = [0x0A, 0x4A, 0x4A, 0x2A, 0x1E];
const PCE500_ARROW_UP_DOWN: [u8; GLYPH_WIDTH] = [0x00, 0x28, 0x6C, 0x6C, 0x28];
const PCE500_ARROW_UP_DOWN_NARROW: [u8; GLYPH_WIDTH] = [0x00, 0x28, 0x6C, 0x6C, 0x00];
const PCE500_LBRACKET: [u8; GLYPH_WIDTH] = [0x00, 0x7F, 0x7F, 0x41, 0x00];
const PCE500_RBRACKET: [u8; GLYPH_WIDTH] = [0x00, 0x41, 0x7F, 0x7F, 0x00];

#[derive(Clone, Debug, Default)]
pub struct Pce500FontMap {
    glyphs: HashMap<[u8; GLYPH_WIDTH], char>,
}

impl Pce500FontMap {
    pub fn load_default() -> Result<Self> {
        let rom_path = default_rom_path().context("could not locate a PC-E500 ROM for text decode")?;
        let rom = fs::read(&rom_path)
            .with_context(|| format!("failed to read ROM {}", rom_path.display()))?;
        Ok(Self::from_pce500_rom(&rom, ROM_WINDOW_START))
    }

    pub fn is_empty(&self) -> bool {
        self.glyphs.is_empty()
    }

    pub fn decode_frame(&self, frame: &[u8]) -> Vec<String> {
        if self.is_empty() || frame.len() != DISPLAY_WIDTH * DISPLAY_HEIGHT {
            return Vec::new();
        }
        let char_rows = DISPLAY_HEIGHT / ROWS_PER_CELL;
        let char_cols = DISPLAY_WIDTH / COLS_PER_CELL;
        let mut lines = Vec::with_capacity(char_rows);

        for page in 0..char_rows {
            let row_base = page * ROWS_PER_CELL;
            let mut row = String::with_capacity(char_cols);
            for char_index in 0..char_cols {
                let col_base = char_index * COLS_PER_CELL;
                let mut pattern = [0u8; GLYPH_WIDTH];
                for (glyph_col, pattern_col) in pattern.iter_mut().enumerate() {
                    let mut bits = 0u8;
                    let col = col_base + glyph_col;
                    for dy in 0..ROWS_PER_CELL {
                        let idx = (row_base + dy) * DISPLAY_WIDTH + col;
                        if frame[idx] != 0 {
                            bits |= 1 << dy;
                        }
                    }
                    *pattern_col = bits & 0x7F;
                }
                row.push(self.resolve(&pattern));
            }
            lines.push(row.trim_end().to_string());
        }

        lines
    }

    fn from_rom(rom: &[u8], font_base_addr: u32, rom_window_start: u32) -> Self {
        let Some(base) = external_addr_offset(rom, font_base_addr, rom_window_start) else {
            return Self::default();
        };

        let mut glyphs = HashMap::new();
        for index in 0..GLYPH_COUNT {
            let start = base + index * GLYPH_STRIDE;
            if start + GLYPH_WIDTH > rom.len() {
                break;
            }
            let mut pattern = [0u8; GLYPH_WIDTH];
            pattern.copy_from_slice(&rom[start..start + GLYPH_WIDTH]);
            for byte in &mut pattern {
                *byte &= 0x7F;
            }
            let codepoint = 0x20 + index as u32;
            if let Some(ch) = char::from_u32(codepoint) {
                insert_pattern(&mut glyphs, pattern, ch);
            }
        }
        insert_pattern(&mut glyphs, PCE500_ARROW_UP_DOWN, '↕');
        insert_pattern(&mut glyphs, PCE500_ARROW_UP_DOWN_NARROW, '↕');
        insert_pattern(&mut glyphs, PCE500_LBRACKET, '[');
        insert_pattern(&mut glyphs, PCE500_RBRACKET, ']');
        Self { glyphs }
    }

    fn from_pce500_rom(rom: &[u8], rom_window_start: u32) -> Self {
        if !looks_like_pce500_jp_font(rom, rom_window_start) {
            return Self::from_rom(rom, ROM_ENGLISH_FONT_BASE_ADDR, rom_window_start);
        }

        let mut glyphs = HashMap::new();
        for code in 0u16..=0xFF {
            let Some(ch) = pce500_jp_display_char(code as u8) else {
                continue;
            };
            let glyph_addr = ROM_JP_FONT_ATLAS_BASE_ADDR + u32::from(code) * GLYPH_STRIDE as u32;
            let Some(pattern) = read_pattern_at(rom, glyph_addr, rom_window_start) else {
                continue;
            };
            insert_pattern(&mut glyphs, pattern, ch);
        }

        insert_pattern(&mut glyphs, PCE500_ARROW_UP_DOWN, '↕');
        insert_pattern(&mut glyphs, PCE500_ARROW_UP_DOWN_NARROW, '↕');
        insert_pattern(&mut glyphs, PCE500_LBRACKET, '[');
        insert_pattern(&mut glyphs, PCE500_RBRACKET, ']');
        Self { glyphs }
    }

    fn resolve(&self, pattern: &[u8; GLYPH_WIDTH]) -> char {
        *self.glyphs.get(pattern).unwrap_or(&'?')
    }
}

fn default_rom_path() -> Option<PathBuf> {
    if let Ok(explicit) = std::env::var("PC_E500_ROM") {
        let path = PathBuf::from(explicit);
        if path.is_file() {
            return Some(path);
        }
    }

    let cwd = std::env::current_dir().ok();
    let exe = std::env::current_exe().ok();
    let mut candidates = Vec::new();
    if let Some(dir) = cwd {
        candidates.push(dir);
    }
    if let Some(path) = exe.and_then(|path| path.parent().map(Path::to_path_buf)) {
        candidates.push(path);
    }

    for base in candidates {
        for ancestor in base.ancestors() {
            let jp = ancestor.join("../binja-esr-tests/roms/pc-e500-jp.bin");
            if jp.is_file() {
                return Some(jp);
            }
            let en = ancestor.join("../binja-esr-tests/roms/pc-e500-en.bin");
            if en.is_file() {
                return Some(en);
            }
        }
    }
    None
}

fn insert_pattern(glyphs: &mut HashMap<[u8; GLYPH_WIDTH], char>, pattern: [u8; GLYPH_WIDTH], ch: char) {
    if pattern.iter().all(|byte| (byte & 0x7F) == 0) && ch != ' ' {
        return;
    }
    glyphs.entry(pattern).or_insert(ch);
    let mut inverted = [0u8; GLYPH_WIDTH];
    for (dest, src) in inverted.iter_mut().zip(pattern) {
        *dest = (!src) & 0x7F;
    }
    glyphs.entry(inverted).or_insert(ch);
}

fn external_addr_offset(rom: &[u8], absolute_addr: u32, rom_window_start: u32) -> Option<usize> {
    let base = usize::try_from(absolute_addr).ok()?;
    if base < rom.len() {
        return Some(base);
    }
    let window_base = absolute_addr.checked_sub(rom_window_start)?;
    let window_base = usize::try_from(window_base).ok()?;
    if window_base < rom.len() {
        return Some(window_base);
    }
    None
}

fn read_pattern_at(rom: &[u8], absolute_addr: u32, rom_window_start: u32) -> Option<[u8; GLYPH_WIDTH]> {
    let start = external_addr_offset(rom, absolute_addr, rom_window_start)?;
    if start + GLYPH_WIDTH > rom.len() {
        return None;
    }
    let mut pattern = [0u8; GLYPH_WIDTH];
    pattern.copy_from_slice(&rom[start..start + GLYPH_WIDTH]);
    for byte in &mut pattern {
        *byte &= 0x7F;
    }
    Some(pattern)
}

fn looks_like_pce500_jp_font(rom: &[u8], rom_window_start: u32) -> bool {
    read_pattern_at(rom, PCE500_JP_SENTINEL_A_ADDR, rom_window_start)
        .is_some_and(|pattern| pattern == PCE500_JP_SENTINEL_A)
        && read_pattern_at(rom, PCE500_JP_SENTINEL_WO_ADDR, rom_window_start)
            .is_some_and(|pattern| pattern == PCE500_JP_SENTINEL_WO)
}

fn pce500_jp_display_char(code: u8) -> Option<char> {
    match code {
        0x20..=0x7E => char::from_u32(u32::from(code)),
        0xA1..=0xDF => char::from_u32(0xFF61 + u32::from(code - 0xA1)),
        0xE8 => Some('✳'),
        0xEC => Some('●'),
        0xEF => Some('/'),
        _ => None,
    }
}
