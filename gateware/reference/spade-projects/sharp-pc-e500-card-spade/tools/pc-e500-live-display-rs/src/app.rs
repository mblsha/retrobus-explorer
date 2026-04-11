use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use eframe::egui::{
    self, Align, Color32, ColorImage, CornerRadius, Frame, Grid, RichText, ScrollArea, Sense,
    Stroke, TextureHandle, TextureOptions,
};
use serde_json::json;

use crate::backend::{
    spawn_backend, BackendCommand, BackendConfig, BackendHandle, BackendSnapshot,
};
use crate::lcd::{DISPLAY_HEIGHT, DISPLAY_WIDTH};

const DEFAULT_UI_SOCKET: &str = "/tmp/pc-e500-live-display.sock";

#[derive(Clone, Debug)]
struct UiExportState {
    connected: bool,
    stream_enabled: bool,
    decoded_text_lines: Vec<String>,
    total_words: u64,
    lcd_writes: u64,
    render_generation: u64,
    last_error: Option<String>,
    last_status_raw: Option<String>,
}

impl From<&BackendSnapshot> for UiExportState {
    fn from(snapshot: &BackendSnapshot) -> Self {
        Self {
            connected: snapshot.connected,
            stream_enabled: snapshot.stream_enabled,
            decoded_text_lines: snapshot.decoded_text_lines.clone(),
            total_words: snapshot.total_words,
            lcd_writes: snapshot.lcd_writes,
            render_generation: snapshot.render_generation,
            last_error: snapshot.last_error.clone(),
            last_status_raw: snapshot
                .last_status
                .as_ref()
                .map(|status| status.raw.clone()),
        }
    }
}

pub struct LiveDisplayApp {
    backend_config: BackendConfig,
    backend: BackendHandle,
    snapshot: BackendSnapshot,
    texture: Option<TextureHandle>,
    export_state: Arc<Mutex<UiExportState>>,
}

impl LiveDisplayApp {
    pub fn new(config: BackendConfig) -> Self {
        let backend = spawn_backend(config.clone());
        let export_state = Arc::new(Mutex::new(UiExportState::from(&BackendSnapshot::default())));
        spawn_ui_socket_server(PathBuf::from(DEFAULT_UI_SOCKET), export_state.clone());
        Self {
            backend_config: config,
            backend,
            snapshot: BackendSnapshot::default(),
            texture: None,
            export_state,
        }
    }

    fn restart_backend(&mut self) {
        let _ = self.backend.commands.send(BackendCommand::Stop);
        self.backend = spawn_backend(self.backend_config.clone());
    }

    fn pump_updates(&mut self, ctx: &egui::Context) {
        while let Ok(snapshot) = self.backend.updates.try_recv() {
            self.snapshot = snapshot;
            if let Ok(mut export_state) = self.export_state.lock() {
                *export_state = UiExportState::from(&self.snapshot);
            }
            self.upload_texture(ctx);
        }
    }

    fn upload_texture(&mut self, ctx: &egui::Context) {
        let pixels: Vec<Color32> = self
            .snapshot
            .frame
            .iter()
            .map(|value| {
                if *value == 0 {
                    Color32::from_gray(235)
                } else {
                    Color32::from_gray(15)
                }
            })
            .collect();
        let image = ColorImage {
            size: [DISPLAY_WIDTH, DISPLAY_HEIGHT],
            pixels,
        };
        match &mut self.texture {
            Some(texture) => texture.set(image, TextureOptions::NEAREST),
            None => {
                self.texture =
                    Some(ctx.load_texture("pc-e500-lcd", image, TextureOptions::NEAREST));
            }
        }
    }

    fn send(&self, command: BackendCommand) {
        let _ = self.backend.commands.send(command);
    }
}

fn spawn_ui_socket_server(socket_path: PathBuf, state: Arc<Mutex<UiExportState>>) {
    thread::spawn(move || {
        if socket_path.exists() {
            let _ = fs::remove_file(&socket_path);
        }
        let listener = match UnixListener::bind(&socket_path) {
            Ok(listener) => listener,
            Err(_) => return,
        };
        while let Ok((mut stream, _)) = listener.accept() {
            let mut request = String::new();
            let _ = BufReader::new(&stream).read_line(&mut request);
            let action = serde_json::from_str::<serde_json::Value>(&request)
                .ok()
                .and_then(|value| {
                    value
                        .get("action")
                        .and_then(|v| v.as_str())
                        .map(str::to_string)
                })
                .unwrap_or_else(|| "status".to_string());
            let payload = build_ui_socket_response(&action, &state);
            let _ = stream.write_all(payload.to_string().as_bytes());
            let _ = stream.write_all(b"\n");
            let _ = stream.flush();
        }
        let _ = fs::remove_file(&socket_path);
    });
}

