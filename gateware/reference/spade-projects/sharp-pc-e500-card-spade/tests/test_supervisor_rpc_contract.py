from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "tests" / "supervisor_rpc_contract.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "pc-e500-expd.py"


def load_python_supervisor_module():
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    sys.modules.setdefault("serial", types.SimpleNamespace())
    spec = importlib.util.spec_from_file_location("pc_e500_expd_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeDaemon:
    def status_payload(self):
        return {"status": "ok", "action": "status"}

    def stream_command(self, command: str):
        return {"status": "ok", "command": command}

    def set_stream_config(self, cfg: int, mode: int | None = None):
        return {"status": "ok", "cfg": cfg, "mode": mode}

    def program_safe_image(self):
        return {"status": "ok", "action": "arm_safe"}

    def debug_echo_short(self, timeout_s: float):
        return {"status": "ok", "timeout_s": timeout_s}

    def wait_ready(self, timeout_s: float):
        return {"status": "ok", "timeout_s": timeout_s}

    def run_experiment(self, script_path: Path, script_args: list[str]):
        return {
            "status": "ok",
            "script_path": str(script_path),
            "script_args": script_args,
        }


class SupervisorRpcContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_python_supervisor_module()
        cls.contract = json.loads(CONTRACT_PATH.read_text())

    def test_python_action_list_matches_contract(self):
        self.assertEqual(
            list(self.contract["actions"]),
            list(self.module.SUPPORTED_RPC_ACTIONS),
        )

    def test_python_handle_request_supports_every_contract_action(self):
        daemon = FakeDaemon()
        requests = {
            "status": {"action": "status"},
            "stream_on": {"action": "stream_on"},
            "stream_off": {"action": "stream_off"},
            "stream_status": {"action": "stream_status"},
            "stream_config": {"action": "stream_config", "cfg": 0x03, "mode": 0x00},
            "arm_safe": {"action": "arm_safe"},
            "debug_echo_short": {"action": "debug_echo_short", "timeout_s": 1.0},
            "wait_ready": {"action": "wait_ready", "timeout_s": 1.0},
            "run": {"action": "run", "script": "/tmp/example.py", "script_args": ["alpha"]},
            "shutdown": {"action": "shutdown"},
        }
        for action in self.contract["actions"]:
            with self.subTest(action=action):
                response = self.module.handle_request(daemon, requests[action])
                self.assertEqual(response["status"], "ok")


if __name__ == "__main__":
    unittest.main()
