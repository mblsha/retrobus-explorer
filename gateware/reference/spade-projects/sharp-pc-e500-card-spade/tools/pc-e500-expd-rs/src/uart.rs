use std::collections::VecDeque;
use std::io::{Read, Write};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Result};
use serde_json::json;
use serialport::SerialPort;

use crate::protocol::{
    absolute_address, build_write_payload, normalize_reply_lines, parse_measure_status_lines,
    parse_measurement_lines, render_terminal_bytes, rom_offset_from_address, ParsedMeasureStatus,
    ParsedMeasurement, DEFAULT_BAUD, DEFAULT_COMMAND_TIMEOUT_S, MEASURE_END_LINE,
};

#[derive(Clone, Debug)]
pub struct UartLine {
    pub timestamp: Instant,
    pub text: String,
}

struct SharedState {
    raw: Vec<u8>,
    partial_line: Vec<u8>,
    lines: VecDeque<UartLine>,
    line_start: usize,
    last_rx_at: Option<Instant>,
    rx_total: usize,
    tx_total: usize,
    stop: bool,
}

impl Default for SharedState {
    fn default() -> Self {
        Self {
            raw: Vec::new(),
            partial_line: Vec::new(),
            lines: VecDeque::with_capacity(2048),
            line_start: 0,
            last_rx_at: None,
            rx_total: 0,
            tx_total: 0,
            stop: false,
        }
    }
}

pub struct ExperimentUart {
    port: Arc<Mutex<Box<dyn SerialPort>>>,
    shared: Arc<(Mutex<SharedState>, Condvar)>,
    reader: Option<thread::JoinHandle<()>>,
    idle_gap: Duration,
    quiet_timeout: Duration,
    command_lock: Mutex<()>,
}

impl ExperimentUart {
    pub fn open(
        port_name: Option<String>,
        baud: u32,
        idle_gap_s: f64,
        quiet_timeout_s: f64,
        monitor_uart: bool,
    ) -> Result<Self> {
        let port_name = port_name.unwrap_or_else(|| detect_second_usb_serial_port().unwrap());
        let port = serialport::new(&port_name, baud)
            .timeout(Duration::from_millis(50))
            .open()
            .map_err(|err| anyhow!("failed to open serial port {port_name}: {err}"))?;
        let port = Arc::new(Mutex::new(port));
        {
            let port_lock = port.lock().unwrap();
            let _ = port_lock.clear(serialport::ClearBuffer::Input);
            let _ = port_lock.clear(serialport::ClearBuffer::Output);
        }

        let shared = Arc::new((Mutex::new(SharedState::default()), Condvar::new()));
        let reader_port = port.clone();
        let reader_shared = shared.clone();
        let reader = thread::spawn(move || reader_loop(reader_port, reader_shared, monitor_uart));

        Ok(Self {
            port,
            shared,
            reader: Some(reader),
            idle_gap: Duration::from_secs_f64(idle_gap_s.max(0.0)),
            quiet_timeout: Duration::from_secs_f64(quiet_timeout_s.max(0.0)),
            command_lock: Mutex::new(()),
        })
    }

    pub fn close(&mut self) {
        {
            let (state, cv) = &*self.shared;
            state.lock().unwrap().stop = true;
            cv.notify_all();
        }
        if let Some(handle) = self.reader.take() {
            let _ = handle.join();
        }
    }

    pub fn stats(&self) -> serde_json::Value {
        let (state, _) = &*self.shared;
        let state = state.lock().unwrap();
        let quiet_for = state.last_rx_at.map(|at| at.elapsed().as_secs_f64());
        json!({
            "rx_total": state.rx_total,
            "tx_total": state.tx_total,
            "buffered_raw": state.raw.len(),
            "line_count": state.line_start + state.lines.len(),
            "quiet_for_s": quiet_for,
        })
    }

    pub fn line_count(&self) -> usize {
        let (state, _) = &*self.shared;
        let state = state.lock().unwrap();
        state.line_start + state.lines.len()
    }

    pub fn raw_count(&self) -> usize {
        self.shared.0.lock().unwrap().raw.len()
    }

