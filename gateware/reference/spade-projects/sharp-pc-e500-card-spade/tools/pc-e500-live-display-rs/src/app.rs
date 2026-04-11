use std::time::Duration;

use eframe::egui::{self, Color32, ColorImage, RichText, TextureHandle, TextureOptions};

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
                    Color32::from_gray(15)
                } else {
                    Color32::from_gray(235)
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
            ui.horizontal_wrapped(|ui| {
                if ui.button("Enable F1").clicked() {
                    self.send(BackendCommand::EnableStream);
                }
                if ui.button("Disable F0").clicked() {
                    self.send(BackendCommand::DisableStream);
                }
                if ui.button("Poll F?").clicked() {
                    self.send(BackendCommand::PollStatus);
                }
                if ui.button("Reconnect").clicked() {
                    self.restart_backend();
                }

                ui.separator();
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

        egui::SidePanel::right("status")
            .default_width(320.0)
            .show(ctx, |ui| {
                ui.heading("Status");
                ui.label(format!("words: {}", self.snapshot.total_words));
                ui.label(format!("lcd writes: {}", self.snapshot.lcd_writes));
                ui.label(format!("stream enabled: {}", self.snapshot.stream_enabled));

                if let Some(status) = &self.snapshot.last_status {
                    ui.separator();
                    ui.monospace(&status.raw);
                    ui.monospace(format!("CFG  = {}", fmt_hex_opt(status.cfg)));
                    ui.monospace(format!("MODE = {}", fmt_hex_opt(status.mode)));
                    ui.monospace(format!("UART = {}", fmt_bool_opt(status.uart)));
                    ui.monospace(format!("WIN  = {}", fmt_bool_opt(status.win)));
                    ui.monospace(format!("CAP  = {}", fmt_bool_opt(status.cap)));
                    ui.monospace(format!("SOVF = {}", fmt_u32_opt(status.sovf)));
                    ui.monospace(format!("OVF  = {}", fmt_u32_opt(status.ovf)));
                }

                if let Some(error) = &self.snapshot.last_error {
                    ui.separator();
                    ui.colored_label(Color32::LIGHT_RED, error);
                }

                ui.separator();
                ui.heading("UART");
                for line in self.snapshot.recent_uart_lines.iter().rev().take(12) {
                    ui.monospace(line);
                }
            });

        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("PC-E500 LCD");
            ui.label("Requires calculator-side FT stream source selection for UART-mirrored sampled words.");
            ui.add_space(8.0);

            if let Some(texture) = &self.texture {
                let scale = 4.0;
                let size = egui::vec2(DISPLAY_WIDTH as f32 * scale, DISPLAY_HEIGHT as f32 * scale);
                ui.image((texture.id(), size));
            } else {
                ui.allocate_space(egui::vec2(DISPLAY_WIDTH as f32 * 4.0, DISPLAY_HEIGHT as f32 * 4.0));
            }
        });

        ctx.request_repaint_after(Duration::from_millis(16));
    }
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
