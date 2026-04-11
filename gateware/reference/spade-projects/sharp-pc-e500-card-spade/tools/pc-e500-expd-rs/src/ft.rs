use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::Result;

use crate::d3xx::Device;

pub const DEFAULT_PIPE_ID: u8 = 0x00;
pub const DEFAULT_READ_SIZE: usize = 64 * 1024;
pub const DEFAULT_READ_TIMEOUT_MS: u32 = 20;
pub const DEFAULT_STREAM_SIZE: u32 = 4;

const SUPERVISOR_ROM_MIN: u32 = 0x10000;
const SUPERVISOR_ROM_MAX: u32 = 0x100ff;
const EXPERIMENT_ROM_MIN: u32 = 0x10100;
const EXPERIMENT_ROM_MAX: u32 = 0x106ff;
const COMMAND_BLOCK_MIN: u32 = 0x107e0;
const COMMAND_BLOCK_MAX: u32 = 0x107ff;
const CTRL_RANGE_MIN: u32 = 0x1fff0;
const CTRL_RANGE_MAX: u32 = 0x1ffff;
const HI_STACK_MIN: u32 = 0x3f800;
const HI_STACK_MAX: u32 = 0x3ffff;

#[derive(Clone, Debug)]
pub struct FtDecodedEvent {
    pub index: usize,
    pub raw_word: u32,
    pub addr: u32,
    pub data: u8,
    pub status: u8,
    pub rw: bool,
    pub ce1_active: bool,
    pub ce6_active: bool,
    pub synthetic_followup: bool,
    pub from_cycle_start: bool,
    pub ctrl_range: bool,
    pub kind: String,
}

#[derive(Clone, Debug)]
pub struct FtCaptureResult {
    pub words: Vec<u32>,
    pub raw_bytes: usize,
    pub chunk_count: usize,
    pub pending_bytes_hex: String,
    pub decode_swap_u16: bool,
    pub drain_idle_s: f64,
    pub drain_hard_s: f64,
    pub retained_words: usize,
    pub total_words_seen: usize,
    pub max_retained_words: usize,
    pub truncated_head: bool,
}

#[derive(Clone, Debug)]
pub struct FtCaptureSession {
    start_word_index: usize,
    start_raw_bytes: usize,
    start_chunk_count: usize,
}

#[derive(Default)]
struct SharedState {
    segments: VecDeque<(usize, Vec<u32>)>,
    retained_word_count: usize,
    total_word_count: usize,
    raw_bytes: usize,
    chunk_count: usize,
    pending: Vec<u8>,
    running: bool,
    stop: bool,
    last_error: Option<String>,
}

pub struct Ft600Capture {
    shared: Arc<Mutex<SharedState>>,
    thread: Option<thread::JoinHandle<()>>,
    pub read_size: usize,
    pub read_timeout_ms: u32,
    pub post_stop_idle_s: f64,
    pub post_stop_hard_s: f64,
    pub max_retained_words: usize,
    pub pipe_id: u8,
    pub stream_size: u32,
    pub library_path: Option<std::path::PathBuf>,
}

impl Ft600Capture {
    pub fn new(max_retained_words: usize) -> Self {
        Self {
            shared: Arc::new(Mutex::new(SharedState::default())),
            thread: None,
            read_size: DEFAULT_READ_SIZE,
            read_timeout_ms: DEFAULT_READ_TIMEOUT_MS,
            post_stop_idle_s: 0.1,
            post_stop_hard_s: 1.0,
            max_retained_words,
            pipe_id: DEFAULT_PIPE_ID,
            stream_size: DEFAULT_STREAM_SIZE,
            library_path: None,
        }
    }

    pub fn ensure_running(&mut self) -> Result<()> {
        if self.thread.is_some() {
            return Ok(());
        }
        let shared = self.shared.clone();
        let pipe_id = self.pipe_id;
        let stream_size = self.stream_size;
        let read_size = self.read_size;
        let read_timeout_ms = self.read_timeout_ms;
        let max_retained_words = self.max_retained_words;
        let library_path = self.library_path.clone();
        self.thread = Some(thread::spawn(move || {
            let mut device =
                match Device::open_default(library_path.as_deref(), pipe_id, stream_size) {
                    Ok(device) => device,
                    Err(err) => {
                        shared.lock().unwrap().last_error = Some(err.to_string());
                        return;
                    }
                };
            shared.lock().unwrap().running = true;
            loop {
                if shared.lock().unwrap().stop {
                    break;
                }
                match device.read_pipe(pipe_id, read_size, read_timeout_ms) {
                    Ok(chunk) => {
                        if chunk.is_empty() {
                            continue;
                        }
                        let mut state = shared.lock().unwrap();
                        state.raw_bytes += chunk.len();
                        state.chunk_count += 1;
                        let words = decode_packed_words(&chunk, &mut state.pending);
                        if !words.is_empty() {
                            let start = state.total_word_count;
                            state.total_word_count += words.len();
                            state.retained_word_count += words.len();
                            state.segments.push_back((start, words));
                            while state.retained_word_count > max_retained_words {
                                if let Some((_, segment)) = state.segments.pop_front() {
                                    state.retained_word_count -= segment.len();
                                } else {
                                    break;
                                }
                            }
                        }
                    }
                    Err(err) => {
                        shared.lock().unwrap().last_error = Some(err.to_string());
                        break;
                    }
                }
            }
            let _ = device.close();
            shared.lock().unwrap().running = false;
        }));
        Ok(())
    }

