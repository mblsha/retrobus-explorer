use std::collections::BTreeMap;

pub const DEFAULT_PIPE_ID: u8 = 0x00;
pub const DEFAULT_READ_SIZE: usize = 64 * 1024;
pub const DEFAULT_READ_TIMEOUT_MS: u32 = 20;
pub const DEFAULT_STREAM_SIZE: u32 = 4;
pub const LCD_WRITE_ADDR_MIN: u32 = 0x0A000;
pub const LCD_WRITE_ADDR_MAX: u32 = 0x0A010;

#[derive(Clone, Debug, Default)]
pub struct StreamStatus {
    pub cfg: Option<u8>,
    pub mode: Option<u8>,
    pub uart: Option<bool>,
    pub win: Option<bool>,
    pub cap: Option<bool>,
    pub sovf: Option<u32>,
    pub ovf: Option<u32>,
    pub raw: String,
    pub fields: BTreeMap<String, String>,
}

impl StreamStatus {
    pub fn desynced(&self) -> bool {
        self.sovf.unwrap_or(0) != 0
    }
}

#[derive(Copy, Clone, Debug)]
pub struct SampledWord {
    pub addr: u32,
    pub data: u8,
    pub status: u8,
}

impl SampledWord {
    pub fn from_raw(raw: u32) -> Self {
        Self {
            addr: raw & 0x3ffff,
            data: ((raw >> 18) & 0xff) as u8,
            status: ((raw >> 26) & 0x3f) as u8,
        }
    }

    pub fn rw(self) -> bool {
        (self.status & 0x01) != 0
    }
}

pub fn decode_packed_words(chunk: &[u8], pending: &mut Vec<u8>) -> Vec<u32> {
    let mut merged = Vec::with_capacity(pending.len() + chunk.len());
    merged.extend_from_slice(pending);
    merged.extend_from_slice(chunk);

    let full_len = merged.len() / 4 * 4;
    let mut words = Vec::with_capacity(full_len / 4);
    for bytes in merged[..full_len].chunks_exact(4) {
        words.push(u32::from_le_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]));
    }
    pending.clear();
    pending.extend_from_slice(&merged[full_len..]);
    words
}

pub fn parse_stream_status_line(line: &str) -> Option<StreamStatus> {
    if !line.starts_with("FS,") {
        return None;
    }
    let mut status = StreamStatus {
        raw: line.trim().to_string(),
        ..Default::default()
    };
    for part in line.trim().split(',').skip(1) {
        let (key, value) = part.split_once('=')?;
        status.fields.insert(key.to_string(), value.to_string());
        match key {
            "CFG" => status.cfg = u8::from_str_radix(value, 16).ok(),
            "MODE" => status.mode = u8::from_str_radix(value, 16).ok(),
            "UART" => status.uart = parse_bool_digit(value),
            "WIN" => status.win = parse_bool_digit(value),
            "CAP" => status.cap = parse_bool_digit(value),
            "SOVF" => status.sovf = u32::from_str_radix(value, 16).ok(),
            "OVF" => status.ovf = u32::from_str_radix(value, 16).ok(),
            _ => {}
        }
    }
    Some(status)
}

fn parse_bool_digit(value: &str) -> Option<bool> {
    match value {
        "0" => Some(false),
        "1" => Some(true),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_packed_words_preserves_pending_bytes() {
        let mut pending = vec![0x11, 0x22];
        let words = decode_packed_words(&[0x33, 0x44, 0x55, 0x66, 0x77], &mut pending);

        assert_eq!(words, vec![0x4433_2211]);
        assert_eq!(pending, vec![0x55, 0x66, 0x77]);
    }

    #[test]
    fn parse_stream_status_line_decodes_core_fields() {
        let status = parse_stream_status_line(
            "FS,CFG=02,MODE=00,UART=1,WIN=0,CAP=1,SOVF=00000000,OVF=00000010",
        )
        .expect("status should parse");

        assert_eq!(status.cfg, Some(0x02));
        assert_eq!(status.mode, Some(0x00));
        assert_eq!(status.uart, Some(true));
        assert_eq!(status.win, Some(false));
        assert_eq!(status.cap, Some(true));
        assert_eq!(status.sovf, Some(0));
        assert_eq!(status.ovf, Some(0x10));
        assert!(!status.desynced());
        assert_eq!(status.fields.get("CFG").map(String::as_str), Some("02"));
    }

    #[test]
    fn sampled_word_extracts_fields() {
        let raw = 0x2a55_1234;
        let word = SampledWord::from_raw(raw);

        assert_eq!(word.addr, raw & 0x3ffff);
        assert_eq!(word.data, ((raw >> 18) & 0xff) as u8);
        assert_eq!(word.status, ((raw >> 26) & 0x3f) as u8);
        assert_eq!(word.rw(), (word.status & 0x01) != 0);
    }
}