    pub fn raw_since(&self, index: usize) -> Vec<u8> {
        let (state, _) = &*self.shared;
        let state = state.lock().unwrap();
        state.raw.get(index..).unwrap_or_default().to_vec()
    }

    pub fn lines_since(&self, index: usize) -> Vec<UartLine> {
        let (state, _) = &*self.shared;
        let state = state.lock().unwrap();
        let start = index.saturating_sub(state.line_start);
        state.lines.iter().skip(start).cloned().collect()
    }

    pub fn last_lines(&self, limit: usize) -> Vec<String> {
        let (state, _) = &*self.shared;
        let state = state.lock().unwrap();
        state
            .lines
            .iter()
            .rev()
            .take(limit)
            .map(|line| line.text.clone())
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect()
    }

    pub fn discard_buffered_input(&self) -> Result<()> {
        let _guard = self.command_lock.lock().unwrap();
        {
            let port = self.port.lock().unwrap();
            let _ = port.clear(serialport::ClearBuffer::Input);
        }
        let (state, cv) = &*self.shared;
        let mut state = state.lock().unwrap();
        state.raw.clear();
        state.partial_line.clear();
        state.lines.clear();
        state.line_start = 0;
        state.last_rx_at = None;
        cv.notify_all();
        Ok(())
    }

    pub fn synchronize_rx_boundary(&self, settle_s: f64, timeout_s: f64) -> Result<()> {
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_s);
        loop {
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                anyhow::bail!("timed out synchronizing UART receive boundary");
            }
            self.wait_until_quiet(Some(remaining), None)?;
            self.discard_buffered_input()?;

