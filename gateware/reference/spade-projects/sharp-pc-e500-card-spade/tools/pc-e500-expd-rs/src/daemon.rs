use std::fs;
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};

use crate::assembler::{assemble_image_from_source, assemble_image_from_text};
use crate::ft::{preview_event_stream, Ft600Capture};
use crate::protocol::*;
use crate::uart::ExperimentUart;

pub struct ExperimentDaemon {
    assembler_dir: PathBuf,
    safe_asm: PathBuf,
    debug_echo_asm: PathBuf,
    pub uart: ExperimentUart,
    status: String,
    needs_reset: bool,
    last_error: Option<String>,
    last_result: Option<Value>,
    last_ready_line: Option<String>,
    safe_image_programmed: bool,
    safe_image_path: Option<String>,
    safe_image_entry: Option<u32>,
    next_seq: u32,
    scan_index: usize,
    run_counter: u32,
    enable_ft: bool,
    pub ft_capture: Ft600Capture,
}

impl ExperimentDaemon {
    pub fn new(
        port: Option<String>,
        baud: u32,
        idle_gap_s: f64,
        quiet_timeout_s: f64,
        assembler_dir: PathBuf,
        safe_asm: PathBuf,
        monitor_uart: bool,
        enable_ft: bool,
    ) -> Result<Self> {
        let assembler_dir = resolve_existing_dir(&assembler_dir, "assembler checkout")?;
        let safe_asm = resolve_existing_file(&safe_asm, "safe supervisor assembly")?;
        let debug_echo_asm =
            resolve_existing_file(&default_debug_echo_asm(), "debug echo assembly")?;
        let uart = ExperimentUart::open(port, baud, idle_gap_s, quiet_timeout_s, monitor_uart)?;
        let mut ft_capture = Ft600Capture::new(DEFAULT_FT_MAX_RETAINED_WORDS);
        if enable_ft {
            ft_capture.ensure_running()?;
        }
        Ok(Self {
            assembler_dir,
            safe_asm,
            debug_echo_asm,
            uart,
            status: "waiting_for_call".into(),
            needs_reset: false,
            last_error: None,
            last_result: None,
            last_ready_line: None,
            safe_image_programmed: false,
            safe_image_path: None,
            safe_image_entry: None,
            next_seq: 1,
            scan_index: 0,
            run_counter: 0,
            enable_ft,
            ft_capture,
        })
    }

    pub fn close(&mut self) {
        self.ft_capture.shutdown();
        self.uart.close();
    }

    fn poll_unsolicited_lines(&mut self) {
        let current_line_count = self.uart.line_count();
        if self.scan_index > current_line_count {
            self.scan_index = current_line_count;
        }
        let lines = self.uart.lines_since(self.scan_index);
        self.scan_index += lines.len();
        for line in lines {
            if line.text.starts_with(READY_PREFIX) {
                self.status = "idle".into();
                self.needs_reset = false;
                self.last_error = None;
                self.last_ready_line = Some(line.text.clone());
            }
            self.observe_sequence_from_line(&line.text);
        }
    }

    fn observe_sequence_from_line(&mut self, text: &str) {
        if !(text.starts_with(&format!("{BEGIN_PREFIX},"))
            || text.starts_with(&format!("{END_PREFIX},")))
        {
            return;
        }
        let parts: Vec<_> = text.split(',').collect();
        if parts.len() < 2 {
            return;
        }
        if let Ok(value) = u32::from_str_radix(parts[1], 16) {
            let value = value & 0xff;
            if value != 0 && self.next_seq <= value {
                self.next_seq = value + 1;
            }
        }
    }

    fn next_sequence(&mut self) -> u8 {
        let mut value = (self.next_seq & 0xff) as u8;
        if value == 0 {
            value = 1;
        }
        self.next_seq = value as u32 + 1;
        value
    }

    fn make_run_id(&mut self) -> String {
        self.run_counter += 1;
        let now = chrono_like_timestamp();
        format!("{now}-{:04}", self.run_counter)
    }

