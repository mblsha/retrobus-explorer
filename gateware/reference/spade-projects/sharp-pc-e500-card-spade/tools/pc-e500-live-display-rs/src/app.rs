use std::time::Duration;

use eframe::egui::{
    self, Align, Color32, ColorImage, CornerRadius, Frame, Grid, RichText, ScrollArea, Sense,
    Stroke, TextureHandle, TextureOptions,
};

use crate::backend::{
    spawn_backend, BackendCommand, BackendConfig, BackendHandle, BackendSnapshot,
};
use crate::lcd::{DISPLAY_HEIGHT, DISPLAY_WIDTH};

pub struct LiveDisplayApp {
    backend_config: BackendConfig,
    backend: BackendHandle,
    snapshot: BackendSnapshot,
    texture: Option<TextureHandle>,
}

impl LiveDisplayApp {
    pub fn new(config: BackendConfig) -> Self {
        let backend = spawn_backend(config.clone());
        Self {
            backend_config: config,
            backend,
            snapshot: BackendSnapshot::default(),
            texture: None,
        }
    }

    fn restart_backend(&mut self) {
        let _ = self.backend.commands.send(BackendCommand::Stop);
        self.backend = spawn_backend(self.backend_config.clone());
    }

    fn pump_updates(&mut self, ctx: &egui::Context) {
        while let Ok(snapshot) = self.backend.updates.try_recv() {
            self.snapshot = snapshot;
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

        let scale = 4.0;
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
                ui.monospace("words");
                ui.monospace(snapshot.total_words.to_string());
                ui.end_row();

                ui.monospace("lcd writes");
                ui.monospace(snapshot.lcd_writes.to_string());
                ui.end_row();

                ui.monospace("stream");
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
                    ui.monospace("CFG");
                    ui.monospace(fmt_hex_opt(status.cfg));
                    ui.end_row();

                    ui.monospace("MODE");
                    ui.monospace(fmt_hex_opt(status.mode));
                    ui.end_row();

                    ui.monospace("UART");
                    ui.monospace(fmt_bool_opt(status.uart));
                    ui.end_row();

                    ui.monospace("WIN");
                    ui.monospace(fmt_bool_opt(status.win));
                    ui.end_row();

                    ui.monospace("CAP");
                    ui.monospace(fmt_bool_opt(status.cap));
                    ui.end_row();

                    ui.monospace("SOVF");
                    ui.monospace(fmt_u32_opt(status.sovf));
                    ui.end_row();

                    ui.monospace("OVF");
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