            let settle_deadline = Instant::now() + Duration::from_secs_f64(settle_s);
            let (state_lock, cv) = &*self.shared;
            let mut state = state_lock.lock().unwrap();
            while state.raw.is_empty() {
                let remaining = settle_deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    return Ok(());
                }
                let (new_state, _) = cv.wait_timeout(state, remaining).unwrap();
                state = new_state;
            }
        }
    }

    pub fn wait_until_quiet(
        &self,
        timeout: Option<Duration>,
        idle_gap: Option<Duration>,
    ) -> Result<()> {
        let timeout = timeout.unwrap_or(self.quiet_timeout);
        let idle_gap = idle_gap.unwrap_or(self.idle_gap);
        let deadline = Instant::now() + timeout;
        let (state_lock, cv) = &*self.shared;
        let mut state = state_lock.lock().unwrap();
        loop {
            let quiet = state
                .last_rx_at
                .map(|at| at.elapsed() >= idle_gap)
                .unwrap_or(true);
            if quiet {
                return Ok(());
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                anyhow::bail!(
                    "UART did not go quiet for {:.3}s within {:.3}s",
                    idle_gap.as_secs_f64(),
                    timeout.as_secs_f64()
                );
            }
            let wait_for = remaining.min(idle_gap);
            let (new_state, _) = cv.wait_timeout(state, wait_for).unwrap();
            state = new_state;
        }
    }

    pub fn wait_for_line<F>(
        &self,
        predicate: F,
        timeout_s: f64,
        start_index: usize,
    ) -> Result<UartLine>
    where
        F: Fn(&str) -> bool,
    {
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_s);
        let (state_lock, cv) = &*self.shared;
        let mut state = state_lock.lock().unwrap();
        loop {
            let start = start_index.saturating_sub(state.line_start);
            for line in state.lines.iter().skip(start) {
                if predicate(&line.text) {
                    return Ok(line.clone());
                }
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                anyhow::bail!("timed out waiting for UART line");
            }
            let (new_state, _) = cv
                .wait_timeout(state, remaining.min(self.idle_gap))
                .unwrap();
            state = new_state;
        }
    }

    pub fn wait_for_bytes(
        &self,
        needle: &[u8],
        timeout_s: f64,
        start_index: usize,
    ) -> Result<Vec<u8>> {
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_s);
        let (state_lock, cv) = &*self.shared;
        let mut state = state_lock.lock().unwrap();
        loop {
            let haystack = state.raw.get(start_index..).unwrap_or_default();
            if haystack
                .windows(needle.len())
                .any(|window| window == needle)
            {
                return Ok(haystack.to_vec());
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                anyhow::bail!("timed out waiting for UART bytes");
            }
            let (new_state, _) = cv
                .wait_timeout(state, remaining.min(self.idle_gap))
                .unwrap();
            state = new_state;
        }
    }

    pub fn send_command(&self, command: &str, timeout_s: Option<f64>) -> Result<Vec<u8>> {
        let mut payload = command.as_bytes().to_vec();
        payload.push(b'\r');
        self.send_payload(&payload, timeout_s)
    }

    pub fn send_payload(&self, payload: &[u8], timeout_s: Option<f64>) -> Result<Vec<u8>> {
        let _guard = self.command_lock.lock().unwrap();
        self.wait_until_quiet(None, None)?;
        let start = self.raw_count();
        {
            let mut port = self.port.lock().unwrap();
            port.write_all(payload)?;
            port.flush()?;
        }
        {
            let (state, _) = &*self.shared;
            state.lock().unwrap().tx_total += payload.len();
        }

        let timeout = Duration::from_secs_f64(timeout_s.unwrap_or(DEFAULT_COMMAND_TIMEOUT_S));
        let deadline = Instant::now() + timeout;
        let (state_lock, cv) = &*self.shared;
        let mut state = state_lock.lock().unwrap();
        let mut saw_reply = false;
        loop {
            let current_len = state.raw.len();
            if current_len > start {
                saw_reply = true;
            }
            let quiet = saw_reply
                && state
                    .last_rx_at
                    .map(|at| at.elapsed() >= self.idle_gap)
                    .unwrap_or(false);
            if quiet {
                return Ok(state.raw[start..current_len].to_vec());
            }
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Ok(state
                    .raw
                    .get(start..current_len)
                    .unwrap_or_default()
                    .to_vec());
            }
            let (new_state, _) = cv
                .wait_timeout(state, remaining.min(self.idle_gap))
                .unwrap();
            state = new_state;
        }
    }

    pub fn run_raw(&self, text: &str) -> Result<Vec<String>> {
        Ok(normalize_reply_lines(&self.send_command(text, None)?))
    }

    pub fn set_timing(&self, cycles: u32) -> Result<()> {
        let reply = self.run_raw(&format!("t{cycles:02}"))?;
        let expected = format!("T={:03}ns", cycles * 10);
        if !reply.iter().any(|line| line == &expected) {
            anyhow::bail!("expected {expected:?} in timing reply, got {reply:?}");
        }
        Ok(())
    }

    pub fn set_control_timing(&self, cycles: u32) -> Result<()> {
        let reply = self.run_raw(&format!("c{cycles:02}"))?;
        let expected_a = format!("C={:03}ns", cycles * 10);
        let expected_b = format!("C={}ns", cycles * 10);
        if !reply
            .iter()
            .any(|line| line == &expected_a || line == &expected_b)
        {
            anyhow::bail!("unexpected control timing reply {reply:?}");
        }
        Ok(())
    }

    pub fn read_rom_byte(&self, address: u32) -> Result<u8> {
        let offset = rom_offset_from_address(address)?;
        let reply = self.run_raw(&format!("R{offset:03X}"))?;
        let result = reply
            .last()
            .ok_or_else(|| anyhow!("unexpected ROM read reply"))?;
        let (addr_text, value_text) = result
            .split_once('=')
            .ok_or_else(|| anyhow!("bad ROM read line"))?;
        if u32::from_str_radix(addr_text, 16)? as usize != offset {
            anyhow::bail!("read reply address mismatch: {result}");
        }
        Ok(u8::from_str_radix(value_text, 16)?)
    }

    pub fn write_rom_byte(&self, address: u32, value: u8) -> Result<()> {
        let offset = rom_offset_from_address(address)?;
        let reply = self.run_raw(&format!("W{offset:03X}={value:02X}"))?;
        if !reply.iter().any(|line| line == "OK") {
            anyhow::bail!("unexpected ROM write reply {reply:?}");
        }
        Ok(())
    }

    pub fn write_rom_bytes(&self, start_address: u32, data: &[u8], fast: bool) -> Result<()> {
        let start_offset = rom_offset_from_address(start_address)?;
        if start_offset + data.len() > crate::protocol::CARD_ROM_SIZE {
            anyhow::bail!("ROM write range exceeds 2 KiB card ROM window");
        }
        if fast {
            let payload = build_write_payload(start_offset, data);
            let wire_time = payload.len() as f64 * 10.0 / DEFAULT_BAUD as f64;
            let processing_margin = (data.len() as f64 * 0.002).max(1.0);
            self.send_payload(
                &payload,
                Some((wire_time + processing_margin).max(DEFAULT_COMMAND_TIMEOUT_S)),
            )?;
            return Ok(());
        }
        for (index, value) in data.iter().enumerate() {
            self.write_rom_byte(absolute_address(start_offset + index), *value)?;
        }
        Ok(())
    }

    pub fn clear_measurements(&self) -> Result<()> {
        let reply = self.run_raw("m!")?;
        if !reply.iter().any(|line| line == "OK") {
            anyhow::bail!("unexpected measurement clear reply {reply:?}");
        }
        Ok(())
    }

    pub fn read_measure_status(&self) -> Result<ParsedMeasureStatus> {
        let lines = self.run_raw("m?")?;
        parse_measure_status_lines(&lines)
    }

    pub fn dump_measurements(&self) -> Result<Vec<ParsedMeasurement>> {
        let _guard = self.command_lock.lock().unwrap();
        self.wait_until_quiet(None, None)?;
        let line_index = self.line_count();
        {
            let mut port = self.port.lock().unwrap();
            port.write_all(b"m\r")?;
            port.flush()?;
        }
        {
            let (state, _) = &*self.shared;
            state.lock().unwrap().tx_total += 2;
        }
        self.wait_for_line(|text| text == MEASURE_END_LINE, 2.0, line_index)?;
        self.wait_until_quiet(Some(Duration::from_secs(2)), None)?;
        let lines: Vec<String> = self
            .lines_since(line_index)
            .into_iter()
            .map(|line| line.text)
            .collect();
        parse_measurement_lines(&lines)
    }
}