    pub fn program_safe_image(&mut self) -> Result<Value> {
        let (start_address, image) =
            assemble_image_from_source(&self.safe_asm, &self.assembler_dir)?;
        self.uart.set_timing(DEFAULT_SAFE_TIMING)?;
        self.uart.set_control_timing(DEFAULT_SAFE_CONTROL_TIMING)?;
        self.uart.write_rom_bytes(start_address, &image, true)?;
        self.safe_image_programmed = true;
        self.safe_image_path = Some(self.safe_asm.display().to_string());
        self.safe_image_entry = Some(start_address);
        self.status = "waiting_for_call".into();
        self.needs_reset = false;
        self.last_error = None;
        Ok(json!({
            "status": "ok",
            "safe_image_programmed": true,
            "safe_image_path": self.safe_asm.display().to_string(),
            "entry": start_address,
            "timing": DEFAULT_SAFE_TIMING,
            "control_timing": DEFAULT_SAFE_CONTROL_TIMING,
        }))
    }

    pub fn debug_echo_short(&mut self, timeout_s: f64) -> Result<Value> {
        let (start_address, image) =
            assemble_image_from_source(&self.debug_echo_asm, &self.assembler_dir)?;
        self.uart.set_timing(5)?;
        self.uart.set_control_timing(10)?;
        self.uart.write_rom_bytes(start_address, &image, true)?;
        self.uart.synchronize_rx_boundary(0.2, 2.0)?;
        let raw_index = self.uart.raw_count();
        match self.uart.wait_for_bytes(b"OK\r\n", timeout_s, raw_index) {
            Ok(captured) => {
                let payload = json!({
                    "status": "ok",
                    "action": "debug_echo_short",
                    "entry": start_address,
                    "asm_path": self.debug_echo_asm.display().to_string(),
                    "captured_text": render_terminal_bytes(&captured),
                    "captured_hex": hex::encode(&captured),
                    "message": "Observed OK\\r\\n from the debug echo payload.",
                });
                self.last_result = Some(payload.clone());
                Ok(payload)
            }
            Err(err) => {
                let recent = self.uart.raw_since(raw_index);
                let payload = json!({
                    "status": "timeout",
                    "action": "debug_echo_short",
                    "entry": start_address,
                    "asm_path": self.debug_echo_asm.display().to_string(),
                    "needs_reset": false,
                    "error": err.to_string(),
                    "captured_text": render_terminal_bytes(&recent),
                    "captured_hex": hex::encode(&recent),
                    "message": "Run CALL &10100 on the PC-E500 while this command is waiting.",
                });
                self.last_result = Some(payload.clone());
                Ok(payload)
            }
        }
    }

    pub fn wait_ready(&mut self, timeout_s: f64) -> Result<Value> {
        self.poll_unsolicited_lines();
        if self.status == "idle" {
            return self.status_payload();
        }
        let line = self.uart.wait_for_line(
            |text| text.starts_with(READY_PREFIX),
            timeout_s,
            self.scan_index,
        )?;
        self.last_ready_line = Some(line.text);
        self.poll_unsolicited_lines();
        self.status = "idle".into();
        self.needs_reset = false;
        self.status_payload()
    }

    pub fn status_payload(&mut self) -> Result<Value> {
        self.poll_unsolicited_lines();
        Ok(json!({
            "status": "ok",
            "device_state": self.status,
            "needs_reset": self.needs_reset,
            "last_error": self.last_error,
            "last_ready_line": self.last_ready_line,
            "safe_image_programmed": self.safe_image_programmed,
            "safe_image_path": self.safe_image_path,
            "safe_image_entry": self.safe_image_entry,
            "ft_capture": {
                "max_retained_words": self.ft_capture.max_retained_words,
            },
            "uart": self.uart.stats(),
            "recent_uart_lines": self.uart.last_lines(20),
        }))
    }

    pub fn stream_command(&mut self, command: &str) -> Result<Value> {
        let reply = self.uart.send_command(command, Some(1.0))?;
        self.poll_unsolicited_lines();
        Ok(json!({
            "status": "ok",
            "action": command,
            "reply_text": render_terminal_bytes(&reply),
            "reply_hex": hex::encode(&reply),
            "recent_uart_lines": self.uart.last_lines(20),
        }))
    }

