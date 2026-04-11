use std::collections::VecDeque;
use std::ffi::CString;
use std::fs;
use std::io::{Read, Write};
use std::os::fd::RawFd;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::thread;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use anyhow::{anyhow, Context, Result};
use crossbeam_channel::{unbounded, Receiver, Sender};
use serde_json::{json, Value};
use crate::d3xx::Device;
use crate::lcd::{LcdModel, DISPLAY_HEIGHT, DISPLAY_WIDTH};
use crate::protocol::{
    decode_packed_words, is_lcd_write_address, parse_stream_status_line, SampledWord,
    StreamStatus, DEFAULT_PIPE_ID, DEFAULT_READ_SIZE, DEFAULT_READ_TIMEOUT_MS,
    DEFAULT_STREAM_SIZE,
};
use crate::text::Pce500FontMap;

#[cfg(target_os = "macos")]
const IOSSIOSPEED: libc::c_ulong = 0x8004_5402;
const BACKEND_IDLE_SLEEP_MS: u64 = 2;

#[derive(Clone, Debug)]
pub struct BackendConfig {
    pub ft_library_path: Option<PathBuf>,
    pub serial_port: Option<String>,
    pub daemon_socket: Option<PathBuf>,
    pub baud_rate: u32,
    pub use_uart: bool,
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
            daemon_socket: None,
            baud_rate: 1_000_000,
            use_uart: true,
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
                "--daemon-socket" => {
                    config.daemon_socket = Some(PathBuf::from(
                        args.next().context("missing value for --daemon-socket")?,
                    ))
                }
                "--baud" => {
                    config.baud_rate = args
                        .next()
                        .context("missing value for --baud")?
                        .parse()
                        .context("invalid --baud value")?
                }
                "--no-uart" => config.use_uart = false,
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
    pub decoded_text_lines: Vec<String>,
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
            decoded_text_lines: Vec::new(),
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
    let serial_port = if config.use_uart {
        Some(config.serial_port.clone().unwrap_or_else(|| {
            detect_second_usb_serial_port().unwrap_or_else(|_| "/dev/cu.usbserial-UNKNOWN".to_string())
        }))
    } else {
        None
    };
    let mut uart = if let Some(serial_port) = &serial_port {
        Some(open_serial(serial_port, config.baud_rate)?)
    } else {
        None
    };
    let ft = Device::open_default(
        config.ft_library_path.as_deref(),
        config.pipe_id,
        config.stream_size,
    )?;
    let mut ft_reader =
        spawn_ft_reader(ft, config.pipe_id, config.read_size, config.read_timeout_ms);
    let mut lcd = LcdModel::default();
    let font = Pce500FontMap::load_default().ok();
    let mut pending = Vec::new();
    let mut uart_buf = Vec::new();
    let mut recent_lines: VecDeque<String> = VecDeque::with_capacity(20);
    let mut snapshot = BackendSnapshot {
        connected: true,
        last_uart_line: serial_port
            .as_ref()
            .map(|serial_port| format!("connected to {serial_port}")),
        ..Default::default()
    };

