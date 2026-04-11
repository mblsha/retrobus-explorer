use std::fs;
use std::io::{Read, Write};
use std::os::unix::net::UnixListener;
use std::path::PathBuf;
use std::process::Command;
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::Value;

fn temp_socket_path(name: &str) -> PathBuf {
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    std::env::temp_dir().join(format!("pc_e500_expd_rs_{name}_{nonce}.sock"))
}

fn read_json_line(stream: &mut std::os::unix::net::UnixStream) -> Value {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let read = stream.read(&mut chunk).expect("read request");
        if read == 0 {
            break;
        }
        buf.extend_from_slice(&chunk[..read]);
        if chunk[..read].contains(&b'\n') {
            break;
        }
    }
    serde_json::from_slice(&buf).expect("request json")
}

#[test]
fn expctl_status_sends_status_action() {
    let socket = temp_socket_path("status");
    let server_socket = socket.clone();
    let handle = thread::spawn(move || {
        let listener = UnixListener::bind(&server_socket).expect("bind socket");
        let (mut stream, _) = listener.accept().expect("accept");
        let request = read_json_line(&mut stream);
        serde_json::to_writer(
            &mut stream,
            &serde_json::json!({"status":"ok","echo":"status"}),
        )
        .expect("write response");
        stream.write_all(b"\n").expect("newline");
        request
    });

    thread::sleep(Duration::from_millis(20));
    let output = Command::new(env!("CARGO_BIN_EXE_pc-e500-expctl-rs"))
        .arg("--socket")
        .arg(&socket)
        .arg("status")
        .output()
        .expect("run expctl");

    let _ = fs::remove_file(&socket);
    assert!(output.status.success());
    let request = handle.join().expect("server thread");
    assert_eq!(request["action"], "status");
}

#[test]
fn expctl_run_sends_script_and_script_args() {
    let socket = temp_socket_path("run");
    let server_socket = socket.clone();
    let script = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("README.md");
    let expected_script = script.canonicalize().expect("canonical script");
    let handle = thread::spawn(move || {
        let listener = UnixListener::bind(&server_socket).expect("bind socket");
        let (mut stream, _) = listener.accept().expect("accept");
        let request = read_json_line(&mut stream);
        serde_json::to_writer(&mut stream, &serde_json::json!({"status":"ok"}))
            .expect("write response");
        stream.write_all(b"\n").expect("newline");
        request
    });

    thread::sleep(Duration::from_millis(20));
    let output = Command::new(env!("CARGO_BIN_EXE_pc-e500-expctl-rs"))
        .arg("--socket")
        .arg(&socket)
        .arg("run")
        .arg(&script)
        .arg("--")
        .arg("alpha")
        .arg("beta")
        .output()
        .expect("run expctl");

    let _ = fs::remove_file(&socket);
    assert!(output.status.success());
    let request = handle.join().expect("server thread");
    assert_eq!(request["action"], "run");
    assert_eq!(request["script"], expected_script.display().to_string());
    assert_eq!(request["script_args"], serde_json::json!(["alpha", "beta"]));
}

#[test]
fn expctl_exits_non_zero_on_timeout_status() {
    let socket = temp_socket_path("timeout");
    let server_socket = socket.clone();
    let handle = thread::spawn(move || {
        let listener = UnixListener::bind(&server_socket).expect("bind socket");
        let (mut stream, _) = listener.accept().expect("accept");
        let _request = read_json_line(&mut stream);
        serde_json::to_writer(
            &mut stream,
            &serde_json::json!({"status":"timeout","error":"simulated timeout"}),
        )
        .expect("write response");
        stream.write_all(b"\n").expect("newline");
    });

    thread::sleep(Duration::from_millis(20));
    let output = Command::new(env!("CARGO_BIN_EXE_pc-e500-expctl-rs"))
        .arg("--socket")
        .arg(&socket)
        .arg("status")
        .output()
        .expect("run expctl");

    let _ = fs::remove_file(&socket);
    handle.join().expect("server thread");
    assert!(!output.status.success());
}
