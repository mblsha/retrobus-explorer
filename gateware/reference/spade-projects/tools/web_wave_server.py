#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import subprocess
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_SURFER = "https://app.surfer-project.org"
RUN_LOCK = threading.Lock()


@dataclass(frozen=True)
class Project:
    name: str
    path: Path

    @property
    def wave_path(self) -> Path:
        return self.path / "test" / "dump.surfer.vcd"

    @property
    def test_script(self) -> Path:
        return self.path / "scripts" / "test_with_vcd.py"


def list_projects() -> list[Project]:
    projects: list[Project] = []
    for path in sorted(ROOT.glob("*-spade")):
        if not path.is_dir():
            continue
        if not (path / "scripts" / "test_with_vcd.py").is_file():
            continue
        projects.append(Project(name=path.name, path=path))
    return projects


def find_project(name: str) -> Project | None:
    for project in list_projects():
        if project.name == name:
            return project
    return None


def project_payload(project: Project, base_url: str) -> dict[str, Any]:
    wave_exists = project.wave_path.is_file()
    wave_url = f"{base_url}/wave/{urllib.parse.quote(project.name)}"
    viewer_url = f"{base_url}/open/{urllib.parse.quote(project.name)}"
    return {
        "name": project.name,
        "path": str(project.path),
        "wave_exists": wave_exists,
        "wave_url": wave_url,
        "viewer_url": viewer_url,
    }


def run_testbench(project: Project) -> tuple[int, str]:
    cmd = [str(project.test_script)]
    proc = subprocess.run(
        cmd,
        cwd=project.path,
        text=True,
        capture_output=True,
        check=False,
    )
    combined = proc.stdout
    if proc.stderr:
        combined = f"{combined}\n{proc.stderr}" if combined else proc.stderr
    return proc.returncode, combined


