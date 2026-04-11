use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};

pub const DEFAULT_BAUD: u32 = 1_000_000;
pub const DEFAULT_IDLE_GAP_S: f64 = 0.05;
pub const DEFAULT_QUIET_TIMEOUT_S: f64 = 5.0;
pub const DEFAULT_COMMAND_TIMEOUT_S: f64 = 1.0;
pub const CARD_ROM_BASE: u32 = 0x10000;
pub const CARD_ROM_SIZE: usize = 0x800;
pub const CARD_ROM_LAST: u32 = CARD_ROM_BASE + CARD_ROM_SIZE as u32 - 1;
pub const DEFAULT_FILL_BYTE: u8 = 0xff;
pub const DEFAULT_SAFE_TIMING: u32 = 5;
pub const DEFAULT_SAFE_CONTROL_TIMING: u32 = 10;
pub const DEFAULT_FT_MAX_RETAINED_WORDS: usize = 262_144;

pub const READY_PREFIX: &str = "XR,READY";
pub const BEGIN_PREFIX: &str = "XR,BEGIN";
pub const END_PREFIX: &str = "XR,END";
pub const MEASURE_END_LINE: &str = "MEND";

pub const CMD_BASE: u32 = 0x107E0;
pub const CMD_MAGIC0: u32 = CMD_BASE + 0x00;
pub const CMD_MAGIC1: u32 = CMD_BASE + 0x01;
pub const CMD_VERSION: u32 = CMD_BASE + 0x02;
pub const CMD_FLAGS: u32 = CMD_BASE + 0x03;
pub const CMD_START_TAG: u32 = CMD_BASE + 0x04;
pub const CMD_STOP_TAG: u32 = CMD_BASE + 0x05;
pub const CMD_ARGS_BASE: u32 = CMD_BASE + 0x06;
pub const CMD_ARGS_COUNT: usize = 10;
pub const CMD_SEQ: u32 = 0x107FF;
pub const CMD_FLAG_ENABLE_FT_CAPTURE: u8 = 0x01;

pub const EXPERIMENT_MIN: u32 = 0x10100;
pub const EXPERIMENT_MAX: u32 = 0x106FF;

pub fn default_socket_path() -> PathBuf {
    dirs_home().join(".cache").join("pc-e500-expd.sock")
}

pub fn default_assembler_dir() -> PathBuf {
    dirs_home().join("src/github/binja-esr-tests/public-src")
}

pub fn project_root_from_manifest() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(3)
        .expect("project root")
        .to_path_buf()
}

pub fn default_safe_asm() -> PathBuf {
    project_root_from_manifest()
        .join("asm")
        .join("card_rom_supervisor_safe.asm")
}

pub fn default_debug_echo_asm() -> PathBuf {
    project_root_from_manifest()
        .join("asm")
        .join("card_rom_echo_short_retf.asm")
}

