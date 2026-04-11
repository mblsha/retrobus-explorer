use std::collections::VecDeque;
use std::fs;
use std::path::PathBuf;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Context, Result};
use crossbeam_channel::{unbounded, Receiver, Sender};
use serialport::SerialPort;

use crate::d3xx::Device;
use crate::lcd::{LcdModel, DISPLAY_HEIGHT, DISPLAY_WIDTH};
use crate::protocol::{
    decode_packed_words, parse_stream_status_line, SampledWord, StreamStatus, DEFAULT_PIPE_ID,
    DEFAULT_READ_SIZE, DEFAULT_READ_TIMEOUT_MS, DEFAULT_STREAM_SIZE, LCD_WRITE_ADDR_MAX,
    LCD_WRITE_ADDR_MIN,
};

#[derive(Clone, Debug)]
pub struct BackendConfig {
    pub ft_library_path: Option<PathBuf>,
    pub serial_port: Option<String>,
    pub baud_rate: u32,
    pub pipe_id: u8,
    pub read_size: usize,
    pub read_timeout_ms: u32,
    pub stream_size: u32,
}

impl Default for BackendConfig {
    fn default() -> Self {
        Self {
            ft_library_path: None,
            serial_port: None,
            baud_rate: 1_000_000,
            pipe_id: DEFAULT_PIPE_ID,
            read_size: DEFAULT_READ_SIZE,
            read_timeout_ms: DEFAULT_READ_TIMEOUT_MS,
            stream_size: DEFAULT_STREAM_SIZE,
        }
    }
}

impl BackendConfig {
    pub fn from_env() -> Result<Self> {
        let mut config = Self::default();
        let mut args = std::env::args().skip(1);
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--serial-port" => {
                    config.serial_port =
                        Some(args.next().context("missing value for --serial-port")?)
                }
                "--ftd3xx" => {
                    config.ft_library_path = Some(PathBuf::from(
                        args.next().context("missing value for --ftd3xx")?,
                    ))
                }
                "--baud" => {
                    config.baud_rate = args
                        .next()
                        .context("missing value for --baud")?
                        .parse()
                        .context("invalid --baud value")?
                }
                other => return Err(anyhow!("unknown argument: {other}")),
            }
        }
        Ok(config)
    }
}

#[derive(Clone, Debug)]
pub struct BackendSnapshot {
    pub connected: bool,
    pub frame: Vec<u8>,
    pub total_words: u64,
    pub lcd_writes: u64,
    pub last_status: Option<StreamStatus>,
    pub last_uart_line: Option<String>,
    pub recent_uart_lines: Vec<String>,
    pub last_error: Option<String>,
    pub stream_enabled: bool,
}

impl Default for BackendSnapshot {
    fn default() -> Self {
        Self {
            connected: false,
            frame: vec![0; DISPLAY_WIDTH * DISPLAY_HEIGHT],
            total_words: 0,
            lcd_writes: 0,
            last_status: None,
            last_uart_line: None,
            recent_uart_lines: Vec::new(),
            last_error: None,
            stream_enabled: false,
        }
    }
}

#[derive(Clone, Debug)]
pub enum BackendCommand {
    EnableStream,
    DisableStream,
    PollStatus,
    Stop,
}

pub struct BackendHandle {
    pub updates: Receiver<BackendSnapshot>,
    pub commands: Sender<BackendCommand>,
}

pub fn spawn_backend(config: BackendConfig) -> BackendHandle {
    let (updates_tx, updates_rx) = unbounded();
    let (commands_tx, commands_rx) = unbounded();
    thread::spawn(move || worker_main(config, commands_rx, updates_tx));
    BackendHandle {
        updates: updates_rx,
        commands: commands_tx,
    }
}

fn worker_main(
    config: BackendConfig,
    commands: Receiver<BackendCommand>,
    updates: Sender<BackendSnapshot>,
) {
    loop {
        let result = run_session(&config, &commands, &updates);
        if let Err(err) = result {
            let mut snapshot = BackendSnapshot::default();
            snapshot.last_error = Some(err.to_string());
            let _ = updates.send(snapshot);
        }

        match commands.recv() {
            Ok(BackendCommand::Stop) | Err(_) => break,
            Ok(_) => continue,
        }
    }
}

