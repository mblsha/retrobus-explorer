use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};
use serde_json::Value;

use crate::protocol::{build_card_rom_image, DEFAULT_FILL_BYTE};

const ASSEMBLER_SNIPPET: &str = r#"
import json
import sys
from pathlib import Path
from sc62015.pysc62015.sc_asm import Assembler
source = Path(sys.argv[1]).read_text()
binfile = Assembler().assemble(source)
print(json.dumps([
    {"address": segment.address, "data_hex": segment.data.hex()}
    for segment in binfile.segments
]))
"#;

fn build_subprocess_env() -> Vec<(&'static str, String)> {
    vec![
        ("FORCE_BINJA_MOCK", "1".to_string()),
        ("UV_NO_CONFIG", "1".to_string()),
    ]
}

pub fn assemble_segments(source_path: &Path, assembler_dir: &Path) -> Result<Vec<(u32, Vec<u8>)>> {
    let mut command = Command::new("uv");
    command
        .arg("run")
        .arg("python")
        .arg("-c")
        .arg(ASSEMBLER_SNIPPET)
        .arg(source_path)
        .current_dir(assembler_dir)
        .env_remove("VIRTUAL_ENV");
    for (key, value) in build_subprocess_env() {
        command.env(key, value);
    }
    let output = command
        .output()
        .context("failed to spawn uv for assembly")?;
    if !output.status.success() {
        anyhow::bail!(
            "assembly failed for {}\nstdout:\n{}\nstderr:\n{}",
            source_path.display(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
    }
    let payload: Value = serde_json::from_slice(&output.stdout)?;
    let mut segments = Vec::new();
    for item in payload.as_array().into_iter().flatten() {
        let address = item["address"].as_u64().unwrap_or(0) as u32;
        let data_hex = item["data_hex"].as_str().unwrap_or_default();
        segments.push((address, hex_to_bytes(data_hex)?));
    }
    if segments.is_empty() {
        anyhow::bail!("assembler produced no output segments");
    }
    segments.sort_by_key(|(address, _)| *address);
    Ok(segments)
}

pub fn assemble_text(source_text: &str, assembler_dir: &Path) -> Result<Vec<(u32, Vec<u8>)>> {
    let temp = tempfile_path("asm");
    fs::write(&temp, source_text)?;
    let result = assemble_segments(&temp, assembler_dir);
    let _ = fs::remove_file(&temp);
    result
}

pub fn assemble_image_from_source(
    source_path: &Path,
    assembler_dir: &Path,
) -> Result<(u32, Vec<u8>)> {
    let segments = assemble_segments(source_path, assembler_dir)?;
    build_card_rom_image(&segments, DEFAULT_FILL_BYTE)
}

pub fn assemble_image_from_text(source_text: &str, assembler_dir: &Path) -> Result<(u32, Vec<u8>)> {
    let segments = assemble_text(source_text, assembler_dir)?;
    build_card_rom_image(&segments, DEFAULT_FILL_BYTE)
}

fn hex_to_bytes(hex: &str) -> Result<Vec<u8>> {
    if hex.len() % 2 != 0 {
        anyhow::bail!("invalid hex length");
    }
    let mut bytes = Vec::with_capacity(hex.len() / 2);
    let chars: Vec<_> = hex.as_bytes().to_vec();
    for index in (0..chars.len()).step_by(2) {
        bytes.push(u8::from_str_radix(
            std::str::from_utf8(&chars[index..index + 2])?,
            16,
        )?);
    }
    Ok(bytes)
}

fn tempfile_path(ext: &str) -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("pc_e500_expd_rs_{nanos}.{ext}"))
}