    let session_result: Result<()> = (|| {
        if uart.is_some() || config.daemon_socket.is_some() {
            enable_stream_and_refresh(
                uart.as_mut(),
                config.daemon_socket.as_deref(),
                &mut snapshot,
                &mut recent_lines,
            )?;
            reset_local_display_state(&mut lcd, &mut pending, &mut snapshot);
            discard_ft_backlog(&ft_reader.rx, &mut pending);
            let _ = updates.send(snapshot.clone());
        } else {
            snapshot.stream_enabled = false;
            snapshot.last_uart_line = Some("FT-only mode (no control plane)".to_string());
            let _ = updates.send(snapshot.clone());
        }

        let mut last_publish = Instant::now();
        let mut last_status_poll = Instant::now();
        let mut desired_stream_enabled = uart.is_some() || config.daemon_socket.is_some();
        let mut stop_requested = false;

        loop {
            while let Ok(command) = commands.try_recv() {
                match command {
                    BackendCommand::EnableStream => {
                        enable_stream_and_refresh(
                            uart.as_mut(),
                            config.daemon_socket.as_deref(),
                            &mut snapshot,
                            &mut recent_lines,
                        )?;
                        reset_local_display_state(&mut lcd, &mut pending, &mut snapshot);
                        discard_ft_backlog(&ft_reader.rx, &mut pending);
                        desired_stream_enabled = true;
                    }
                    BackendCommand::DisableStream => {
                        if let Some(uart) = uart.as_mut() {
                            send_uart_command(uart, "F0")?;
                        } else if let Some(socket_path) = config.daemon_socket.as_deref() {
                            apply_daemon_response(
                                &daemon_request(socket_path, "stream_off")?,
                                &mut snapshot,
                                &mut recent_lines,
                            );
                        }
                        snapshot.stream_enabled = false;
                        desired_stream_enabled = false;
                    }
                    BackendCommand::PollStatus => {
                        if let Some(uart) = uart.as_mut() {
                            send_uart_command(uart, "F?")?;
                        } else if let Some(socket_path) = config.daemon_socket.as_deref() {
                            apply_daemon_response(
                                &daemon_request(socket_path, "stream_status")?,
                                &mut snapshot,
                                &mut recent_lines,
                            );
                        }
                    }
                    BackendCommand::Stop => {
                        stop_requested = true;
                        break;
                    }
                }
            }

            if stop_requested {
                break Ok(());
            }

            if let Some(error) = ft_reader.error_rx.try_iter().last() {
                break Err(error);
            }

            if last_status_poll.elapsed() >= Duration::from_secs(1) {
                if let Some(uart) = uart.as_mut() {
                    let _ = send_uart_command(uart, "F?");
                } else if let Some(socket_path) = config.daemon_socket.as_deref() {
                    if let Ok(response) = daemon_request(socket_path, "stream_status") {
                        apply_daemon_response(&response, &mut snapshot, &mut recent_lines);
                    }
                }
                last_status_poll = Instant::now();
            }

            let stream_latch_missing =
                snapshot.last_status.as_ref().and_then(|status| status.uart) == Some(false);
            let continuous_source_missing = config.daemon_socket.is_some()
                && snapshot
                    .last_status
                    .as_ref()
                    .and_then(|status| status.cfg)
                    .map(|cfg| (cfg & 0x02) == 0)
                    .unwrap_or(false);
            if desired_stream_enabled && (stream_latch_missing || continuous_source_missing) {
                enable_stream_and_refresh(
                    uart.as_mut(),
                    config.daemon_socket.as_deref(),
                    &mut snapshot,
                    &mut recent_lines,
                )?;
                reset_local_display_state(&mut lcd, &mut pending, &mut snapshot);
                discard_ft_backlog(&ft_reader.rx, &mut pending);
            }

            let mut saw_chunk = false;
            for chunk in ft_reader.rx.try_iter() {
                saw_chunk = true;
                process_ft_chunk(&chunk, &mut pending, &mut snapshot, &mut lcd);
            }

            if let Some(uart) = uart.as_mut() {
                drain_uart(uart, &mut uart_buf, &mut snapshot, &mut recent_lines)?;
            }

            if last_publish.elapsed() >= Duration::from_millis(33) {
                snapshot.frame = lcd.render_monochrome();
                snapshot.decoded_text_lines = font
                    .as_ref()
                    .map(|font| font.decode_frame(&snapshot.frame))
                    .unwrap_or_default();
                snapshot.recent_uart_lines = recent_lines.iter().cloned().collect();
                let _ = updates.send(snapshot.clone());
                last_publish = Instant::now();
            }

            if !saw_chunk {
                thread::sleep(Duration::from_millis(BACKEND_IDLE_SLEEP_MS));
            }
        }
    })();

    ft_reader.stop();
    session_result
}

struct FtReaderHandle {
    rx: Receiver<Vec<u8>>,
    error_rx: Receiver<anyhow::Error>,
    stop_tx: Sender<()>,
    join_handle: Option<JoinHandle<()>>,
}

impl FtReaderHandle {
    fn stop(&mut self) {
        let _ = self.stop_tx.send(());
        if let Some(join_handle) = self.join_handle.take() {
            let _ = join_handle.join();
        }
    }
}

fn spawn_ft_reader(
    mut ft: Device,
    pipe_id: u8,
    read_size: usize,
    read_timeout_ms: u32,
) -> FtReaderHandle {
    let (chunk_tx, chunk_rx) = unbounded();
    let (error_tx, error_rx) = unbounded();
    let (stop_tx, stop_rx) = unbounded();
    let join_handle = thread::spawn(move || loop {
        if stop_rx.try_recv().is_ok() {
            break;
        }
        match ft.read_pipe(pipe_id, read_size, read_timeout_ms) {
            Ok(chunk) => {
                if chunk.is_empty() {
                    continue;
                }
                if chunk_tx.send(chunk).is_err() {
                    break;
                }
            }
            Err(err) => {
                let _ = error_tx.send(err.context("FT reader thread failed"));
                break;
            }
        }
    });
    FtReaderHandle {
        rx: chunk_rx,
        error_rx,
        stop_tx,
        join_handle: Some(join_handle),
    }
}