fn build_ui_socket_response(action: &str, state: &Arc<Mutex<UiExportState>>) -> serde_json::Value {
    let snapshot = state
        .lock()
        .map(|guard| guard.clone())
        .unwrap_or(UiExportState {
            connected: false,
            stream_enabled: false,
            decoded_text_lines: Vec::new(),
            total_words: 0,
            lcd_writes: 0,
            render_generation: 0,
            last_error: Some("failed to lock UI state".to_string()),
            last_status_raw: None,
        });
    match action {
        "get_text" => json!({
            "status": "ok",
            "connected": snapshot.connected,
            "stream_enabled": snapshot.stream_enabled,
            "lines": snapshot.decoded_text_lines,
            "total_words": snapshot.total_words,
            "lcd_writes": snapshot.lcd_writes,
            "render_generation": snapshot.render_generation,
            "last_error": snapshot.last_error,
            "last_status": snapshot.last_status_raw,
        }),
        _ => json!({
            "status": "ok",
            "connected": snapshot.connected,
            "stream_enabled": snapshot.stream_enabled,
            "line_count": snapshot.decoded_text_lines.len(),
            "total_words": snapshot.total_words,
            "lcd_writes": snapshot.lcd_writes,
            "render_generation": snapshot.render_generation,
            "last_error": snapshot.last_error,
            "last_status": snapshot.last_status_raw,
        }),
    }
}

impl eframe::App for LiveDisplayApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.pump_updates(ctx);

        egui::TopBottomPanel::top("toolbar").show(ctx, |ui| {
            ui.horizontal(|ui| {
                ui.heading("PC-E500 Live Display");
                ui.add_space(12.0);
                ui.label(RichText::new("source: FT600 + USB-UART").monospace());
                ui.with_layout(egui::Layout::right_to_left(Align::Center), |ui| {
                    if ui.button("Reconnect").clicked() {
                        self.restart_backend();
                    }
                    if ui.button("Poll F?").clicked() {
                        self.send(BackendCommand::PollStatus);
                    }
                    if ui.button("Disable F0").clicked() {
                        self.send(BackendCommand::DisableStream);
                    }
                    if ui.button("Enable F1").clicked() {
                        self.send(BackendCommand::EnableStream);
                    }
                });
            });
            ui.horizontal(|ui| {
                ui.label("status:");
                let status_text = if self.snapshot.connected {
                    "connected"
                } else {
                    "disconnected"
                };
                ui.label(RichText::new(status_text).strong());
                if let Some(status) = &self.snapshot.last_status {
                    if status.desynced() {
                        ui.colored_label(Color32::from_rgb(255, 180, 80), "desynced");
                    } else {
                        ui.colored_label(Color32::from_rgb(140, 220, 140), "in sync");
                    }
                }
            });
        });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.vertical(|ui| {
                ui.columns(2, |columns| {
                    draw_lcd_panel(&mut columns[0], self.texture.as_ref());
                    draw_transport_panel(&mut columns[1], &self.snapshot);
                });

                ui.add_space(10.0);
                draw_uart_panel(ui, &self.snapshot);
            });
        });

        ctx.request_repaint_after(Duration::from_millis(16));
    }
}

fn draw_lcd_panel(ui: &mut egui::Ui, texture: Option<&TextureHandle>) {
    framed_panel(ui, "LCD View", |ui| {
        ui.label("Local decoded 240x32 framebuffer");
        ui.add_space(8.0);

        let scale = 2.0;
        let size = egui::vec2(DISPLAY_WIDTH as f32 * scale, DISPLAY_HEIGHT as f32 * scale);
        let (rect, _) = ui.allocate_exact_size(size, Sense::hover());
        ui.painter()
            .rect_filled(rect, CornerRadius::same(8), Color32::from_gray(12));
        ui.painter().rect_stroke(
            rect,
            CornerRadius::same(8),
            Stroke::new(1.0, Color32::from_gray(80)),
            egui::StrokeKind::Outside,
        );

        if let Some(texture) = texture {
            let inner = rect.shrink2(egui::vec2(10.0, 10.0));
            ui.put(inner, egui::Image::new((texture.id(), inner.size())));
        }

        ui.add_space(8.0);
        ui.label(
            "Requires calculator-side FT stream source selection for UART-mirrored sampled words.",
        );
    });
}