    pub fn run_experiment(
        &mut self,
        script_path: PathBuf,
        script_args: Vec<String>,
    ) -> Result<Value> {
        self.poll_unsolicited_lines();
        if self.status != "idle" || self.needs_reset {
            anyhow::bail!("device is not idle; wait for XR,READY or reset + CALL &10000");
        }

        let plan = self.load_plan(&script_path, &script_args)?;
        let run_id = self.make_run_id();
        let timing = plan.timing;
        let control_timing = plan.control_timing;
        let timeout_s = plan.timeout_s;

        let (start_address, image) = if let Some(asm_source) = &plan.asm_source {
            assemble_image_from_source(&PathBuf::from(asm_source), &self.assembler_dir)?
        } else if let Some(asm_text) = &plan.asm_text {
            assemble_image_from_text(asm_text, &self.assembler_dir)?
        } else {
            anyhow::bail!("experiment plan must provide asm_source or asm_text");
        };

        let image_to_program = if plan.fill_experiment_region {
            self.build_full_experiment_region(start_address, &image)?
        } else {
            image.clone()
        };
        let sequence = self.next_sequence();
        let command_block = self.compose_command_block(&plan, sequence)?;

        self.uart.set_timing(timing)?;
        self.uart.set_control_timing(control_timing)?;
        self.uart.clear_measurements()?;
        self.uart.write_rom_bytes(
            if plan.fill_experiment_region {
                EXPERIMENT_MIN
            } else {
                start_address
            },
            &image_to_program,
            true,
        )?;
        self.uart.synchronize_rx_boundary(0.2, 2.0)?;
        let line_index = self.uart.line_count();
        self.ft_capture.read_size = plan.ft_read_size;
        self.ft_capture.read_timeout_ms = plan.ft_read_timeout_ms;
        self.ft_capture.post_stop_idle_s = plan.ft_post_stop_idle_s;
        self.ft_capture.post_stop_hard_s = plan.ft_post_stop_hard_s;
        self.ft_capture
            .set_max_retained_words(plan.ft_max_retained_words);
        let ft_session = if plan.ft_capture {
            if !self.enable_ft {
                anyhow::bail!("FT capture requested but daemon started with FT disabled");
            }
            Some(self.ft_capture.start())
        } else {
            None
        };
        self.commit_command_block(&command_block)?;
        self.status = "running".into();

        let begin_text = format!("{BEGIN_PREFIX},{sequence:02X}");
        let end_prefix = format!("{END_PREFIX},{sequence:02X},");

        let result = match (
            self.uart
                .wait_for_line(|text| text == begin_text, timeout_s, line_index),
            self.uart
                .wait_for_line(|text| text.starts_with(&end_prefix), timeout_s, line_index),
        ) {
            (Ok(begin_line), Ok(end_line)) => {
                let ft_capture_result = if let Some(session) = &ft_session {
                    Some(self.ft_capture.stop(session)?)
                } else {
                    None
                };
                let measurements = self.uart.dump_measurements()?;
                let xr_lines: Vec<String> = self
                    .uart
                    .lines_since(line_index)
                    .into_iter()
                    .filter(|line| line.text.starts_with("XR,"))
                    .map(|line| line.text)
                    .collect();
                let mut result = json!({
                    "status": "ok",
                    "run_id": run_id,
                    "needs_reset": false,
                    "experiment": plan.name.clone().unwrap_or_else(|| script_path.file_stem().unwrap_or_default().to_string_lossy().to_string()),
                    "script_path": script_path.display().to_string(),
                    "script_args": script_args,
                    "timing": timing,
                    "control_timing": control_timing,
                    "begin_line": begin_line.text,
                    "end_line": end_line.text,
                    "measurement": measurements,
                    "uart_lines": xr_lines,
                    "plan": plan.public_json(),
                });
                if let Some(ft_capture_result) = ft_capture_result {
                    result["ft_capture"] =
                        self.build_ft_capture_payload(&plan, &ft_capture_result, &measurements)?;
                }
                if let Some(parsed) =
                    self.parse_experiment_result(&script_path, &script_args, &result)?
                {
                    result["parsed"] = parsed;
                }
                self.status = "idle".into();
                self.needs_reset = false;
                self.last_error = None;
                self.last_result = Some(result.clone());
                result
            }
            _ => {
                let ft_capture_result = if let Some(session) = &ft_session {
                    self.ft_capture.stop(session).ok()
                } else {
                    None
                };
                let measurements = self.uart.dump_measurements().unwrap_or_default();
                let xr_lines: Vec<String> = self
                    .uart
                    .lines_since(line_index)
                    .into_iter()
                    .filter(|line| line.text.starts_with("XR,"))
                    .map(|line| line.text)
                    .collect();
                self.handle_timeout(
                    &run_id,
                    "timed out waiting for UART line",
                    Some(&plan),
                    Some(&script_path),
                    Some(&script_args),
                    Some(timing),
                    Some(control_timing),
                    &measurements,
                    &xr_lines,
                    ft_capture_result.as_ref(),
                )?
            }
        };

        Ok(result)
    }

