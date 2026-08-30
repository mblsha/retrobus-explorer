use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::Value;

fn hw_enabled(var: &str) -> bool {
    matches!(std::env::var(var).as_deref(), Ok("1"))
}

fn temp_socket_path(name: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("pc_e500_expd_rs_{name}_{nonce}.sock"))
}

struct DaemonChild {
    child: Child,
    socket: PathBuf,
}

impl Drop for DaemonChild {
    fn drop(&mut self) {
        let _ = Command::new(env!("CARGO_BIN_EXE_pc-e500-expctl-rs"))
            .arg("--socket")
            .arg(&self.socket)
            .arg("shutdown")
            .output();
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = fs::remove_file(&self.socket);
    }
}

fn wait_for_socket(path: &Path, timeout: Duration) {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if path.exists() {
            return;
        }
        thread::sleep(Duration::from_millis(50));
    }
    panic!("socket {} was not created in time", path.display());
}

fn run_client(socket: &Path, args: &[&str]) -> Value {
    let output = Command::new(env!("CARGO_BIN_EXE_pc-e500-expctl-rs"))
        .arg("--socket")
        .arg(socket)
        .args(args)
        .output()
        .expect("run client");
    assert!(
        output.status.success(),
        "client failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    serde_json::from_slice(&output.stdout).expect("client json")
}

fn spawn_daemon(name: &str) -> DaemonChild {
    let socket = temp_socket_path(name);
    let mut command = Command::new(env!("CARGO_BIN_EXE_pc-e500-expd-rs"));
    command.arg("--socket").arg(&socket);
    if let Ok(port) = std::env::var("PC_E500_SERIAL_PORT") {
        command.arg("--port").arg(port);
    }
    let child = command.spawn().expect("spawn daemon");
    wait_for_socket(&socket, Duration::from_secs(5));
    DaemonChild { child, socket }
}

#[test]
fn daemon_status_smoke_opt_in() {
    if !hw_enabled("PC_E500_HW") {
        eprintln!("skipping hardware smoke; set PC_E500_HW=1 to enable");
        return;
    }

    let daemon = spawn_daemon("status");
    let status = run_client(&daemon.socket, &["status"]);
    assert_eq!(status["status"], "ok");
    assert!(status["uart"].is_object());
}

#[test]
fn daemon_ready_and_run_smoke_opt_in() {
    if !hw_enabled("PC_E500_HW_FULL") {
        eprintln!(
            "skipping full hardware smoke; set PC_E500_HW_FULL=1 when XR,READY,01,SAFEFT is already active"
        );
        return;
    }

    let daemon = spawn_daemon("full");
    let ready = run_client(&daemon.socket, &["wait-ready", "--timeout", "5"]);
    assert_eq!(ready["status"], "ok");

    let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("project root")
        .to_path_buf();
    let experiment = project_root
        .join("experiments")
        .join("return_immediately.py");
    let result = run_client(
        &daemon.socket,
        &["run", experiment.to_str().expect("utf8 path")],
    );
    assert_eq!(result["status"], "ok");
    assert!(result["end_line"]
        .as_str()
        .unwrap_or_default()
        .contains("OK"));
}
