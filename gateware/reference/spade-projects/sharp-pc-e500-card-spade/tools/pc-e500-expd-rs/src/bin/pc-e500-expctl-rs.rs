use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::PathBuf;

use anyhow::Result;
use serde_json::{json, Value};

use pc_e500_expd_rs::protocol::default_socket_path;

fn main() -> Result<()> {
    let mut socket = default_socket_path();
    let mut pretty = false;
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--socket" => {
                socket = PathBuf::from(args.get(index + 1).expect("missing --socket value"));
                args.drain(index..=index + 1);
            }
            "--pretty" => {
                pretty = true;
                args.remove(index);
            }
            _ => index += 1,
        }
    }

    let command = args.first().map(String::as_str).unwrap_or("status");
    let request = match command {
        "status" => json!({"action":"status"}),
        "arm-safe" => json!({"action":"arm_safe"}),
        "debug-echo-short" => {
            let timeout = parse_flag_value(&args, "--timeout")
                .unwrap_or_else(|| "10".into())
                .parse::<f64>()?;
            json!({"action":"debug_echo_short","timeout_s":timeout})
        }
        "wait-ready" => {
            let timeout = parse_flag_value(&args, "--timeout")
                .unwrap_or_else(|| "30".into())
                .parse::<f64>()?;
            json!({"action":"wait_ready","timeout_s":timeout})
        }
        "run" => {
            let script = args
                .get(1)
                .ok_or_else(|| anyhow::anyhow!("missing script path"))?;
            let mut script_args = args.iter().skip(2).cloned().collect::<Vec<_>>();
            if script_args.first().map(String::as_str) == Some("--") {
                script_args.remove(0);
            }
            json!({"action":"run","script":PathBuf::from(script).canonicalize()?.display().to_string(),"script_args":script_args})
        }
        "shutdown" => json!({"action":"shutdown"}),
        other => anyhow::bail!("unknown command: {other}"),
    };

    let response = send_request(&socket, &request)?;
    if pretty {
        println!("{}", serde_json::to_string_pretty(&response)?);
    } else {
        println!("{}", serde_json::to_string(&response)?);
    }
    let status = response["status"].as_str().unwrap_or_default();
    if status == "error" || status == "timeout" {
        std::process::exit(1);
    }
    Ok(())
}

fn send_request(socket: &PathBuf, request: &Value) -> Result<Value> {
    let mut stream = UnixStream::connect(socket)?;
    stream.write_all(serde_json::to_string(request)?.as_bytes())?;
    stream.write_all(b"\n")?;
    let mut response = Vec::new();
    let mut chunk = [0u8; 4096];
    loop {
        let read = stream.read(&mut chunk)?;
        if read == 0 {
            break;
        }
        response.extend_from_slice(&chunk[..read]);
        if chunk[..read].contains(&b'\n') {
            break;
        }
    }
    Ok(serde_json::from_slice(&response)?)
}

fn parse_flag_value(args: &[String], flag: &str) -> Option<String> {
    args.windows(2)
        .find(|window| window[0] == flag)
        .map(|window| window[1].clone())
}
