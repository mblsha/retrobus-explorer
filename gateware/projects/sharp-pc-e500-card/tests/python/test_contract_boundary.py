from __future__ import annotations

import json
from pathlib import Path

from pce500_host.contract import SUPERVISOR_RPC_ACTIONS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = PROJECT_ROOT / "tests" / "supervisor_rpc_contract.json"


def test_contract_file_matches_shared_constant():
    payload = json.loads(CONTRACT_PATH.read_text())
    assert tuple(payload["actions"]) == SUPERVISOR_RPC_ACTIONS