def html_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Spade Wave Browser</title>
  <style>
    body { font-family: sans-serif; max-width: 980px; margin: 2rem auto; padding: 0 1rem; }
    h1 { margin-bottom: 0.5rem; }
    .muted { color: #555; margin-bottom: 1rem; }
    .row { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; margin-bottom: 0.75rem; }
    select, button { font-size: 0.95rem; padding: 0.45rem 0.7rem; }
    #status { font-size: 0.95rem; min-height: 1.2rem; }
    pre {
      background: #111; color: #e5e5e5; padding: 0.8rem; border-radius: 6px;
      overflow: auto; max-height: 58vh; white-space: pre-wrap;
    }
    code { background: #f2f2f2; padding: 0.15rem 0.3rem; border-radius: 4px; }
  </style>
</head>
<body>
  <h1>Spade Wave Browser</h1>
  <div class="muted">
    Pick a project, run its testbench, then open the waveform in the Surfer web app.
  </div>

  <div class="row">
    <label for="project">Project</label>
    <select id="project"></select>
    <button id="refresh">Refresh</button>
  </div>

  <div class="row">
    <button id="run">Run Testbench</button>
    <button id="open">Open Waveform Viewer</button>
    <button id="raw">Open Raw dump.surfer.vcd</button>
  </div>

  <div id="status"></div>
  <pre id="log"></pre>

  <script>
    const projectSelect = document.getElementById("project");
    const statusEl = document.getElementById("status");
    const logEl = document.getElementById("log");
    let projects = [];

    function selected() {
      return projectSelect.value;
    }

    function setStatus(text) {
      statusEl.textContent = text;
    }

    function setLog(text) {
      logEl.textContent = text || "";
    }

    async function loadProjects() {
      setStatus("Loading projects...");
      const resp = await fetch("/api/projects");
      const data = await resp.json();
      projects = data.projects || [];
      projectSelect.innerHTML = "";
      for (const p of projects) {
        const opt = document.createElement("option");
        opt.value = p.name;
        opt.textContent = p.wave_exists ? `${p.name} (wave ready)` : `${p.name} (no wave yet)`;
        projectSelect.appendChild(opt);
      }
      if (projects.length === 0) {
        setStatus("No Spade projects found.");
      } else {
        setStatus(`Loaded ${projects.length} project(s).`);
      }
    }

    async function runProject() {
      const name = selected();
      if (!name) return;
      setStatus(`Running testbench for ${name}...`);
      setLog("");
      const resp = await fetch(`/api/run?project=${encodeURIComponent(name)}`, { method: "POST" });
      const data = await resp.json();
      setLog(data.output || "");
      if (data.ok) {
        setStatus(`Testbench passed for ${name}. Waveform ready.`);
      } else {
        setStatus(`Testbench failed for ${name} (exit=${data.returncode}).`);
      }
      await loadProjects();
    }

    function openViewer() {
      const name = selected();
      if (!name) return;
      window.open(`/open/${encodeURIComponent(name)}`, "_blank");
    }

    function openRaw() {
      const name = selected();
      if (!name) return;
      window.open(`/wave/${encodeURIComponent(name)}`, "_blank");
    }

    document.getElementById("refresh").addEventListener("click", loadProjects);
    document.getElementById("run").addEventListener("click", runProject);
    document.getElementById("open").addEventListener("click", openViewer);
    document.getElementById("raw").addEventListener("click", openRaw);

    loadProjects().catch((err) => setStatus(`Failed to load projects: ${err}`));
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "SpadeWaveServer/1.0"

    def _base_url(self) -> str:
        host = self.headers.get("Host", f"{self.server.server_address[0]}:{self.server.server_address[1]}")
        return f"http://{host}"

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, payload: str, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy_surfer(self, suffix: str, query: str) -> None:
        upstream = f"{UPSTREAM_SURFER}/{suffix}"
        if query:
            upstream = f"{upstream}?{query}"
        req = urllib.request.Request(upstream, headers={"User-Agent": "spade-wave-server"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
                self.send_response(resp.status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            self._send_text(f"Upstream error {err.code}\n\n{detail}", status=err.code)
        except urllib.error.URLError as err:
            self._send_text(f"Upstream unavailable: {err}", status=HTTPStatus.BAD_GATEWAY)

    def _serve_wave(self, project_name: str) -> None:
        project = find_project(project_name)
        if project is None:
            self._send_text(f"Unknown project: {project_name}\n", status=HTTPStatus.NOT_FOUND)
            return
        wave = project.wave_path
        if not wave.is_file():
            self._send_text(
                f"Waveform not found for {project_name}.\nRun the testbench first.\n",
                status=HTTPStatus.NOT_FOUND,
            )
            return
        data = wave.read_bytes()
        content_type = mimetypes.guess_type(str(wave))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send_text(html_page(), content_type="text/html; charset=utf-8")
            return

        if path == "/api/projects":
            base = self._base_url()
            payload = {"projects": [project_payload(p, base) for p in list_projects()]}
            self._send_json(payload)
            return

        if path.startswith("/wave/"):
            name = urllib.parse.unquote(path.removeprefix("/wave/"))
            self._serve_wave(name)
            return

        if path.startswith("/open/"):
            name = urllib.parse.unquote(path.removeprefix("/open/"))
            project = find_project(name)
            if project is None:
                self._send_text(f"Unknown project: {name}\n", status=HTTPStatus.NOT_FOUND)
                return
            load_url = f"{self._base_url()}/wave/{urllib.parse.quote(project.name)}"
            target = f"/surfer/?load_url={urllib.parse.quote(load_url, safe='')}"
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", target)
            self.end_headers()
            return

        if path == "/surfer":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/surfer/")
            self.end_headers()
            return

        if path.startswith("/surfer/"):
            suffix = path.removeprefix("/surfer/")
            self._proxy_surfer(suffix, parsed.query)
            return

        if path == "/healthz":
            self._send_text("ok\n")
            return

        self._send_text("Not found\n", status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/run":
            self._send_text("Not found\n", status=HTTPStatus.NOT_FOUND)
            return

        query = urllib.parse.parse_qs(parsed.query)
        name = query.get("project", [""])[0]
        if not name:
            self._send_json({"ok": False, "error": "missing project query parameter"}, status=HTTPStatus.BAD_REQUEST)
            return

        project = find_project(name)
        if project is None:
            self._send_json({"ok": False, "error": f"unknown project: {name}"}, status=HTTPStatus.NOT_FOUND)
            return

        with RUN_LOCK:
            code, output = run_testbench(project)

        base = self._base_url()
        payload = {
            "ok": code == 0,
            "returncode": code,
            "output": output,
            "project": project_payload(project, base),
        }
        status = HTTPStatus.OK if code == 0 else HTTPStatus.BAD_REQUEST
        self._send_json(payload, status=status)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local web UI for Spade testbench waveforms")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8090, help="Bind port")
    return parser.parse_args()


def best_local_ip() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packets are sent; this only picks a local interface.
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def main() -> int:
    args = parse_args()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        print(f"Spade wave server listening on {args.host}:{args.port}")
        if args.host == "0.0.0.0":
            ip = best_local_ip()
            if ip:
                print(f"Open from this machine: http://127.0.0.1:{args.port}")
                print(f"Open from LAN devices: http://{ip}:{args.port}")
            else:
                print(f"Open from this machine: http://127.0.0.1:{args.port}")
                print(f"Open from LAN devices: http://<this-machine-ip>:{args.port}")
        else:
            print(f"Open in browser: http://{args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