fn reset_local_display_state(
    lcd: &mut LcdModel,
    pending: &mut Vec<u8>,
    snapshot: &mut BackendSnapshot,
) {
    *lcd = LcdModel::default();
    pending.clear();
    snapshot.frame = lcd.render_monochrome();
    snapshot.decoded_text_lines.clear();
    snapshot.lcd_writes = 0;
}

fn discard_ft_backlog(ft_rx: &Receiver<Vec<u8>>, pending: &mut Vec<u8>) {
    while let Ok(chunk) = ft_rx.try_recv() {
        let _ = decode_packed_words(&chunk, pending);
    }
    pending.clear();
}

fn process_ft_chunk(
    chunk: &[u8],
    pending: &mut Vec<u8>,
    snapshot: &mut BackendSnapshot,
    lcd: &mut LcdModel,
) {
    for raw in decode_packed_words(chunk, pending) {
        snapshot.total_words += 1;
        let word = SampledWord::from_raw(raw);
        if word.rw() {
            continue;
        }
        if !is_lcd_write_address(word.addr) {
            continue;
        }
        if lcd.apply_raw(word.addr, word.data).is_ok() {
            snapshot.lcd_writes += 1;
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

fn open_serial(path: &str, baud_rate: u32) -> Result<PortHandle> {
    let port = PortHandle::open(path, baud_rate)
        .with_context(|| format!("failed to open serial port {path}"))?;
    let _ = port.clear_input();
    let _ = port.clear_output();
    Ok(port)
}

fn send_uart_command(port: &mut PortHandle, command: &str) -> Result<()> {
    port.write_all(command.as_bytes())?;
    port.write_all(b"\r")?;
    port.flush()?;
    Ok(())
}

fn enable_stream_and_refresh(
    uart: Option<&mut PortHandle>,
    daemon_socket: Option<&std::path::Path>,
    snapshot: &mut BackendSnapshot,
    recent_lines: &mut VecDeque<String>,
) -> Result<()> {
    if let Some(uart) = uart {
        // F0 -> F1 gives the FPGA a clean stream re-arm and clears session-local SOVF.
        send_uart_command(uart, "F0")?;
        send_uart_command(uart, "F1")?;
        send_uart_command(uart, "F?")?;
    } else if let Some(socket_path) = daemon_socket {
        apply_daemon_response(
            &daemon_json_request(
                socket_path,
                json!({ "action": "stream_config", "cfg": 0x03, "mode": 0x00 }),
            )?,
            snapshot,
            recent_lines,
        );
        apply_daemon_response(
            &daemon_request(socket_path, "stream_off")?,
            snapshot,
            recent_lines,
        );
        apply_daemon_response(
            &daemon_request(socket_path, "stream_on")?,
            snapshot,
            recent_lines,
        );
        apply_daemon_response(
            &daemon_request(socket_path, "stream_status")?,
            snapshot,
            recent_lines,
        );
    }
    snapshot.stream_enabled = true;
    Ok(())
}

fn daemon_request(socket_path: &std::path::Path, action: &str) -> Result<Value> {
    daemon_json_request(socket_path, json!({ "action": action }))
}

fn daemon_json_request(socket_path: &std::path::Path, request: Value) -> Result<Value> {
    let mut stream = UnixStream::connect(socket_path)
        .with_context(|| format!("failed to connect to daemon socket {}", socket_path.display()))?;
    stream.write_all(request.to_string().as_bytes())?;
    stream.write_all(b"\n")?;
    stream.flush()?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    serde_json::from_str(&response).with_context(|| {
        format!(
            "invalid daemon response for {}: {response}",
            request
                .get("action")
                .and_then(|value| value.as_str())
                .unwrap_or("<unknown>")
        )
    })
}

fn apply_daemon_response(
    response: &Value,
    snapshot: &mut BackendSnapshot,
    recent_lines: &mut VecDeque<String>,
) {
    if let Some(lines) = response.get("recent_uart_lines").and_then(|value| value.as_array()) {
        for line in lines.iter().filter_map(|value| value.as_str()) {
            push_uart_line(snapshot, recent_lines, line);
        }
    }
    if let Some(reply_text) = response.get("reply_text").and_then(|value| value.as_str()) {
        for line in reply_text.lines() {
            let line = line.trim();
            if !line.is_empty() {
                push_uart_line(snapshot, recent_lines, line);
            }
        }
    }
}

fn push_uart_line(
    snapshot: &mut BackendSnapshot,
    recent_lines: &mut VecDeque<String>,
    line: &str,
) {
    snapshot.last_uart_line = Some(line.to_string());
    if let Some(status) = parse_stream_status_line(line) {
        snapshot.last_status = Some(status);
    }
    if recent_lines.len() == 20 {
        recent_lines.pop_front();
    }
    recent_lines.push_back(line.to_string());
}

fn drain_uart(
    port: &mut PortHandle,
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
                    push_uart_line(snapshot, recent_lines, &line);
                }
            }
            Err(err) if err.kind() == std::io::ErrorKind::TimedOut => break,
            Err(err) => return Err(err).context("UART read failed"),
        }
    }
    Ok(())
}

