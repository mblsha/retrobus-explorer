from __future__ import annotations

import array
import collections
import importlib.util
import subprocess
import sys
import sysconfig
import threading
import time
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "py" / "d3xx" / "ftd3xx.py").is_file():
            return candidate
    raise RuntimeError(f"failed to locate retrobus-explorer repo root from {start}")


REPO_ROOT = _find_repo_root(SCRIPT_DIR)
D3XX_DIR = REPO_ROOT / "py" / "d3xx"

if str(D3XX_DIR) not in sys.path:
    sys.path.insert(0, str(D3XX_DIR))



def _load_module_from_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mft = _load_module_from_path("_ftd3xx_linux", D3XX_DIR / "_ftd3xx_linux.py")
ftd3xx = _load_module_from_path("ftd3xx", D3XX_DIR / "ftd3xx.py")

NATIVE_MODULE_NAME = "pc_e500_ft600_native"
NATIVE_CPP = SCRIPT_DIR / f"{NATIVE_MODULE_NAME}.cpp"
NATIVE_SO = SCRIPT_DIR / f"{NATIVE_MODULE_NAME}{sysconfig.get_config_var('EXT_SUFFIX')}"


def _build_native_module() -> None:
    include_dir = sysconfig.get_paths()["include"]
    command = [
        "c++",
        "-O3",
        "-std=c++17",
        "-shared",
        "-I",
        include_dir,
        "-o",
        str(NATIVE_SO),
        str(NATIVE_CPP),
    ]
    if sys.platform == "darwin":
        command[1:1] = ["-undefined", "dynamic_lookup"]
    subprocess.run(command, check=True, cwd=SCRIPT_DIR)