fn draw_transport_panel(ui: &mut egui::Ui, snapshot: &BackendSnapshot) {
    framed_panel(ui, "Transport", |ui| {
        Grid::new("transport_grid")
            .num_columns(2)
            .spacing([12.0, 6.0])
            .show(ui, |ui| {
                tooltip_label(
                    ui,
                    "words",
                    "Total sampled-bus words consumed from FT600 since this UI session started.",
                );
                ui.monospace(snapshot.total_words.to_string());
                ui.end_row();

                tooltip_label(
                    ui,
                    "lcd writes",
                    "Subset of sampled-bus words that decoded as LCD controller write operations and were replayed into the local LCD model.",
                );
                ui.monospace(snapshot.lcd_writes.to_string());
                ui.end_row();

                tooltip_label(
                    ui,
                    "stream",
                    "Host-side desired stream state. This means the UI is trying to keep FT streaming enabled; actual FPGA state is shown below in UART / WIN / CAP.",
                );
                ui.monospace(if snapshot.stream_enabled {
                    "enabled"
                } else {
                    "disabled"
                });
                ui.end_row();
            });

        if let Some(status) = &snapshot.last_status {
            ui.add_space(10.0);
            ui.monospace(&status.raw);
            ui.add_space(4.0);

            Grid::new("status_grid")
                .num_columns(2)
                .spacing([12.0, 4.0])
                .show(ui, |ui| {
                    tooltip_label(
                        ui,
                        "CFG",
                        "FT_STREAM_CFG source-enable mask. bit0 = measurement-window source, bit1 = UART-latched always-stream source. 03 means both sources are enabled.",
                    );
                    ui.monospace(fmt_hex_opt(status.cfg));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "MODE",
                        "FT_STREAM_MODE behavior mask. bit0 controls whether the measurement FT source follows live CFG changes or holds the start-of-window policy for a whole measurement window. 00 means live-following.",
                    );
                    ui.monospace(fmt_hex_opt(status.mode));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "UART",
                        "UART FT source latch from F1/F0. 1 means the always-stream UART source is armed; 0 means it is inactive even if CFG.bit1 is enabled.",
                    );
                    ui.monospace(fmt_bool_opt(status.uart));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "WIN",
                        "Measurement-window FT source currently active. 1 means an experiment measurement window is open; 0 means no measurement window is active.",
                    );
                    ui.monospace(fmt_bool_opt(status.win));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "CAP",
                        "Effective FT capture-active flag after OR-ing all enabled FT sources. If CAP=1 outside a measurement window, the UART-latched always-stream source is feeding FT600.",
                    );
                    ui.monospace(fmt_bool_opt(status.cap));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "SOVF",
                        "Session-local FT overflow counter for the current or most recent UART streaming session. F1 starts a new session baseline; nonzero means the live display may be desynced.",
                    );
                    ui.monospace(fmt_u32_opt(status.sovf));
                    ui.end_row();

                    tooltip_label(
                        ui,
                        "OVF",
                        "Cumulative FT overflow counter since FPGA reset. This is historical and can stay nonzero even when the current session is healthy.",
                    );
                    ui.monospace(fmt_u32_opt(status.ovf));
                    ui.end_row();
                });
        } else {
            ui.add_space(10.0);
            ui.monospace("No F? status yet");
        }

        if let Some(error) = &snapshot.last_error {
            ui.add_space(10.0);
            ui.colored_label(Color32::LIGHT_RED, error);
        }
    });
}

fn draw_uart_panel(ui: &mut egui::Ui, snapshot: &BackendSnapshot) {
    framed_panel(ui, "UART Log", |ui| {
        ScrollArea::vertical()
            .auto_shrink([false, false])
            .stick_to_bottom(true)
            .max_height(220.0)
            .show(ui, |ui| {
                if snapshot.recent_uart_lines.is_empty() {
                    ui.monospace("<no UART lines yet>");
                } else {
                    for line in &snapshot.recent_uart_lines {
                        ui.monospace(line);
                    }
                }
            });
    });
}

fn framed_panel(ui: &mut egui::Ui, title: &str, add_contents: impl FnOnce(&mut egui::Ui)) {
    Frame::group(ui.style())
        .fill(Color32::from_gray(22))
        .stroke(Stroke::new(1.0, Color32::from_gray(70)))
        .corner_radius(CornerRadius::same(10))
        .inner_margin(12.0)
        .show(ui, |ui| {
            ui.heading(title);
            ui.add_space(8.0);
            add_contents(ui);
        });
}

fn tooltip_label(ui: &mut egui::Ui, text: &str, tooltip: &str) {
    ui.monospace(text).on_hover_text(tooltip);
}

fn fmt_hex_opt(value: Option<u8>) -> String {
    value
        .map(|value| format!("{value:02X}"))
        .unwrap_or_else(|| "--".to_string())
}

fn fmt_bool_opt(value: Option<bool>) -> &'static str {
    match value {
        Some(true) => "1",
        Some(false) => "0",
        None => "-",
    }
}

fn fmt_u32_opt(value: Option<u32>) -> String {
    value
        .map(|value| format!("{value:08X}"))
        .unwrap_or_else(|| "--------".to_string())
}