impl Drop for ExperimentUart {
    fn drop(&mut self) {
        self.close();
    }
}

fn reader_loop(
    port: Arc<Mutex<Box<dyn SerialPort>>>,
    shared: Arc<(Mutex<SharedState>, Condvar)>,
    monitor: bool,
) {
    let mut chunk = [0u8; 256];
    loop {
        {
            if shared.0.lock().unwrap().stop {
                return;
            }
        }
        let read = {
            let mut port = port.lock().unwrap();
            match port.read(&mut chunk) {
                Ok(0) => continue,
                Ok(read) => read,
                Err(err) if err.kind() == std::io::ErrorKind::TimedOut => continue,
                Err(_) => return,
            }
        };
        let now = Instant::now();
        let (state_lock, cv) = &*shared;
        let mut state = state_lock.lock().unwrap();
        state.raw.extend_from_slice(&chunk[..read]);
        state.rx_total += read;
        state.last_rx_at = Some(now);
        append_lines(&mut state, &chunk[..read], now);
        cv.notify_all();
        drop(state);
        if monitor {
            print!("{}", render_terminal_bytes(&chunk[..read]));
            let _ = std::io::stdout().flush();
        }
    }
}

fn append_lines(state: &mut SharedState, chunk: &[u8], now: Instant) {
    for &byte in chunk {
        if byte == b'\n' {
            let text = String::from_utf8_lossy(&state.partial_line)
                .trim_end_matches('\r')
                .to_string();
            if state.lines.len() == 2048 {
                state.line_start += 1;
                state.lines.pop_front();
            }
            state.lines.push_back(UartLine {
                timestamp: now,
                text,
            });
            state.partial_line.clear();
        } else {
            state.partial_line.push(byte);
        }
    }
}

fn detect_second_usb_serial_port() -> Result<String> {
    let mut ports: Vec<String> = std::fs::read_dir("/dev")?
        .filter_map(|entry| {
            let entry = entry.ok()?;
            let name = entry.file_name().into_string().ok()?;
            if name.starts_with("cu.usbserial-") {
                Some(format!("/dev/{name}"))
            } else {
                None
            }
        })
        .collect();
    ports.sort();
    ports
        .get(1)
        .cloned()
        .ok_or_else(|| anyhow!("expected at least two /dev/cu.usbserial-* devices"))
}