def _load_native_module():
    if not NATIVE_SO.exists() or NATIVE_SO.stat().st_mtime < NATIVE_CPP.stat().st_mtime:
        _build_native_module()
    spec = importlib.util.spec_from_file_location(NATIVE_MODULE_NAME, NATIVE_SO)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load native module from {NATIVE_SO}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[NATIVE_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


native = _load_native_module()


DEFAULT_PIPE_ID = 0x00
DEFAULT_READ_SIZE = 64 * 1024
DEFAULT_READ_TIMEOUT_MS = 20
DEFAULT_STREAM_SIZE = 4
DEFAULT_POST_STOP_IDLE_S = 0.1
DEFAULT_POST_STOP_HARD_S = 1.0
DEFAULT_MAX_RETAINED_WORDS = 262_144
SUPERVISOR_ROM_MIN = 0x10000
SUPERVISOR_ROM_MAX = 0x100FF
EXPERIMENT_ROM_MIN = 0x10100
EXPERIMENT_ROM_MAX = 0x106FF
COMMAND_BLOCK_MIN = 0x107E0
COMMAND_BLOCK_MAX = 0x107FF
CTRL_RANGE_MIN = 0x1FFF0
CTRL_RANGE_MAX = 0x1FFFF
HI_STACK_MIN = 0x3F800
HI_STACK_MAX = 0x3FFFF

CTRL_ADDR_LABELS = {
    0x1FFF0: "MARK_START",
    0x1FFF1: "ECHO",
    0x1FFF2: "MARK_STOP",
    0x1FFF3: "MARK_ABORT",
    0x1FFF4: "FT_STREAM_CFG",
}


@dataclass(frozen=True)
class FtSampleWord:
    raw_word: int
    addr: int
    data: int
    status: int


@dataclass(frozen=True)
class FtCaptureResult:
    words: list[int]
    raw_bytes: int
    chunk_count: int
    pending_bytes_hex: str
    decode_swap_u16: bool
    drain_idle_s: float
    drain_hard_s: float
    retained_words: int
    total_words_seen: int
    max_retained_words: int
    truncated_head: bool


@dataclass(frozen=True)
class FtCaptureSession:
    start_word_index: int
    start_raw_bytes: int
    start_chunk_count: int


@dataclass(frozen=True)
class FtDecodedEvent:
    index: int
    raw_word: int
    addr: int
    data: int
    status: int
    rw: bool
    ce1_active: bool
    ce6_active: bool
    synthetic_followup: bool
    from_cycle_start: bool
    ctrl_range: bool
    kind: str


@dataclass(frozen=True)
class FtAnnotatedEvent:
    event: FtDecodedEvent
    region: str
    addr_label: str | None
    note: str | None


def decode_sampled_word(word: int) -> FtSampleWord:
    return FtSampleWord(
        raw_word=word & 0xFFFFFFFF,
        addr=word & 0x3FFFF,
        data=(word >> 18) & 0xFF,
        status=(word >> 26) & 0x3F,
    )


def decode_status_flags(status: int) -> dict[str, bool]:
    return {
        "rw": bool(status & 0x01),
        "ce1_active": bool(status & 0x02),
        "ce6_active": bool(status & 0x04),
        "synthetic_followup": bool(status & 0x08),
        "from_cycle_start": bool(status & 0x10),
        "ctrl_range": bool(status & 0x20),
    }


def classify_decoded_word(word: int, *, index: int = 0) -> FtDecodedEvent:
    decoded = decode_sampled_word(word)
    flags = decode_status_flags(decoded.status)
    if flags["ce6_active"] and flags["ctrl_range"]:
        kind = "ce6_ctrl_read" if flags["rw"] else "ce6_ctrl_write"
    elif flags["ce6_active"]:
        kind = "ce6_read" if flags["rw"] else "ce6_write"
    elif flags["ce1_active"]:
        kind = "ce1_read" if flags["rw"] else "ce1_write"
    else:
        kind = "addr_only_read" if flags["rw"] else "addr_only_write"
    return FtDecodedEvent(
        index=index,
        raw_word=decoded.raw_word,
        addr=decoded.addr,
        data=decoded.data,
        status=decoded.status,
        rw=flags["rw"],
        ce1_active=flags["ce1_active"],
        ce6_active=flags["ce6_active"],
        synthetic_followup=flags["synthetic_followup"],
        from_cycle_start=flags["from_cycle_start"],
        ctrl_range=flags["ctrl_range"],
        kind=kind,
    )


def decode_word_stream(words: list[int]) -> list[FtDecodedEvent]:
    return [classify_decoded_word(word, index=index) for index, word in enumerate(words)]


def annotate_address(addr: int) -> tuple[str, str | None, str | None]:
    if addr in CTRL_ADDR_LABELS:
        return ("ce6_ctrl", CTRL_ADDR_LABELS[addr], None)
    if COMMAND_BLOCK_MIN <= addr <= COMMAND_BLOCK_MAX:
        return ("command_block", f"CMD+0x{addr - COMMAND_BLOCK_MIN:02X}", None)
    if EXPERIMENT_ROM_MIN <= addr <= EXPERIMENT_ROM_MAX:
        return ("experiment_rom", None, None)
    if SUPERVISOR_ROM_MIN <= addr <= SUPERVISOR_ROM_MAX:
        return ("supervisor_rom", None, None)
    if CTRL_RANGE_MIN <= addr <= CTRL_RANGE_MAX:
        return ("ce6_ctrl", None, None)
    if HI_STACK_MIN <= addr <= HI_STACK_MAX:
        return ("high_stack_window", None, "likely stack/internal high memory")
    return ("other", None, None)


def annotate_event(event: FtDecodedEvent) -> FtAnnotatedEvent:
    region, addr_label, note = annotate_address(event.addr)
    return FtAnnotatedEvent(event=event, region=region, addr_label=addr_label, note=note)


def annotate_event_stream(events: list[FtDecodedEvent]) -> list[FtAnnotatedEvent]:
    return [annotate_event(event) for event in events]


def find_measurement_window(
    events: list[FtDecodedEvent],
    *,
    start_tag: int,
    stop_tag: int,
) -> list[FtDecodedEvent]:
    start_index: int | None = None
    for index, event in enumerate(events):
        if event.kind == "ce6_ctrl_write" and event.addr == 0x1FFF0 and event.data == (start_tag & 0xFF):
            start_index = index
            break
    if start_index is None:
        return []
    for index in range(start_index + 1, len(events)):
        event = events[index]
        if event.kind == "ce6_ctrl_write" and event.addr == 0x1FFF2 and event.data == (stop_tag & 0xFF):
            return events[start_index : index + 1]
    return events[start_index:]


def infer_execution_window(events: list[FtDecodedEvent]) -> list[FtDecodedEvent]:
    start_index: int | None = None
    left_experiment = False
    for index, event in enumerate(events):
        if start_index is None:
            if EXPERIMENT_ROM_MIN <= event.addr <= EXPERIMENT_ROM_MAX:
                start_index = index
            continue
        if not (EXPERIMENT_ROM_MIN <= event.addr <= EXPERIMENT_ROM_MAX):
            left_experiment = True
        if (
            left_experiment
            and SUPERVISOR_ROM_MIN <= event.addr <= SUPERVISOR_ROM_MAX
            and event.kind.startswith("ce6_")
        ):
            return events[start_index : index + 1]
    return events[start_index:] if start_index is not None else []


def compact_event_stream(events: list[FtDecodedEvent]) -> list[FtDecodedEvent]:
    compacted: list[FtDecodedEvent] = []
    for event in events:
        if compacted:
            previous = compacted[-1]
            # A late CE-qualified synthetic followup after an address-only seed is
            # usually the more useful representation of the real bus action.
            if (
                event.synthetic_followup
                and previous.addr == event.addr
                and previous.data == event.data
                and previous.kind.startswith("addr_only")
                and not event.kind.startswith("addr_only")
            ):
                compacted[-1] = event
                continue
            if (
                previous.addr == event.addr
                and previous.data == event.data
                and previous.kind == event.kind
                and previous.synthetic_followup == event.synthetic_followup
            ):
                continue
        if event.synthetic_followup and compacted:
            previous = compacted[-1]
            if (
                previous.addr == event.addr
                and previous.data == event.data
                and previous.kind == event.kind
            ):
                continue
        if event.synthetic_followup and event.kind.startswith("addr_only"):
            continue
        compacted.append(event)
    return compacted


def preview_event_stream(
    words: list[int],
    *,
    limit: int = 32,
    compact: bool = False,
    window: str = "all",
    start_tag: int | None = None,
    stop_tag: int | None = None,
) -> list[dict[str, object]]:
    events = decode_word_stream(words)
    if window == "measurement" and start_tag is not None and stop_tag is not None:
        measurement_window = find_measurement_window(events, start_tag=start_tag, stop_tag=stop_tag)
        if measurement_window:
            events = measurement_window
    elif window == "execution":
        execution_window = infer_execution_window(events)
        if execution_window:
            events = execution_window
    if compact:
        events = compact_event_stream(events)
    preview = []
    for annotated in annotate_event_stream(events[:limit]):
        event = annotated.event
        preview.append(
            {
                "index": event.index,
                "raw_word": event.raw_word,
                "raw_hex": f"{event.raw_word:08X}",
                "addr": event.addr,
                "data": event.data,
                "status": event.status,
                "kind": event.kind,
                "rw": event.rw,
                "ce1_active": event.ce1_active,
                "ce6_active": event.ce6_active,
                "synthetic_followup": event.synthetic_followup,
                "from_cycle_start": event.from_cycle_start,
                "ctrl_range": event.ctrl_range,
                "region": annotated.region,
                "addr_label": annotated.addr_label,
                "note": annotated.note,
            }
        )
    return preview


class Ft600Capture:
    def __init__(
        self,
        *,
        pipe_id: int = DEFAULT_PIPE_ID,
        read_size: int = DEFAULT_READ_SIZE,
        read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS,
        stream_size: int = DEFAULT_STREAM_SIZE,
        swap_bytes_within_u16: bool = False,
        post_stop_idle_s: float = DEFAULT_POST_STOP_IDLE_S,
        post_stop_hard_s: float = DEFAULT_POST_STOP_HARD_S,
        max_retained_words: int = DEFAULT_MAX_RETAINED_WORDS,
    ) -> None:
        self.pipe_id = pipe_id & 0xFF
        self.read_size = read_size
        self.read_timeout_ms = read_timeout_ms
        self.stream_size = stream_size
        self.swap_bytes_within_u16 = swap_bytes_within_u16
        self.post_stop_idle_s = post_stop_idle_s
        self.post_stop_hard_s = post_stop_hard_s
        self.max_retained_words = max(1, int(max_retained_words))
        self._device = None
        self._segments: collections.deque[tuple[int, bytes]] = collections.deque()
        self._retained_word_count = 0
        self._total_word_count = 0
        self._raw_bytes = 0
        self._chunk_count = 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._error: Exception | None = None
        self._lock = threading.Lock()
        self._pending_bytes = b""
        self._session: FtCaptureSession | None = None
        self._stale_drained = False

    def _open_device(self) -> None:
        if self._device is not None:
            return
        device = ftd3xx.create(0, mft.FT_OPEN_BY_INDEX)
        if device is None:
            raise RuntimeError("failed to open FT600 via D3XX")
        self._device = device
        try:
            self._device.setStreamPipe(self.pipe_id, self.stream_size)
        except Exception:
            pass
        try:
            self._device.flushPipe(self.pipe_id)
        except Exception:
            pass

    def _close_device(self) -> None:
        if self._device is None:
            return
        try:
            try:
                self._device.clearStreamPipe(self.pipe_id)
            except Exception:
                pass
            self._device.close()
        finally:
            self._device = None

    def _read_chunk(self) -> bytes:
        assert self._device is not None
        result = self._device.readPipeEx(self.pipe_id, self.read_size, timeout=self.read_timeout_ms, raw=True)
        if isinstance(result, dict):
            return bytes(result.get("bytes", b""))
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        return b""

    def _retained_start_word_index_locked(self) -> int:
        if self._segments:
            return self._segments[0][0]
        return self._total_word_count

    def _append_decoded_bytes_locked(self, decoded_bytes: bytes) -> None:
        if not decoded_bytes:
            return
        word_count = len(decoded_bytes) // 4
        if word_count <= 0:
            return
        self._segments.append((self._total_word_count, bytes(decoded_bytes)))
        self._total_word_count += word_count
        self._retained_word_count += word_count
        while self._retained_word_count > self.max_retained_words and self._segments:
            segment_start, segment_bytes = self._segments[0]
            segment_words = len(segment_bytes) // 4
            overflow_words = self._retained_word_count - self.max_retained_words
            if overflow_words >= segment_words:
                self._segments.popleft()
                self._retained_word_count -= segment_words
                continue
            trim_words = overflow_words
            trim_bytes = trim_words * 4
            self._segments[0] = (segment_start + trim_words, segment_bytes[trim_bytes:])
            self._retained_word_count -= trim_words
            break

    def set_max_retained_words(self, max_retained_words: int) -> None:
        if max_retained_words < 1:
            raise ValueError("max_retained_words must be >= 1")
        with self._lock:
            self.max_retained_words = int(max_retained_words)
            while self._retained_word_count > self.max_retained_words and self._segments:
                segment_start, segment_bytes = self._segments[0]
                segment_words = len(segment_bytes) // 4
                overflow_words = self._retained_word_count - self.max_retained_words
                if overflow_words >= segment_words:
                    self._segments.popleft()
                    self._retained_word_count -= segment_words
                    continue
                trim_words = overflow_words
                trim_bytes = trim_words * 4
                self._segments[0] = (segment_start + trim_words, segment_bytes[trim_bytes:])
                self._retained_word_count -= trim_words
                break

    def _drain_stale_data(self) -> None:
        deadline = time.monotonic() + 0.25
        while time.monotonic() < deadline:
            chunk = self._read_chunk()
            if not chunk:
                break

    def _wait_for_quiet_or_deadline(self, idle_s: float, hard_s: float) -> int:
        stable_deadline: float | None = None
        hard_deadline = time.monotonic() + hard_s
        with self._lock:
            last_words = self._total_word_count
        while True:
            time.sleep(min(0.01, idle_s if idle_s > 0 else 0.01))
            with self._lock:
                current_words = self._total_word_count
            now = time.monotonic()
            if current_words != last_words:
                last_words = current_words
                stable_deadline = now + idle_s
            elif stable_deadline is None:
                stable_deadline = now + idle_s
            elif now >= stable_deadline:
                return current_words
            if now >= hard_deadline:
                return current_words

    def _read_loop(self) -> None:
        assert self._device is not None
        try:
            while not self._stop_event.is_set():
                chunk = self._read_chunk()
                if chunk:
                    decoded_bytes, self._pending_bytes = native.decode_words_packed(
                        chunk,
                        pending=self._pending_bytes,
                        swap_bytes_within_u16=self.swap_bytes_within_u16,
                    )
                    with self._lock:
                        self._raw_bytes += len(chunk)
                        self._chunk_count += 1
                        self._append_decoded_bytes_locked(decoded_bytes)
        except Exception as exc:  # noqa: BLE001
            self._error = exc

    def ensure_running(self) -> None:
        if self._thread is None:
            self._error = None
            self._pending_bytes = b""
            self._stop_event.clear()
            self._open_device()
            if not self._stale_drained:
                self._drain_stale_data()
                self._stale_drained = True
            self._thread = threading.Thread(target=self._read_loop, name="pc-e500-ft600", daemon=True)
            self._thread.start()

    def start(self) -> None:
        self.ensure_running()
        if self._session is not None:
            raise RuntimeError("FT capture session already started")
        with self._lock:
            self._session = FtCaptureSession(
                start_word_index=self._total_word_count,
                start_raw_bytes=self._raw_bytes,
                start_chunk_count=self._chunk_count,
            )

    def shutdown(self) -> None:
        if self._thread is None:
            self._close_device()
            return
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            raise RuntimeError("timed out waiting for FT capture thread to stop")
        self._thread = None
        self._session = None
        self._close_device()

    def _snapshot_words_locked(self, start_word_index: int, end_word_index: int) -> tuple[list[int], bool]:
        retained_start = self._retained_start_word_index_locked()
        effective_start = max(start_word_index, retained_start)
        effective_end = min(end_word_index, self._total_word_count)
        truncated_head = start_word_index < retained_start
        if effective_end <= effective_start:
            return [], truncated_head
        chunks: list[bytes] = []
        for segment_start, segment_bytes in self._segments:
            segment_words = len(segment_bytes) // 4
            segment_end = segment_start + segment_words
            if segment_end <= effective_start:
                continue
            if segment_start >= effective_end:
                break
            slice_start_words = max(effective_start - segment_start, 0)
            slice_end_words = min(effective_end - segment_start, segment_words)
            start_byte = slice_start_words * 4
            end_byte = slice_end_words * 4
            chunks.append(segment_bytes[start_byte:end_byte])
        words = array.array("I")
        for chunk in chunks:
            words.frombytes(chunk)
        return words.tolist(), truncated_head

    def stop(self) -> FtCaptureResult:
        if self._thread is None or self._session is None:
            raise RuntimeError("FT capture session was not started")
        end_word_index = self._wait_for_quiet_or_deadline(self.post_stop_idle_s, self.post_stop_hard_s)
        if self._error is not None:
            raise RuntimeError(f"FT capture failed: {self._error}") from self._error
        with self._lock:
            session = self._session
            assert session is not None
            words, truncated_head = self._snapshot_words_locked(session.start_word_index, end_word_index)
            raw_bytes = self._raw_bytes - session.start_raw_bytes
            chunk_count = self._chunk_count - session.start_chunk_count
            retained_words = self._retained_word_count
            total_words_seen = self._total_word_count
            max_retained_words = self.max_retained_words
            self._session = None
        return FtCaptureResult(
            words=words,
            raw_bytes=raw_bytes,
            chunk_count=chunk_count,
            pending_bytes_hex=self._pending_bytes.hex(),
            decode_swap_u16=self.swap_bytes_within_u16,
            drain_idle_s=self.post_stop_idle_s,
            drain_hard_s=self.post_stop_hard_s,
            retained_words=retained_words,
            total_words_seen=total_words_seen,
            max_retained_words=max_retained_words,
            truncated_head=truncated_head,
        )