fn run_session(
    config: &BackendConfig,
    commands: &Receiver<BackendCommand>,
    updates: &Sender<BackendSnapshot>,
) -> Result<()> {
    let serial_port = config.serial_port.clone().unwrap_or_else(|| {
        detect_second_usb_serial_port().unwrap_or_else(|_| "/dev/cu.usbserial-UNKNOWN".to_string())
    });
    let mut uart = open_serial(&serial_port, config.baud_rate)?;
    let mut ft = Device::open_default(
        config.ft_library_path.as_deref(),
        config.pipe_id,
        config.stream_size,
    )?;
    let mut lcd = LcdModel::default();
    let mut pending = Vec::new();
    let mut uart_buf = Vec::new();
    let mut recent_lines: VecDeque<String> = VecDeque::with_capacity(20);
    let mut snapshot = BackendSnapshot {
        connected: true,
        last_uart_line: Some(format!("connected to {serial_port}")),
        ..Default::default()
    };

    send_uart_command(&mut *uart, "F1")?;
    snapshot.stream_enabled = true;
    let _ = updates.send(snapshot.clone());
    send_uart_command(&mut *uart, "F?")?;

    let mut last_publish = Instant::now();
    let mut last_status_poll = Instant::now();

    loop {
        while let Ok(command) = commands.try_recv() {
            match command {
                BackendCommand::EnableStream => {
                    send_uart_command(&mut *uart, "F1")?;
                    snapshot.stream_enabled = true;
                }
                BackendCommand::DisableStream => {
                    send_uart_command(&mut *uart, "F0")?;
                    snapshot.stream_enabled = false;
                }
                BackendCommand::PollStatus => send_uart_command(&mut *uart, "F?")?,
                BackendCommand::Stop => return Ok(()),
            }
        }

        if last_status_poll.elapsed() >= Duration::from_secs(1) {
            let _ = send_uart_command(&mut *uart, "F?");
            last_status_poll = Instant::now();
        }

        let chunk = ft.read_pipe(config.pipe_id, config.read_size, config.read_timeout_ms)?;
        if !chunk.is_empty() {
            for raw in decode_packed_words(&chunk, &mut pending) {
                snapshot.total_words += 1;
                let word = SampledWord::from_raw(raw);
                if word.rw() {
                    continue;
                }
                if !(LCD_WRITE_ADDR_MIN..=LCD_WRITE_ADDR_MAX).contains(&word.addr) {
                    continue;
                }
                if lcd.apply_raw(word.addr, word.data).is_ok() {
                    snapshot.lcd_writes += 1;
                }
            }
        }

        drain_uart(&mut *uart, &mut uart_buf, &mut snapshot, &mut recent_lines)?;

        if last_publish.elapsed() >= Duration::from_millis(33) {
            snapshot.frame = lcd.render_monochrome();
            snapshot.recent_uart_lines = recent_lines.iter().cloned().collect();
            let _ = updates.send(snapshot.clone());
            last_publish = Instant::now();
        }
    }
}

fn detect_second_usb_serial_port() -> Result<String> {
    let mut ports: Vec<String> = fs::read_dir("/dev")?
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

fn open_serial(path: &str, baud_rate: u32) -> Result<Box<dyn SerialPort>> {
    serialport::new(path, baud_rate)
        .timeout(Duration::from_millis(10))
        .open()
        .with_context(|| format!("failed to open serial port {path}"))
}

fn send_uart_command(port: &mut dyn SerialPort, command: &str) -> Result<()> {
    port.write_all(command.as_bytes())?;
    port.write_all(b"\r")?;
    Ok(())
}

fn drain_uart(
    port: &mut dyn SerialPort,
    buffer: &mut Vec<u8>,
    snapshot: &mut BackendSnapshot,
    recent_lines: &mut VecDeque<String>,
) -> Result<()> {
    let mut temp = [0u8; 4096];
    loop {
        match port.read(&mut temp) {
            Ok(0) => break,
            Ok(read) => {
                buffer.extend_from_slice(&temp[..read]);
                while let Some(end) = buffer.iter().position(|byte| *byte == b'\n') {
                    let line = String::from_utf8_lossy(&buffer[..=end]).trim().to_string();
                    buffer.drain(..=end);
                    if line.is_empty() {
                        continue;
                    }
                    snapshot.last_uart_line = Some(line.clone());
                    if let Some(status) = parse_stream_status_line(&line) {
                        snapshot.last_status = Some(status);
                    }
                    if recent_lines.len() == 20 {
                        recent_lines.pop_front();
                    }
                    recent_lines.push_back(line);
                }
            }
            Err(err) if err.kind() == std::io::ErrorKind::TimedOut => break,
            Err(err) => return Err(err).context("UART read failed"),
        }
    }
    Ok(())
}