    pub fn shutdown(&mut self) {
        if let Some(handle) = self.thread.take() {
            self.shared.lock().unwrap().stop = true;
            let _ = handle.join();
        }
    }

    pub fn start(&self) -> FtCaptureSession {
        let state = self.shared.lock().unwrap();
        FtCaptureSession {
            start_word_index: state.total_word_count,
            start_raw_bytes: state.raw_bytes,
            start_chunk_count: state.chunk_count,
        }
    }

    pub fn stop(&self, session: &FtCaptureSession) -> Result<FtCaptureResult> {
        let current_words =
            self.wait_for_quiet_or_deadline(self.post_stop_idle_s, self.post_stop_hard_s);
        let state = self.shared.lock().unwrap();
        let mut words = Vec::new();
        let mut truncated_head = false;
        for (start, segment) in state.segments.iter() {
            let end = start + segment.len();
            if end <= session.start_word_index {
                continue;
            }
            if *start > session.start_word_index {
                truncated_head = true;
            }
            let from = session.start_word_index.saturating_sub(*start);
            words.extend_from_slice(&segment[from..]);
        }
        let words_to_take = current_words.saturating_sub(session.start_word_index);
        words.truncate(words_to_take);
        Ok(FtCaptureResult {
            words,
            raw_bytes: state.raw_bytes.saturating_sub(session.start_raw_bytes),
            chunk_count: state.chunk_count.saturating_sub(session.start_chunk_count),
            pending_bytes_hex: hex::encode(&state.pending),
            decode_swap_u16: false,
            drain_idle_s: self.post_stop_idle_s,
            drain_hard_s: self.post_stop_hard_s,
            retained_words: state.retained_word_count,
            total_words_seen: state.total_word_count,
            max_retained_words: self.max_retained_words,
            truncated_head,
        })
    }

    pub fn set_max_retained_words(&mut self, max_retained_words: usize) {
        self.max_retained_words = max_retained_words.max(1);
    }

    fn wait_for_quiet_or_deadline(&self, idle_s: f64, hard_s: f64) -> usize {
        let start = Instant::now();
        let mut stable_deadline: Option<Instant> = None;
        let mut last_words = self.shared.lock().unwrap().total_word_count;
        loop {
            thread::sleep(Duration::from_millis(10));
            let current_words = self.shared.lock().unwrap().total_word_count;
            let now = Instant::now();
            if current_words != last_words {
                last_words = current_words;
                stable_deadline = Some(now + Duration::from_secs_f64(idle_s));
            } else if stable_deadline.is_none() {
                stable_deadline = Some(now + Duration::from_secs_f64(idle_s));
            } else if now >= stable_deadline.unwrap() {
                return current_words;
            }
            if now.duration_since(start).as_secs_f64() >= hard_s {
                return current_words;
            }
        }
    }
}