    pub fn handle_request(&mut self, request: Value) -> Result<Value> {
        match request["action"].as_str().unwrap_or_default() {
            "status" => self.status_payload(),
            "stream_on" => self.stream_command("F1"),
            "stream_off" => self.stream_command("F0"),
            "stream_status" => self.stream_command("F?"),
            "arm_safe" => self.program_safe_image(),
            "debug_echo_short" => {
                self.debug_echo_short(request["timeout_s"].as_f64().unwrap_or(10.0))
            }
            "wait_ready" => self.wait_ready(request["timeout_s"].as_f64().unwrap_or(30.0)),
            "run" => {
                let script = PathBuf::from(
                    request["script"]
                        .as_str()
                        .ok_or_else(|| anyhow!("missing script"))?,
                );
                let args = request["script_args"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|value| value.as_str().map(ToOwned::to_owned))
                    .collect();
                self.run_experiment(script, args)
            }
            "shutdown" => Ok(json!({"status":"ok","shutdown":true})),
            other => Err(anyhow!("unknown action {other:?}")),
        }
    }

    fn load_plan(&self, script_path: &Path, script_args: &[String]) -> Result<RunPlan> {
        let script_path = resolve_existing_file(script_path, "experiment script")?;
        let output = Command::new("python3")
            .arg(&script_path)
            .arg("plan")
            .args(script_args)
            .output()
            .with_context(|| format!("failed to run {} plan", script_path.display()))?;
        if !output.status.success() {
            anyhow::bail!(
                "experiment plan failed for {}\nstdout:\n{}\nstderr:\n{}",
                script_path.display(),
                String::from_utf8_lossy(&output.stdout),
                String::from_utf8_lossy(&output.stderr)
            );
        }
        let mut plan: RunPlan = serde_json::from_slice(&output.stdout)?;
        plan.extra.insert(
            "_script_path".into(),
            Value::String(script_path.display().to_string()),
        );
        plan.extra.insert(
            "_script_args".into(),
            Value::Array(script_args.iter().cloned().map(Value::String).collect()),
        );
        Ok(plan)
    }

    fn parse_experiment_result(
        &self,
        script_path: &Path,
        script_args: &[String],
        raw_result: &Value,
    ) -> Result<Option<Value>> {
        let temp_path = temp_json_path();
        fs::write(&temp_path, serde_json::to_vec(raw_result)?)?;
        let output = Command::new("python3")
            .arg(script_path)
            .arg("parse")
            .arg(&temp_path)
            .args(script_args)
            .output()
            .with_context(|| format!("failed to run {} parse", script_path.display()))?;
        let _ = fs::remove_file(&temp_path);
        if !output.status.success() {
            return Ok(None);
        }
        Ok(Some(serde_json::from_slice(&output.stdout)?))
    }

    fn build_full_experiment_region(&self, start_address: u32, image: &[u8]) -> Result<Vec<u8>> {
        if start_address != EXPERIMENT_MIN {
            anyhow::bail!(
                "experiment entry must start at {:05X}; assembled image starts at {:05X}",
                EXPERIMENT_MIN,
                start_address
            );
        }
        let end = start_address + image.len() as u32 - 1;
        if start_address < EXPERIMENT_MIN || end > EXPERIMENT_MAX {
            anyhow::bail!(
                "experiment image spans {:05X}..{:05X}, outside experiment region {:05X}..{:05X}",
                start_address,
                end,
                EXPERIMENT_MIN,
                EXPERIMENT_MAX
            );
        }
        let mut region = vec![DEFAULT_FILL_BYTE; (EXPERIMENT_MAX - EXPERIMENT_MIN + 1) as usize];
        let offset = (start_address - EXPERIMENT_MIN) as usize;
        region[offset..offset + image.len()].copy_from_slice(image);
        Ok(region)
    }