fn dirs_home() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .expect("HOME must be set")
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParsedMeasurement {
    pub start_tag: u32,
    pub stop_tag: u32,
    pub ticks: u32,
    pub ce_events: u32,
    pub addr_uart: u32,
    pub ft_overflow: u32,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ParsedMeasureStatus {
    pub count: u32,
    pub overflow: u32,
    pub armed: bool,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RunPlan {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub asm_source: Option<String>,
    #[serde(default)]
    pub asm_text: Option<String>,
    #[serde(default = "default_timing")]
    pub timing: u32,
    #[serde(default = "default_control_timing")]
    pub control_timing: u32,
    #[serde(default = "default_timeout")]
    pub timeout_s: f64,
    #[serde(default = "default_start_tag")]
    pub start_tag: u32,
    #[serde(default = "default_stop_tag")]
    pub stop_tag: u32,
    #[serde(default)]
    pub flags: u32,
    #[serde(default)]
    pub args: Vec<u32>,
    #[serde(default = "default_ft_capture")]
    pub ft_capture: bool,
    #[serde(default = "default_fill_experiment_region")]
    pub fill_experiment_region: bool,
    #[serde(default = "default_ft_read_size")]
    pub ft_read_size: usize,
    #[serde(default = "default_ft_read_timeout_ms")]
    pub ft_read_timeout_ms: u32,
    #[serde(default = "default_ft_post_stop_idle")]
    pub ft_post_stop_idle_s: f64,
    #[serde(default = "default_ft_post_stop_hard")]
    pub ft_post_stop_hard_s: f64,
    #[serde(default = "default_ft_max_retained_words")]
    pub ft_max_retained_words: usize,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, Value>,
}

fn default_timing() -> u32 {
    5
}
fn default_control_timing() -> u32 {
    10
}
fn default_timeout() -> f64 {
    2.0
}
fn default_start_tag() -> u32 {
    0x11
}
fn default_stop_tag() -> u32 {
    0x12
}
fn default_ft_capture() -> bool {
    true
}
fn default_fill_experiment_region() -> bool {
    true
}
fn default_ft_read_size() -> usize {
    64 * 1024
}
fn default_ft_read_timeout_ms() -> u32 {
    20
}
fn default_ft_post_stop_idle() -> f64 {
    0.1
}
fn default_ft_post_stop_hard() -> f64 {
    1.0
}
fn default_ft_max_retained_words() -> usize {
    DEFAULT_FT_MAX_RETAINED_WORDS
}

impl RunPlan {
    pub fn public_json(&self) -> Value {
        let mut value = serde_json::to_value(self).unwrap_or_else(|_| json!({}));
        if let Value::Object(ref mut map) = value {
            map.remove("_script_path");
            map.remove("_script_args");
        }
        value
    }
}

pub fn parse_key_value_csv(line: &str) -> anyhow::Result<(String, serde_json::Map<String, Value>)> {
    let mut parts = line.trim().split(',');
    let prefix = parts
        .next()
        .ok_or_else(|| anyhow::anyhow!("missing CSV prefix"))?
        .to_string();
    let mut values = serde_json::Map::new();
    for part in parts {
        let (key, value) = part
            .split_once('=')
            .ok_or_else(|| anyhow::anyhow!("invalid CSV field: {part}"))?;
        if key == "ARM" {
            values.insert(key.to_string(), Value::Bool(value == "1"));
        } else {
            values.insert(
                key.to_string(),
                Value::Number(serde_json::Number::from(u64::from_str_radix(value, 16)?)),
            );
        }
    }
    Ok((prefix, values))
}

pub fn render_terminal_bytes(data: &[u8]) -> String {
    let mut rendered = String::new();
    for &byte in data {
        match byte {
            0x20..=0x7e => rendered.push(byte as char),
            b'\n' => rendered.push('\n'),
            b'\r' => rendered.push('\r'),
            b'\t' => rendered.push('\t'),
            other => rendered.push_str(&format!("\\x{other:02X}")),
        }
    }
    rendered
}

pub fn normalize_reply_lines(reply: &[u8]) -> Vec<String> {
    String::from_utf8_lossy(reply)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .split('\n')
        .filter(|line| !line.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

pub fn parse_measure_status_lines(lines: &[String]) -> anyhow::Result<ParsedMeasureStatus> {
    for line in lines {
        if line.starts_with("MS,") {
            let (prefix, values) = parse_key_value_csv(line)?;
            if prefix != "MS" {
                continue;
            }
            return Ok(ParsedMeasureStatus {
                count: values["CNT"].as_u64().unwrap_or(0) as u32,
                overflow: values["OVF"].as_u64().unwrap_or(0) as u32,
                armed: values["ARM"].as_bool().unwrap_or(false),
            });
        }
    }
    anyhow::bail!("measure status line not found")
}

pub fn parse_measurement_lines(lines: &[String]) -> anyhow::Result<Vec<ParsedMeasurement>> {
    let mut measurements = Vec::new();
    for line in lines {
        if line == MEASURE_END_LINE || !line.starts_with("MR,") {
            continue;
        }
        let (prefix, values) = parse_key_value_csv(line)?;
        if prefix != "MR" {
            continue;
        }
        measurements.push(ParsedMeasurement {
            start_tag: values["S"].as_u64().unwrap_or(0) as u32,
            stop_tag: values["E"].as_u64().unwrap_or(0) as u32,
            ticks: values["TK"].as_u64().unwrap_or(0) as u32,
            ce_events: values["EV"].as_u64().unwrap_or(0) as u32,
            addr_uart: values["AU"].as_u64().unwrap_or(0) as u32,
            ft_overflow: values.get("FO").and_then(Value::as_u64).unwrap_or(0) as u32,
        });
    }
    Ok(measurements)
}

pub fn rom_offset_from_address(address: u32) -> anyhow::Result<usize> {
    if address < CARD_ROM_SIZE as u32 {
        return Ok(address as usize);
    }
    if (CARD_ROM_BASE..=CARD_ROM_LAST).contains(&address) {
        return Ok((address - CARD_ROM_BASE) as usize);
    }
    anyhow::bail!(
        "address {:X} is outside the 2 KiB card-ROM window ({:05X}..{:05X} or offsets 000..7FF)",
        address,
        CARD_ROM_BASE,
        CARD_ROM_LAST
    )
}

pub fn absolute_address(offset: usize) -> u32 {
    CARD_ROM_BASE + offset as u32
}

pub fn build_write_payload(start_offset: usize, data: &[u8]) -> Vec<u8> {
    let mut payload = Vec::with_capacity(data.len() * 8);
    for (index, value) in data.iter().enumerate() {
        payload
            .extend_from_slice(format!("W{:03X}={:02X}\r", start_offset + index, value).as_bytes());
    }
    payload
}

pub fn build_card_rom_image(
    segments: &[(u32, Vec<u8>)],
    fill_byte: u8,
) -> anyhow::Result<(u32, Vec<u8>)> {
    let start = segments
        .iter()
        .map(|(addr, _)| *addr)
        .min()
        .ok_or_else(|| anyhow::anyhow!("no segments"))?;
    let end = segments
        .iter()
        .map(|(addr, data)| *addr + data.len() as u32)
        .max()
        .ok_or_else(|| anyhow::anyhow!("no segments"))?;
    if start < CARD_ROM_BASE || end - 1 > CARD_ROM_LAST {
        anyhow::bail!(
            "assembled image spans {:05X}..{:05X}, outside card ROM window {:05X}..{:05X}",
            start,
            end - 1,
            CARD_ROM_BASE,
            CARD_ROM_LAST
        );
    }

    let mut image = vec![fill_byte; (end - start) as usize];
    let mut written = vec![false; image.len()];
    for (address, data) in segments {
        let offset = (*address - start) as usize;
        for (index, value) in data.iter().enumerate() {
            let pos = offset + index;
            if written[pos] && image[pos] != *value {
                anyhow::bail!(
                    "overlapping segments disagree at {:05X}",
                    start + pos as u32
                );
            }
            image[pos] = *value;
            written[pos] = true;
        }
    }
    Ok((start, image))
}

pub fn resolve_existing_file(path: &Path, label: &str) -> anyhow::Result<PathBuf> {
    let resolved = path
        .expanduser()
        .canonicalize()
        .unwrap_or_else(|_| path.expanduser());
    if !resolved.is_file() {
        anyhow::bail!("{label} not found at {}", resolved.display());
    }
    Ok(resolved)
}

pub fn resolve_existing_dir(path: &Path, label: &str) -> anyhow::Result<PathBuf> {
    let resolved = path
        .expanduser()
        .canonicalize()
        .unwrap_or_else(|_| path.expanduser());
    if !resolved.is_dir() {
        anyhow::bail!("{label} not found at {}", resolved.display());
    }
    Ok(resolved)
}

trait ExpandUser {
    fn expanduser(&self) -> PathBuf;
}

impl ExpandUser for Path {
    fn expanduser(&self) -> PathBuf {
        let text = self.to_string_lossy();
        if let Some(rest) = text.strip_prefix("~/") {
            return dirs_home().join(rest);
        }
        self.to_path_buf()
    }
}
