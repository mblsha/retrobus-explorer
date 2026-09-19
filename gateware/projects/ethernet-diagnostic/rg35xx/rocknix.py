"""Fetch the ROCKNIX files this build pins, and nothing else.

The kernel is mainline plus ROCKNIX's patches and configuration, and the panel
needs ROCKNIX's init-sequence firmware, so a build starts from files that live
in another repository. rocknix-sources.json records the commit they came from
and a SHA-256 for each. This turns that manifest back into files: every file is
requested at the pinned commit and written only if its hash matches, so what
arrives is what was measured, or nothing arrives at all.

Downloads go through curl and GitHub's contents API. On the bench machine that
is the only route that works: raw.githubusercontent.com is unreachable, and
Python's own HTTPS client intermittently fails its TLS handshake with the API
while curl does not.
"""

import base64
import hashlib
import json
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


def download(repository: str, commit: str, path: str) -> bytes:
    """Return one file of `repository` at `commit`, or raise FileNotFoundError."""
    from urllib.parse import quote

    url = f"https://api.github.com/repos/{repository}/contents/{quote(path)}?ref={commit}"
    result = subprocess.run(
        ["curl", "-sS", "--fail-with-body", "--max-time", "60", url],
        capture_output=True, check=False,
    )
    try:
        reply = json.loads(result.stdout or b"{}")
    except json.JSONDecodeError as error:
        raise OSError(f"{path}: GitHub returned something that is not JSON") from error
    if reply.get("status") == "404" or reply.get("message") == "Not Found":
        raise FileNotFoundError(path)
    if result.returncode or "content" not in reply:
        raise OSError(f"{path}: {reply.get('message') or result.stderr.decode()[:200]}")
    return base64.b64decode(reply["content"])


def _pinned(content: bytes, digest: str, name: str) -> bytes:
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError(f"{name} at the pinned commit does not match its recorded hash")
    return content


def fetch_kernel_sources(work: Path, sources: Path = SOURCES, download=download) -> list[str]:
    """Write the pinned patches and configuration into a kernel work directory."""
    manifest = json.loads(sources.read_text())
    repository, commit = manifest["repository"], manifest["commit"]
    patches = work / "patches"
    patches.mkdir(parents=True, exist_ok=True)
    written = []
    for name, digest in sorted(manifest["patches"].items()):
        for directory in PATCH_DIRECTORIES:
            try:
                content = download(repository, commit, f"{directory}/{name}")
            except FileNotFoundError:
                continue
            (patches / name).write_bytes(_pinned(content, digest, name))
            written.append(name)
            break
        else:
            raise FileNotFoundError(f"{name} is in neither patch directory at {commit[:12]}")
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