#[cfg(target_os = "macos")]
#[derive(Debug)]
struct PortHandle {
    fd: RawFd,
}

#[cfg(target_os = "macos")]
impl PortHandle {
    fn open(path: &str, baud: u32) -> Result<Self> {
        let c_path = CString::new(path)?;
        let fd = unsafe {
            libc::open(
                c_path.as_ptr(),
                libc::O_RDWR | libc::O_NOCTTY | libc::O_NONBLOCK,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }

        let mut termios = unsafe {
            let mut termios = std::mem::zeroed::<libc::termios>();
            if libc::tcgetattr(fd, &mut termios) != 0 {
                let err = std::io::Error::last_os_error();
                libc::close(fd);
                return Err(err.into());
            }
            termios
        };

        unsafe { libc::cfmakeraw(&mut termios) };
        termios.c_cflag |= libc::CREAD | libc::CLOCAL;
        termios.c_cflag &= !libc::CSIZE;
        termios.c_cflag |= libc::CS8;
        termios.c_cflag &= !libc::CSTOPB;
        termios.c_cflag &= !(libc::PARENB | libc::PARODD);
        termios.c_iflag &= !(libc::IXON | libc::IXOFF | libc::IXANY);
        termios.c_cc[libc::VMIN] = 0;
        termios.c_cc[libc::VTIME] = 0;

        unsafe {
            if libc::cfsetispeed(&mut termios, libc::B9600) != 0
                || libc::cfsetospeed(&mut termios, libc::B9600) != 0
            {
                let err = std::io::Error::last_os_error();
                libc::close(fd);
                return Err(err.into());
            }
            if libc::tcsetattr(fd, libc::TCSANOW, &termios) != 0 {
                let err = std::io::Error::last_os_error();
                libc::close(fd);
                return Err(err.into());
            }
            let speed = baud as libc::speed_t;
            if libc::ioctl(fd, IOSSIOSPEED, &speed) != 0 {
                let err = std::io::Error::last_os_error();
                libc::close(fd);
                return Err(err.into());
            }
        }

        Ok(Self { fd })
    }

    fn clear_input(&self) -> std::io::Result<()> {
        let rc = unsafe { libc::tcflush(self.fd, libc::TCIFLUSH) };
        if rc == 0 {
            Ok(())
        } else {
            Err(std::io::Error::last_os_error())
        }
    }

    fn clear_output(&self) -> std::io::Result<()> {
        let rc = unsafe { libc::tcflush(self.fd, libc::TCOFLUSH) };
        if rc == 0 {
            Ok(())
        } else {
            Err(std::io::Error::last_os_error())
        }
    }
}

#[cfg(target_os = "macos")]
impl Read for PortHandle {
    fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
        let read = unsafe { libc::read(self.fd, buffer.as_mut_ptr().cast(), buffer.len()) };
        if read < 0 {
            let err = std::io::Error::last_os_error();
            if err.kind() == std::io::ErrorKind::WouldBlock {
                return Err(std::io::Error::new(std::io::ErrorKind::TimedOut, err));
            }
            return Err(err);
        }
        Ok(read as usize)
    }
}

#[cfg(target_os = "macos")]
impl Write for PortHandle {
    fn write(&mut self, buffer: &[u8]) -> std::io::Result<usize> {
        let wrote = unsafe { libc::write(self.fd, buffer.as_ptr().cast(), buffer.len()) };
        if wrote < 0 {
            return Err(std::io::Error::last_os_error());
        }
        Ok(wrote as usize)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        let rc = unsafe { libc::tcdrain(self.fd) };
        if rc == 0 {
            Ok(())
        } else {
            Err(std::io::Error::last_os_error())
        }
    }
}

#[cfg(target_os = "macos")]
impl Drop for PortHandle {
    fn drop(&mut self) {
        unsafe {
            libc::close(self.fd);
        }
    }
}

#[cfg(not(target_os = "macos"))]
type PortHandle = serialport::TTYPort;

#[cfg(not(target_os = "macos"))]
impl PortHandle {
    fn open(path: &str, baud: u32) -> Result<Self> {
        serialport::new(path, baud)
            .timeout(Duration::from_millis(10))
            .open_native()
            .map_err(Into::into)
    }

    fn clear_input(&self) -> std::io::Result<()> {
        self.clear(serialport::ClearBuffer::Input)
    }

    fn clear_output(&self) -> std::io::Result<()> {
        self.clear(serialport::ClearBuffer::Output)
    }
}
