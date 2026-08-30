use std::fs;
use std::path::PathBuf;

use pc_e500_expd_rs::SUPERVISOR_RPC_ACTIONS;
use serde_json::Value;

fn contract_path() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("project root")
        .join("tests")
        .join("supervisor_rpc_contract.json")
}

#[test]
fn rust_supervisor_actions_match_contract() {
    let payload = fs::read_to_string(contract_path()).expect("read contract");
    let value: Value = serde_json::from_str(&payload).expect("parse contract");
    let actions = value["actions"]
        .as_array()
        .expect("actions array")
        .iter()
        .map(|item| item.as_str().expect("action string"))
        .collect::<Vec<_>>();
    assert_eq!(actions, SUPERVISOR_RPC_ACTIONS);
}