    fn compose_command_block(&self, plan: &RunPlan, sequence: u8) -> Result<Vec<u8>> {
        let mut block = vec![0u8; (CMD_SEQ - CMD_BASE + 1) as usize];
        block[(CMD_MAGIC0 - CMD_BASE) as usize] = 0x58;
        block[(CMD_MAGIC1 - CMD_BASE) as usize] = 0x52;
        block[(CMD_VERSION - CMD_BASE) as usize] = 0x01;
        let mut flags = (plan.flags & 0xff) as u8;
        if plan.ft_capture {
            flags |= CMD_FLAG_ENABLE_FT_CAPTURE;
        }
        block[(CMD_FLAGS - CMD_BASE) as usize] = flags;
        block[(CMD_START_TAG - CMD_BASE) as usize] = (plan.start_tag & 0xff) as u8;
        block[(CMD_STOP_TAG - CMD_BASE) as usize] = (plan.stop_tag & 0xff) as u8;
        if plan.args.len() > CMD_ARGS_COUNT {
            anyhow::bail!("experiment args exceed {CMD_ARGS_COUNT} bytes");
        }
        for (index, value) in plan.args.iter().enumerate() {
            block[(CMD_ARGS_BASE - CMD_BASE) as usize + index] = (*value & 0xff) as u8;
        }
        block[(CMD_SEQ - CMD_BASE) as usize] = sequence;
        Ok(block)
    }

    fn commit_command_block(&self, block: &[u8]) -> Result<()> {
        let body = &block[..block.len() - 1];
        let seq = *block.last().unwrap();
        self.uart.write_rom_bytes(CMD_BASE, body, true)?;
        self.uart.synchronize_rx_boundary(0.2, 2.0)?;
        self.uart.write_rom_byte(CMD_SEQ, seq)?;
        Ok(())
    }

    fn build_ft_capture_payload(
        &self,
        plan: &RunPlan,
        ft: &crate::ft::FtCaptureResult,
        measurements: &[ParsedMeasurement],
    ) -> Result<Value> {
        Ok(json!({
            "enabled": true,
            "word_count": ft.words.len(),
            "raw_bytes": ft.raw_bytes,
            "chunk_count": ft.chunk_count,
            "pending_bytes_hex": ft.pending_bytes_hex,
            "decode_swap_u16": ft.decode_swap_u16,
            "drain_idle_s": ft.drain_idle_s,
            "drain_hard_s": ft.drain_hard_s,
            "retained_words": ft.retained_words,
            "total_words_seen": ft.total_words_seen,
            "max_retained_words": ft.max_retained_words,
            "truncated_head": ft.truncated_head,
            "health": if measurements.iter().all(|m| m.ft_overflow == 0) { "ok" } else { "overflow" },
            "words": ft.words,
            "preview": preview_event_stream(&ft.words, 32, false, "all", None, None),
            "compact_preview": preview_event_stream(&ft.words, 64, true, "all", None, None),
            "execution_preview": preview_event_stream(&ft.words, 64, true, "execution", None, None),
            "measurement_preview": preview_event_stream(
                &ft.words,
                64,
                true,
                "measurement",
                Some((plan.start_tag & 0xff) as u8),
                Some((plan.stop_tag & 0xff) as u8),
            ),
        }))
    }

