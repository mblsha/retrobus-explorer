mod app;
mod backend;
mod d3xx;
mod lcd;
mod protocol;

use anyhow::Result;
use app::LiveDisplayApp;
use backend::BackendConfig;

fn main() -> Result<()> {
    let config = BackendConfig::from_env()?;
    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1100.0, 620.0])
            .with_min_inner_size([860.0, 480.0])
            .with_title("PC-E500 Live Display"),
        ..Default::default()
    };

    eframe::run_native(
        "PC-E500 Live Display",
        native_options,
        Box::new(move |_cc| Ok(Box::new(LiveDisplayApp::new(config.clone())))),
    )
    .map_err(|err| anyhow::anyhow!(err.to_string()))
}