impl Drop for Ft600Capture {
    fn drop(&mut self) {
        self.shutdown();
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

pub fn classify_decoded_word(word: u32, index: usize) -> FtDecodedEvent {
    let addr = word & 0x3ffff;
    let data = ((word >> 18) & 0xff) as u8;
    let status = ((word >> 26) & 0x3f) as u8;
    let rw = (status & 0x01) != 0;
    let ce1_active = (status & 0x02) != 0;
    let ce6_active = (status & 0x04) != 0;
    let synthetic_followup = (status & 0x08) != 0;
    let from_cycle_start = (status & 0x10) != 0;
    let ctrl_range = (status & 0x20) != 0;
    let kind = if ce6_active && ctrl_range {
        if rw {
            "ce6_ctrl_read"
        } else {
            "ce6_ctrl_write"
        }
    } else if ce6_active {
        if rw {
            "ce6_read"
        } else {
            "ce6_write"
        }
    } else if ce1_active {
        if rw {
            "ce1_read"
        } else {
            "ce1_write"
        }
    } else if rw {
        "addr_only_read"
    } else {
        "addr_only_write"
    }
    .to_string();
    FtDecodedEvent {
        index,
        raw_word: word,
        addr,
        data,
        status,
        rw,
        ce1_active,
        ce6_active,
        synthetic_followup,
        from_cycle_start,
        ctrl_range,
        kind,
    }
}

pub fn preview_event_stream(
    words: &[u32],
    limit: usize,
    compact: bool,
    window: &str,
    start_tag: Option<u8>,
    stop_tag: Option<u8>,
) -> Vec<serde_json::Value> {
    let mut events: Vec<FtDecodedEvent> = words
        .iter()
        .enumerate()
        .map(|(index, &word)| classify_decoded_word(word, index))
        .collect();
    if window == "measurement" {
        if let (Some(start_tag), Some(stop_tag)) = (start_tag, stop_tag) {
            events = find_measurement_window(&events, start_tag, stop_tag);
        }
    } else if window == "execution" {
        let execution = infer_execution_window(&events);
        if !execution.is_empty() {
            events = execution;
        }
    }
    if compact {
        events = compact_event_stream(&events);
    }
    events
        .into_iter()
        .take(limit)
        .map(|event| {
            let (region, addr_label, note) = annotate_address(event.addr);
            serde_json::json!({
                "index": event.index,
                "raw_word": event.raw_word,
                "raw_hex": format!("{:08X}", event.raw_word),
                "addr": event.addr,
                "data": event.data,
                "status": event.status,
                "kind": event.kind,
                "rw": event.rw,
                "ce1_active": event.ce1_active,
                "ce6_active": event.ce6_active,
                "synthetic_followup": event.synthetic_followup,
                "from_cycle_start": event.from_cycle_start,
                "ctrl_range": event.ctrl_range,
                "region": region,
                "addr_label": addr_label,
                "note": note,
            })
        })
        .collect()
}

fn annotate_address(addr: u32) -> (&'static str, Option<String>, Option<String>) {
    match addr {
        0x1fff0 => ("ce6_ctrl", Some("MARK_START".into()), None),
        0x1fff1 => ("ce6_ctrl", Some("ECHO".into()), None),
        0x1fff2 => ("ce6_ctrl", Some("MARK_STOP".into()), None),
        0x1fff3 => ("ce6_ctrl", Some("MARK_ABORT".into()), None),
        0x1fff4 => ("ce6_ctrl", Some("FT_STREAM_CFG".into()), None),
        _ if (COMMAND_BLOCK_MIN..=COMMAND_BLOCK_MAX).contains(&addr) => (
            "command_block",
            Some(format!("CMD+0x{:02X}", addr - COMMAND_BLOCK_MIN)),
            None,
        ),
        _ if (EXPERIMENT_ROM_MIN..=EXPERIMENT_ROM_MAX).contains(&addr) => {
            ("experiment_rom", None, None)
        }
        _ if (SUPERVISOR_ROM_MIN..=SUPERVISOR_ROM_MAX).contains(&addr) => {
            ("supervisor_rom", None, None)
        }
        _ if (CTRL_RANGE_MIN..=CTRL_RANGE_MAX).contains(&addr) => ("ce6_ctrl", None, None),
        _ if (HI_STACK_MIN..=HI_STACK_MAX).contains(&addr) => (
            "high_stack_window",
            None,
            Some("likely stack/internal high memory".into()),
        ),
        _ => ("other", None, None),
    }
}

fn find_measurement_window(
    events: &[FtDecodedEvent],
    start_tag: u8,
    stop_tag: u8,
) -> Vec<FtDecodedEvent> {
    let start_index = events.iter().position(|event| {
        event.kind == "ce6_ctrl_write" && event.addr == 0x1fff0 && event.data == start_tag
    });
    let Some(start_index) = start_index else {
        return Vec::new();
    };
    for (index, event) in events.iter().enumerate().skip(start_index + 1) {
        if event.kind == "ce6_ctrl_write" && event.addr == 0x1fff2 && event.data == stop_tag {
            return events[start_index..=index].to_vec();
        }
    }
    events[start_index..].to_vec()
}

fn infer_execution_window(events: &[FtDecodedEvent]) -> Vec<FtDecodedEvent> {
    let mut start_index = None;
    let mut left_experiment = false;
    for (index, event) in events.iter().enumerate() {
        if start_index.is_none() {
            if (EXPERIMENT_ROM_MIN..=EXPERIMENT_ROM_MAX).contains(&event.addr) {
                start_index = Some(index);
            }
            continue;
        }
        if !(EXPERIMENT_ROM_MIN..=EXPERIMENT_ROM_MAX).contains(&event.addr) {
            left_experiment = true;
        }
        if left_experiment
            && (SUPERVISOR_ROM_MIN..=SUPERVISOR_ROM_MAX).contains(&event.addr)
            && event.kind.starts_with("ce6_")
        {
            return events[start_index.unwrap()..=index].to_vec();
        }
    }
    start_index
        .map(|index| events[index..].to_vec())
        .unwrap_or_default()
}

fn compact_event_stream(events: &[FtDecodedEvent]) -> Vec<FtDecodedEvent> {
    let mut compacted: Vec<FtDecodedEvent> = Vec::new();
    for event in events {
        if let Some(previous) = compacted.last_mut() {
            if event.synthetic_followup
                && previous.addr == event.addr
                && previous.data == event.data
                && previous.kind.starts_with("addr_only")
                && !event.kind.starts_with("addr_only")
            {
                *previous = event.clone();
                continue;
            }
            if previous.addr == event.addr
                && previous.data == event.data
                && previous.kind == event.kind
                && previous.synthetic_followup == event.synthetic_followup
            {
                continue;
            }
        }
        if event.synthetic_followup && event.kind.starts_with("addr_only") {
            continue;
        }
        compacted.push(event.clone());
    }
    compacted
}