    fn handle_timeout(
        &mut self,
        run_id: &str,
        reason: &str,
        plan: Option<&RunPlan>,
        script_path: Option<&Path>,
        script_args: Option<&[String]>,
        timing: Option<u32>,
        control_timing: Option<u32>,
        measurements: &[ParsedMeasurement],
        uart_lines: &[String],
        ft_capture_result: Option<&crate::ft::FtCaptureResult>,
    ) -> Result<Value> {
        self.status = "needs_reset".into();
        self.needs_reset = true;
        self.last_error = Some(reason.to_string());
        let (safe_programmed, safe_error) = match self.program_safe_image() {
            Ok(result) => (
                result["safe_image_programmed"].as_bool().unwrap_or(false),
                None,
            ),
            Err(err) => (false, Some(err.to_string())),
        };
        self.status = "needs_reset".into();
        self.needs_reset = true;
        self.last_error = Some(reason.to_string());
        let mut payload = json!({
            "status": "timeout",
            "run_id": run_id,
            "needs_reset": true,
            "safe_image_programmed": safe_programmed,
            "safe_image_error": safe_error,
            "message": "Reset the PC-E500 and run CALL &10000 again.",
            "error": reason,
        });
        if let Some(plan) = plan {
            payload["experiment"] = Value::String(plan.name.clone().unwrap_or_else(|| {
                script_path
                    .and_then(|p| p.file_stem())
                    .unwrap_or_default()
                    .to_string_lossy()
                    .to_string()
            }));
            payload["script_path"] = Value::String(
                script_path
                    .map(|p| p.display().to_string())
                    .unwrap_or_default(),
            );
            payload["script_args"] = Value::Array(
                script_args
                    .unwrap_or(&[])
                    .iter()
                    .cloned()
                    .map(Value::String)
                    .collect(),
            );
            payload["timing"] = json!(timing);
            payload["control_timing"] = json!(control_timing);
            payload["measurement"] = serde_json::to_value(measurements)?;
            payload["uart_lines"] = serde_json::to_value(uart_lines)?;
            payload["plan"] = plan.public_json();
        }
        if let (Some(plan), Some(ft_capture_result)) = (plan, ft_capture_result) {
            payload["ft_capture"] =
                self.build_ft_capture_payload(plan, ft_capture_result, measurements)?;
        }
        self.last_result = Some(payload.clone());
        Ok(payload)
    }
}

pub fn serve(socket_path: &Path, daemon: &mut ExperimentDaemon) -> Result<i32> {
    if let Some(parent) = socket_path.parent() {
        fs::create_dir_all(parent)?;
    }
    if socket_path.exists() {
        let _ = fs::remove_file(socket_path);
    }
    let listener = UnixListener::bind(socket_path)?;
    let exit_code = 0;
    for stream in listener.incoming() {
        let mut stream = stream?;
        let response = match read_request(&mut stream) {
            Ok(request) => daemon
                .handle_request(request)
                .unwrap_or_else(|err| json!({"status":"error","error":err.to_string()})),
            Err(err) => json!({"status":"error","error":err.to_string()}),
        };
        let line = serde_json::to_vec(&response)?;
        stream.write_all(&line)?;
        stream.write_all(b"\n")?;
        if response["shutdown"].as_bool().unwrap_or(false) {
            break;
        }
    }
    let _ = fs::remove_file(socket_path);
    Ok(exit_code)
}

fn read_request(stream: &mut UnixStream) -> Result<Value> {
    let mut payload = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let read = stream.read(&mut chunk)?;
        if read == 0 {
            break;
        }
        payload.extend_from_slice(&chunk[..read]);
        if chunk[..read].contains(&b'\n') {
            break;
        }
    }
    if payload.is_empty() {
        anyhow::bail!("empty request");
    }
    Ok(serde_json::from_slice(&payload)?)
}

fn temp_json_path() -> PathBuf {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("pc_e500_expd_rs_{nanos}.json"))
}

fn chrono_like_timestamp() -> String {
    let now = std::time::SystemTime::now();
    let datetime: chrono_stub::DateTime = now.into();
    datetime.format()
}

mod chrono_stub {
    use std::time::{Duration, SystemTime, UNIX_EPOCH};

    pub struct DateTime {
        secs: i64,
    }

    impl From<SystemTime> for DateTime {
        fn from(value: SystemTime) -> Self {
            let secs = value
                .duration_since(UNIX_EPOCH)
                .unwrap_or(Duration::ZERO)
                .as_secs() as i64;
            Self { secs }
        }
    }

    impl DateTime {
        pub fn format(&self) -> String {
            let tm = unsafe {
                let mut result = std::mem::zeroed::<libc::tm>();
                let secs = self.secs;
                libc::localtime_r(&secs, &mut result);
                result
            };
            format!(
                "{:04}{:02}{:02}-{:02}{:02}{:02}",
                tm.tm_year + 1900,
                tm.tm_mon + 1,
                tm.tm_mday,
                tm.tm_hour,
                tm.tm_min,
                tm.tm_sec
            )
        }
    }
}
