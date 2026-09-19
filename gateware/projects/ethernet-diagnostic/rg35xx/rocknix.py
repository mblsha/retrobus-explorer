"""Fetch the ROCKNIX files this build pins, and nothing else.

The kernel is mainline plus ROCKNIX's patches and configuration, and the panel
needs ROCKNIX's init-sequence firmware, so a build starts from files that live
in another repository. rocknix-sources.json records the commit they came from
and a SHA-256 for each. This turns that manifest back into files: every file is
requested at the pinned commit and written only if its hash matches, so what
arrives is what was measured, or nothing arrives at all.

Downloads go through GitHub's contents API, by way of the gh CLI when it is
installed and curl otherwise. The API is the only route that works from the
bench machine, where raw.githubusercontent.com is unreachable and Python's own
HTTPS client intermittently fails its TLS handshake. gh matters because it is
authenticated: a fetch is about thirty requests and an anonymous address is
allowed sixty an hour, which the first day of using this ran out of.
"""

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "rocknix-sources.json"
# Where the pinned files live in ROCKNIX's tree. Device patches override generic
# ones of the same name there, so the device directory is tried first.
PATCH_DIRECTORIES = (
    "projects/ROCKNIX/devices/H700/patches/linux",
    "packages/linux/patches/default",
)
CONFIG_PATH = "projects/ROCKNIX/devices/H700/linux/linux.aarch64.conf"
FIRMWARE_DIRECTORY = (
    "projects/ROCKNIX/packages/linux-firmware/kernel-firmware/extra-firmware"
)


def _api(query: str):
    """One GET against the GitHub API; FileNotFoundError for a 404."""
    if shutil.which("gh"):
        result = subprocess.run(["gh", "api", query], capture_output=True, check=False)
        if result.returncode:
            message = (result.stderr or result.stdout).decode(errors="replace").strip()
            if "404" in message:
                raise FileNotFoundError(query)
            raise OSError(message[:200])
        return json.loads(result.stdout)
    result = subprocess.run(
        ["curl", "-sS", "--max-time", "60", f"https://api.github.com/{query}"],
        capture_output=True, check=False,
    )
    try:
        reply = json.loads(result.stdout or b"{}")
    except json.JSONDecodeError as error:
        raise OSError(f"{query}: GitHub returned something that is not JSON") from error
    if isinstance(reply, dict) and reply.get("message") == "Not Found":
        raise FileNotFoundError(query)
    if result.returncode or (isinstance(reply, dict) and "message" in reply and "content" not in reply):
        detail = reply.get("message") if isinstance(reply, dict) else ""
        raise OSError(f"{query}: {detail or result.stderr.decode()[:200]}")
    return reply


def _contents(repository: str, commit: str, path: str) -> str:
    from urllib.parse import quote

    return f"repos/{repository}/contents/{quote(path)}?ref={commit}"


def download(repository: str, commit: str, path: str) -> bytes:
    """Return one file of `repository` at `commit`, or raise FileNotFoundError."""
    return base64.b64decode(_api(_contents(repository, commit, path))["content"])


def listing(repository: str, commit: str, directory: str) -> set[str]:
    """Return the names directly inside `directory` at `commit`."""
    return {entry["name"] for entry in _api(_contents(repository, commit, directory))}


def _pinned(content: bytes, digest: str, name: str) -> bytes:
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f"{name} at the pinned commit does not match its recorded hash")
    return content


def fetch_kernel_sources(work: Path, sources: Path = SOURCES, download=download,
                         listing=listing) -> list[str]:
    """Write the pinned patches and configuration into a kernel work directory."""
    manifest = json.loads(sources.read_text())
    repository, commit = manifest["repository"], manifest["commit"]
    # Each directory is listed once, rather than every patch being asked for in
    # both: the manifest names patches without saying which directory holds
    # them, and a request that comes back 404 still counts against the quota.
    where = {}
    for directory in reversed(PATCH_DIRECTORIES):
        for name in listing(repository, commit, directory):
            where[name] = directory
    patches = work / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    written = []
    for name, digest in sorted(manifest["patches"].items()):
        if name not in where:
            raise FileNotFoundError(f"{name} is in neither patch directory at {commit[:12]}")
        content = download(repository, commit, f"{where[name]}/{name}")
        (patches / name).write_bytes(_pinned(content, digest, name))
        written.append(name)
    config = _pinned(download(repository, commit, CONFIG_PATH), manifest["config_sha256"], "base.config")
    (work / "base.config").write_bytes(config)
    return [*written, "base.config"]


def fetch_firmware(destination: Path, sources: Path = SOURCES, download=download) -> list[str]:
    """Write the pinned firmware files under `destination`, as /lib/firmware sees them."""
    manifest = json.loads(sources.read_text())
    repository, commit = manifest["repository"], manifest["commit"]
    written = []
    for name, digest in sorted(manifest.get("firmware", {}).items()):
        content = _pinned(download(repository, commit, f"{FIRMWARE_DIRECTORY}/{name}"), digest, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        written.append(name)
    return written


def verified_firmware(firmware_dir: Path, sources: Path = SOURCES) -> dict[str, bytes]:
    """Return the pinned firmware files from `firmware_dir`, or refuse.

    The panel's init sequence is a firmware file. One that is missing leaves
    the screen dark with nothing to say why, and one that is wrong drives a
    panel with another panel's register writes, so both are stopped against the
    hashes recorded beside the kernel sources.
    """
    pinned = json.loads(sources.read_text()).get("firmware", {})
    files = {}
    for name, digest in sorted(pinned.items()):
        path = firmware_dir / name
        if not path.is_file():
            raise ValueError(f"firmware {name} is missing from {firmware_dir}; --fetch downloads it")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError(f"firmware {name} does not match the pinned hash")
        files[name] = content
    return files
