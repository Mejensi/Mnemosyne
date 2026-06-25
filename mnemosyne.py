# -*- coding: utf-8 -*-
"""
Mnemosyne V2.0 - The Keeper of Digital Memory
Copyright (C) 2026 Mejensi
Licensed under GNU GPL v3.0

This software relies on FFmpeg (https://ffmpeg.org) for video processing.
FFmpeg is licensed under the LGPL/GPL.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import os, sys, platform, subprocess, shutil, time, datetime, json, argparse, threading, traceback, logging, random, re, hashlib, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional
from logging.handlers import RotatingFileHandler

if platform.system() == "Windows":
    try:
        import ctypes
        # Enable VT100 support for ANSI colors
        kernel32 = ctypes.windll.kernel32
        hStdOut = kernel32.GetStdHandle(-11)
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
        mode.value |= 0x0004 # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        kernel32.SetConsoleMode(hStdOut, mode)
    except (OSError, AttributeError, ValueError, TypeError) as _e:
        print(f"[Mnemosyne] Could not initialize Windows VT100 console mode: {_e}", file=sys.stderr)

VERSION, APP_NAME = "2.0", "Mnemosyne"
SYSTEM, IS_WINDOWS = platform.system(), platform.system() == "Windows"
SESSION_ID = f"{os.getpid()}_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

def ensure_utf8_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

if IS_WINDOWS:
    APP_DATA = Path(os.environ["APPDATA"]) / APP_NAME
else:
    APP_DATA = Path.home() / ".mnemosyne"

LOG_DIR = APP_DATA / "logs"
BIN_DIR = APP_DATA / "bin"
APP_CONFIG_FILE = APP_DATA / "config.json"
FFMPEG_STATE_FILE = APP_DATA / "ffmpeg_state.json"
RUNTIME_DIR_NAME = ".mnemosyne_runtime"
MANAGED_FFMPEG_MARKER = ".mnemosyne_managed_ffmpeg.json"
STALE_FFMPEG_DAYS = 7

PROFILE_PRESETS = {
    "360p": {
        "target_height": 360,
        "video_bitrate": "500k",
        "audio_bitrate": "96k",
        "target_fps": 30,
        "label": "360p Compact",
    },
    "480p": {
        "target_height": 480,
        "video_bitrate": "800k",
        "audio_bitrate": "128k",
        "target_fps": 30,
        "label": "480p Standard",
    },
    "720p": {
        "target_height": 720,
        "video_bitrate": "1800k",
        "audio_bitrate": "160k",
        "target_fps": 30,
        "label": "720p HD",
    },
    "1080p": {
        "target_height": 1080,
        "video_bitrate": "3500k",
        "audio_bitrate": "192k",
        "target_fps": 30,
        "label": "1080p Full HD",
    },
}
PROFILE_KEYS = ("target_height", "video_bitrate", "audio_bitrate", "target_fps")
DEFAULT_PROFILE_ID = "480p"
SAVEABLE_CONFIG_KEYS = {
    "profile_id",
    "target_height",
    "video_bitrate",
    "audio_bitrate",
    "target_fps",
    "max_workers",
    "recursive",
    "verify_frames",
    "auto_download_ffmpeg",
    "x264_preset",
    "ffmpeg_threads",
    "sort",
    "desktop_log",
    "auto_cleanup",
    "show_drive_warnings",
    "preserve_metadata",
    "system_ffmpeg_policy",
}
MANAGED_FFMPEG_STORAGE_MODES = {"appdata", "portable", "session", "custom"}

DEFAULT_CONFIG = {
    "profile_id": DEFAULT_PROFILE_ID,
    "target_height": 480,
    "video_bitrate": "800k",
    "audio_bitrate": "128k",
    "target_fps": 30,
    "max_workers": max(1, os.cpu_count() // 2) if os.cpu_count() else 2,
    "recursive": False,
    "verify_frames": True,
    "auto_download_ffmpeg": True,
    "x264_preset": "medium",
    "ffmpeg_threads": 0,
    "sort": "name_az",
    "desktop_log": False,
    "auto_cleanup": True,
    "show_drive_warnings": True,
    "preserve_metadata": True,
    "system_ffmpeg_policy": "prompt",
}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m4v'}
STREAM_TYPES = ("video", "audio", "subtitle", "data", "attachment")
TEMP_WORKSPACE_NAME = ".mnemosyne_work"
TEMP_WORKSPACE_MARKER = ".mnemosyne_owner"
TEMP_WORKSPACE_LOCK = ".mnemosyne_lock"
TRANSACTION_JOURNAL_SUFFIX = ".mnemosyne_txn.json"
LAUNCHER_DIR_ENV = "MNEMOSYNE_LAUNCHER_DIR"
FFMPEG_CMD = "ffmpeg"
FFPROBE_CMD = "ffprobe"
TARGET_PIXEL_FORMAT = "yuv420p"
VALID_SYSTEM_FFMPEG_POLICIES = {"prompt", "allow", "deny"}
EVERMEET_GPG_FINGERPRINT = "20F6EA3E0CFD6B4C53447A73476C4B611A660874"
EVERMEET_GPG_KEY_URL = "https://evermeet.cx/ffmpeg/0x1A660874.asc"
LOCK = threading.Lock()
TEMP_WORKSPACE_LOCKS = {}
TEMP_WORKSPACE_INIT_LOCK = threading.Lock()
DISPLAY_LOCK = threading.Lock()
RUNTIME_STATE = {"recursive": False, "auto_cleanup": True, "target_dirs": [Path.cwd()]}
UNICODE_OUTPUT_SAMPLE = "╔═║╝➤◆✦█░✓⚠"
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
DISPLAY_STATE = {"mode": None, "last_compact_at": 0.0, "last_compact_snapshot": ""}
MIN_LIVE_DASHBOARD_WIDTH = 68
MIN_LIVE_DASHBOARD_HEIGHT = 14
COMPACT_DASHBOARD_INTERVAL = 1.5

MIN_VALID_VIDEO_BYTES = 10240        # 10 KB (minimum valid video file size)
DOWNLOAD_CHUNK_SIZE = 1024 * 1024     # 1 MB (download and read chunk size)
PROCESS_SPACE_MULTIPLIER = 1.25       # 25% overhead factor for processing space estimate
PROCESS_SPACE_MIN_BYTES = 512 * 1024 * 1024  # 512 MB minimum processing space

FRAME_TOLERANCE_RATIO = 0.02          # 2% frame count tolerance
ASPECT_RATIO_TOLERANCE = 0.03         # 3% aspect ratio deviation tolerance
GEOMETRY_TOLERANCE_RATIO = 0.02       # 2% geometry/resolution deviation tolerance
DURATION_TOLERANCE_MIN = 0.25         # 0.25s minimum duration tolerance
DURATION_TOLERANCE_RATIO = 0.01       # 1% duration ratio tolerance
DURATION_RATIO_MIN = 0.98             # min acceptable output/input duration ratio
DURATION_RATIO_MAX = 1.02             # max acceptable output/input duration ratio

MAX_FFMPEG_TIMEOUT_SEC = 900          # 15 minutes
BASE_DECODE_TIMEOUT_SEC = 60          # 1 minute default
DECODE_TIMEOUT_MULTIPLIER = 4         # duration * 4 + 15s
DECODE_TIMEOUT_ADDEND = 15            # base addend for decode timeout
MIN_DECODE_TIMEOUT_SEC = 30           # minimum decode timeout
PROCESS_TERMINATE_TIMEOUT = 2         # seconds to wait after terminate before kill

@dataclass
class RunContext:
    mode: str
    input_files: List[Path] = field(default_factory=list)
    target_dirs: List[Path] = field(default_factory=list)
    invalid_inputs: List[Path] = field(default_factory=list)
    removable_targets: List[Path] = field(default_factory=list)
    session_config: Dict = field(default_factory=dict)
    saved_config_loaded: bool = False
    ffmpeg_preferences: Dict = field(default_factory=dict)

    @property
    def is_explicit_file_mode(self):
        return self.mode == "explicit-files"

class ProcessManager:
    def __init__(self):
        self.active_procs = set()
        self.lock = threading.Lock()
    def register(self, proc):
        with self.lock: self.active_procs.add(proc)
    def unregister(self, proc):
        with self.lock: self.active_procs.discard(proc)
    def kill_all(self):
        with self.lock:
            procs_snapshot = list(self.active_procs)
        for p in procs_snapshot:
            try:
                p.terminate()
                try:
                    p.wait(timeout=PROCESS_TERMINATE_TIMEOUT)
                except subprocess.TimeoutExpired:
                    p.kill()
            except Exception as e:
                logging.warning(f"Failed to kill process: {e}")
PROCESS_MGR = ProcessManager()

DRIVE_FIXED = 3
DRIVE_REMOVABLE = 2

class C:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    PRIMARY = '\033[38;2;91;155;213m'   # Soft Blue
    SUCCESS = '\033[38;2;16;185;129m'   # Emerald
    WARNING = '\033[38;2;245;158;11m'   # Amber
    ERROR = '\033[38;2;239;68;68m'      # Rose
    INFO = '\033[38;2;14;165;233m'      # Sky
    ACCENT = '\033[38;2;168;85;247m'    # Purple
    MUTED = '\033[38;2;100;116;139m'    # Slate
    WHITE = '\033[38;2;255;255;255m'

# Unicode escapes for box characters to prevent source encoding issues
BOX_UNICODE = {
    'tl': '\u2554', # ╔
    'tr': '\u2557', # ╗
    'bl': '\u255a', # ╚
    'br': '\u255d', # ╝
    'h':  '\u2550', # ═
    'v':  '\u2551', # ║
    'ml': '\u2560', # ╠
    'mr': '\u2563'  # ╣
}
BOX_ASCII = {
    'tl': '+',
    'tr': '+',
    'bl': '+',
    'br': '+',
    'h':  '-',
    'v':  '|',
    'ml': '+',
    'mr': '+'
}

ASCII_ART = r"""
 __  __                                                    
|  \/  |____   ___ ____ ___   ___  ___ _   _ _ __   ___   
| |\/| | '_ \ / _ \ '_ ` _ \ / _ \/ __| | | | '_ \ / _ \  
| |  | | | | |  __/ | | | | | (_) \__ \ |_| | | | |  __/  
|_|  |_|_| |_|\___|_| |_| |_|\___/|___/\__, |_| |_|\___|  
                                       |___/ v{version}
"""

INFO_TICKER_UNICODE = [
    "➤ Targeting 30 FPS for optimal timeline stability.",
    "◆ Safety Bridge ensures zero-loss atomic file swaps.",
    "✦ Mnemosyne preserves file dates to keep your timeline intact.",
    "✦ Processing is 100% local. No cloud, no tracking.",
    "◈ GPU acceleration detected - using hardware encoding for speed.",
    "➤ Frame verification ensures output quality matches input.",
    "✦ Automatic backup system prevents data loss during conversion.",
    "◆ Multi-threaded processing maximizes your CPU efficiency.",
    "◈ Bitrate optimization reduces file size while preserving quality.",
    "➤ Metadata preservation: Your file timestamps remain unchanged.",
    "✦ Open source transparency - every line of code is auditable.",
    "◆ Atomic file operations prevent corruption from interruptions.",
    "◈ Smart codec detection automatically selects best encoder."
]
INFO_TICKER_ASCII = [
    "Targeting 30 FPS for optimal timeline stability.",
    "Safety Bridge ensures zero-loss atomic file swaps.",
    "Mnemosyne preserves file dates to keep your timeline intact.",
    "Processing is 100% local. No cloud, no tracking.",
    "GPU acceleration detected - using hardware encoding for speed.",
    "Frame verification ensures output quality matches input.",
    "Automatic backup system prevents data loss during conversion.",
    "Multi-threaded processing maximizes your CPU efficiency.",
    "Bitrate optimization reduces file size while preserving quality.",
    "Metadata preservation: Your file timestamps remain unchanged.",
    "Open source transparency - every line of code is auditable.",
    "Atomic file operations prevent corruption from interruptions.",
    "Smart codec detection automatically selects best encoder."
]

def supports_unicode_output(stream=None):
    stream = stream or getattr(sys, "stdout", None)
    if stream is None:
        return False
    encoding = getattr(stream, "encoding", None) or "utf-8"
    try:
        UNICODE_OUTPUT_SAMPLE.encode(encoding)
        return True
    except Exception:
        return False

def get_box_chars():
    return BOX_UNICODE if supports_unicode_output() else BOX_ASCII

def get_ticker_messages():
    return INFO_TICKER_UNICODE if supports_unicode_output() else INFO_TICKER_ASCII

def get_progress_glyphs():
    if supports_unicode_output():
        return ('\u2588', '\u2591', '\u2713', '\u27a4', '\u2514\u2500')
    return ('#', '-', 'OK', '>', '|-')

def get_warning_symbol():
    return '\u26a0' if supports_unicode_output() else 'WARNING'

def strip_ansi(text):
    return ANSI_ESCAPE_RE.sub("", str(text or ""))

def ellipsize_text(text, max_width):
    text = str(text or "")
    max_width = max(1, int(max_width))
    if len(text) <= max_width:
        return text
    if max_width <= 3:
        return text[:max_width]
    return text[: max_width - 3] + "..."

def get_terminal_dimensions():
    try:
        size = shutil.get_terminal_size(fallback=(80, 24))
        return max(40, int(size.columns)), max(10, int(size.lines))
    except Exception:
        return 80, 24

def supports_live_dashboard(stream=None):
    stream = stream or getattr(sys, "stdout", None)
    if stream is None:
        return False
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except Exception:
        return False

def emit_compact_dashboard(snapshot, completed, total):
    now = time.time()
    with DISPLAY_LOCK:
        if completed < total and now - DISPLAY_STATE["last_compact_at"] < COMPACT_DASHBOARD_INTERVAL:
            return
        if (
            DISPLAY_STATE["mode"] == "compact"
            and DISPLAY_STATE["last_compact_snapshot"] == snapshot
            and completed >= total
        ):
            return
        if DISPLAY_STATE["mode"] == "live":
            sys.stdout.write("\n")
        sys.stdout.write(snapshot + "\n")
        sys.stdout.flush()
        DISPLAY_STATE["mode"] = "compact"
        DISPLAY_STATE["last_compact_at"] = now
        DISPLAY_STATE["last_compact_snapshot"] = snapshot

def render_live_dashboard(frame):
    with DISPLAY_LOCK:
        prefix = "\033[2J\033[H" if DISPLAY_STATE["mode"] != "live" else "\033[H"
        sys.stdout.write(prefix + frame + "\033[J")
        sys.stdout.flush()
        DISPLAY_STATE["mode"] = "live"
        DISPLAY_STATE["last_compact_snapshot"] = ""

def format_recent_output(lines, max_lines=6):
    tail = [line.strip() for line in lines if line and line.strip()]
    if not tail:
        return "n/a"
    return " | ".join(tail[-max_lines:])

def get_runtime_dir(create=True):
    runtime_dir = get_launcher_dir() / RUNTIME_DIR_NAME
    if create:
        runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir

def get_runtime_work_dir(name, create=True):
    work_dir = get_runtime_dir(create=create) / name
    if create:
        work_dir.mkdir(parents=True, exist_ok=True)
    return work_dir

def setup_logging(debug=False, desktop_mode=False):
    if desktop_mode:
        desktop = Path.home() / "Desktop"
        if not desktop.exists(): desktop = Path.home()
        log_file = desktop / "Mnemosyne_Log.txt"
    else:
        log_file = get_runtime_dir() / "Mnemosyne_Log.txt"

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    logger.handlers.clear()
    fh = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=2, encoding='utf-8')
    fh.setFormatter(fmt); fh.setLevel(logging.DEBUG); logger.addHandler(fh)
    return log_file

def enable_ansi():
    if not IS_WINDOWS: return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        m = ctypes.wintypes.DWORD()
        kernel32.GetConsoleMode(h, ctypes.byref(m))
        kernel32.SetConsoleMode(h, m.value | 0x0004)
    except (OSError, AttributeError, ValueError, TypeError) as e:
        logging.debug(f"Could not initialize Windows VT100 console mode: {e}")

def reset_cursor():
    # Home cursor and clear everything below it to prevent ghosting
    sys.stdout.write("\033[H")
    sys.stdout.flush()

def hide_cursor(): sys.stdout.write("\033[?25l"); sys.stdout.flush()
def show_cursor(): sys.stdout.write("\033[?25h"); sys.stdout.flush()

def clear_screen(): os.system('cls' if IS_WINDOWS else 'clear')

_MOUNT_CACHE = {"linux": None, "darwin": None}
_MOUNT_CACHE_LOCK = threading.Lock()


def _read_linux_mounts():
    """Parse /proc/mounts once per process into a {mount_point: device_name} map.

    Returns an empty dict if /proc/mounts is unreadable. The result is cached
    on the module because reading the file in tight loops (one call per file
    during folder scan) would otherwise be wasteful. Access is locked because
    the folder scan and the parallel worker pool can both call this on
    different threads — without locking, a half-populated dict could be
    returned to a reader while another thread is still writing.
    """
    cached = _MOUNT_CACHE["linux"]
    if cached is not None:
        return cached
    with _MOUNT_CACHE_LOCK:
        cached = _MOUNT_CACHE["linux"]
        if cached is not None:
            return cached
        mapping: Dict[str, str] = {}
        try:
            with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    parts = raw_line.split()
                    if len(parts) < 3:
                        continue
                    device, mount_point = parts[0], parts[1]
                    if not mount_point.startswith("/"):
                        continue
                    if not device.startswith("/dev/"):
                        continue
                    resolved_mount = os.path.realpath(mount_point)
                    mapping[resolved_mount] = device
        except OSError as exc:
            logging.debug(f"Could not read /proc/mounts: {exc}")
        _MOUNT_CACHE["linux"] = mapping
        return mapping


def _linux_device_is_removable(device_name: str) -> bool:
    """Return True if the block device backing `device_name` is removable.

    Walks /sys/class/block/<dev>/removable — falls back to the parent device
    for partitions. Linux partition naming has two flavours:
      - legacy: /dev/sda1, /dev/sdb2  -> parent is /dev/sda, /dev/sdb
      - modern: /dev/nvme0n1p1, /dev/mmcblk0p2 -> parent has trailing "p"
    Returns False on any error so that the default behaviour (assume fixed)
    is preserved when sysfs is unavailable.
    """
    if not device_name.startswith("/dev/"):
        return False
    dev_name = device_name[len("/dev/"):].rstrip("/")
    if not dev_name:
        return False
    candidates = [f"/sys/class/block/{dev_name}/removable"]
    # Modern "p"-prefixed partitions: nvme0n1p1 -> nvme0n1, mmcblk0p2 -> mmcblk0.
    p_idx = dev_name.rfind("p")
    if p_idx > 0:
        base = dev_name[:p_idx]
        if base:
            candidates.append(f"/sys/class/block/{base}/removable")
    # Legacy numeric partitions: sdb1 -> sdb, sda12 -> sda.
    num_idx = len(dev_name)
    while num_idx > 0 and dev_name[num_idx - 1].isdigit():
        num_idx -= 1
    if 0 < num_idx < len(dev_name):
        base = dev_name[:num_idx]
        if base:
            candidates.append(f"/sys/class/block/{base}/removable")
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                value = fh.read().strip()
            if value == "1":
                return True
            if value == "0":
                return False
        except OSError:
            continue
    return False


def _read_darwin_volumes():
    """Collect mount points under /Volumes on macOS.

    These are the user-visible USB/external/network mounts that macOS
    surfaces — and the most common removable-media case the launcher needs
    to detect.
    """
    if _MOUNT_CACHE["darwin"] is not None:
        return _MOUNT_CACHE["darwin"]
    with _MOUNT_CACHE_LOCK:
        cached = _MOUNT_CACHE["darwin"]
        if cached is not None:
            return cached
        volumes_root = Path("/Volumes")
        mounts: List[str] = []
        if volumes_root.is_dir():
            for entry in volumes_root.iterdir():
                try:
                    mounts.append(os.path.realpath(str(entry)))
                except OSError:
                    continue
        _MOUNT_CACHE["darwin"] = mounts
        return mounts


def get_drive_type(path):
    if IS_WINDOWS:
        try:
            import ctypes
            root = os.path.splitdrive(path)[0] + "\\"
            return ctypes.windll.kernel32.GetDriveTypeW(root)
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logging.debug(f"Could not determine drive type for {path}: {e}")
            return DRIVE_FIXED
    if platform.system() == "Linux":
        try:
            abs_path = os.path.realpath(path)
        except OSError:
            return DRIVE_FIXED
        mounts = _read_linux_mounts()
        # Find the longest mount-point prefix that contains the path.
        best_match = ""
        best_device = ""
        for mount_point, device in mounts.items():
            if abs_path == mount_point or abs_path.startswith(mount_point + os.sep):
                if len(mount_point) > len(best_match):
                    best_match = mount_point
                    best_device = device
        if best_device and _linux_device_is_removable(best_device):
            return DRIVE_REMOVABLE
        return DRIVE_FIXED
    if platform.system() == "Darwin":
        try:
            abs_path = os.path.realpath(path)
        except OSError:
            return DRIVE_FIXED
        for mount_point in _read_darwin_volumes():
            if abs_path == mount_point or abs_path.startswith(mount_point + os.sep):
                return DRIVE_REMOVABLE
        return DRIVE_FIXED
    return DRIVE_FIXED

def get_local_config_file():
    return Path.cwd() / "config.json"

def get_config_files():
    return [APP_CONFIG_FILE]

def has_saved_config():
    return any(cfg.exists() for cfg in get_config_files())

def default_ffmpeg_state():
    return {
        "preferred_auto_download": DEFAULT_CONFIG["auto_download_ffmpeg"],
        "preferred_storage_mode": "",
        "preferred_custom_path": "",
        "managed_installs": [],
    }

def normalize_profile_id(value):
    profile_id = str(value or DEFAULT_PROFILE_ID).strip().lower()
    if profile_id not in PROFILE_PRESETS:
        return DEFAULT_PROFILE_ID
    return profile_id

def normalize_storage_mode(value):
    storage_mode = str(value or "").strip().lower()
    return storage_mode if storage_mode in MANAGED_FFMPEG_STORAGE_MODES else ""

def normalize_saved_config(raw_config=None):
    raw_config = dict(raw_config or {})
    config = DEFAULT_CONFIG.copy()
    config.update(raw_config)
    config["profile_id"] = normalize_profile_id(config.get("profile_id"))
    for key, value in PROFILE_PRESETS[config["profile_id"]].items():
        if key in PROFILE_KEYS:
            config[key] = value
    if "profile_id" not in raw_config:
        for key in PROFILE_KEYS:
            if key in raw_config:
                config[key] = raw_config[key]
    try:
        config["max_workers"] = normalize_worker_count(config.get("max_workers", DEFAULT_CONFIG["max_workers"]))
    except ValueError:
        config["max_workers"] = DEFAULT_CONFIG["max_workers"]
    try:
        config["target_height"] = max(1, int(config.get("target_height", DEFAULT_CONFIG["target_height"])))
    except (TypeError, ValueError):
        config["target_height"] = DEFAULT_CONFIG["target_height"]
    try:
        config["target_fps"] = max(1, int(config.get("target_fps", DEFAULT_CONFIG["target_fps"])))
    except (TypeError, ValueError):
        config["target_fps"] = DEFAULT_CONFIG["target_fps"]
    config["system_ffmpeg_policy"] = normalize_system_ffmpeg_policy(
        config.get("system_ffmpeg_policy", DEFAULT_CONFIG["system_ffmpeg_policy"])
    )
    config["recursive"] = bool(config.get("recursive", DEFAULT_CONFIG["recursive"]))
    config["verify_frames"] = bool(config.get("verify_frames", DEFAULT_CONFIG["verify_frames"]))
    config["auto_download_ffmpeg"] = bool(config.get("auto_download_ffmpeg", DEFAULT_CONFIG["auto_download_ffmpeg"]))
    config["x264_preset"] = str(config.get("x264_preset", DEFAULT_CONFIG["x264_preset"]) or DEFAULT_CONFIG["x264_preset"])
    try:
        config["ffmpeg_threads"] = max(0, int(config.get("ffmpeg_threads", DEFAULT_CONFIG["ffmpeg_threads"])))
    except (TypeError, ValueError):
        config["ffmpeg_threads"] = DEFAULT_CONFIG["ffmpeg_threads"]
    config["desktop_log"] = bool(config.get("desktop_log", DEFAULT_CONFIG["desktop_log"]))
    config["auto_cleanup"] = bool(config.get("auto_cleanup", DEFAULT_CONFIG["auto_cleanup"]))
    config["show_drive_warnings"] = bool(config.get("show_drive_warnings", DEFAULT_CONFIG["show_drive_warnings"]))
    config["preserve_metadata"] = bool(config.get("preserve_metadata", DEFAULT_CONFIG["preserve_metadata"]))
    config["sort"] = str(config.get("sort", DEFAULT_CONFIG["sort"]) or DEFAULT_CONFIG["sort"])
    if config["sort"] not in {"name_az", "name_za", "size_desc", "size_asc"}:
        config["sort"] = DEFAULT_CONFIG["sort"]
    return config

def load_json_file(path, fallback):
    path = Path(path)
    if not path.exists():
        return json.loads(json.dumps(fallback))
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        logging.warning(f"Could not load JSON from {path}: {exc}")
        return json.loads(json.dumps(fallback))

def load_ffmpeg_state():
    state_file = APP_DATA / 'ffmpeg_state.json'
    raw_state = load_json_file(state_file, default_ffmpeg_state())
    state = default_ffmpeg_state()
    state["preferred_auto_download"] = bool(raw_state.get("preferred_auto_download", DEFAULT_CONFIG["auto_download_ffmpeg"]))
    state["preferred_storage_mode"] = normalize_storage_mode(raw_state.get("preferred_storage_mode"))
    state["preferred_custom_path"] = str(raw_state.get("preferred_custom_path") or "").strip()
    managed_installs = []
    for entry in raw_state.get("managed_installs", []):
        if not isinstance(entry, dict):
            continue
        install_path = str(entry.get("install_path") or "").strip()
        if not install_path:
            continue
        storage_mode = normalize_storage_mode(entry.get("storage_mode"))
        if not storage_mode:
            continue
        managed_installs.append({
            "install_path": install_path,
            "storage_mode": storage_mode,
            "source_identity": str(entry.get("source_identity") or ""),
            "created_at": int(entry.get("created_at") or 0),
            "last_used_at": int(entry.get("last_used_at") or 0),
            "verification_status": str(entry.get("verification_status") or "verified"),
            "last_validation_error": str(entry.get("last_validation_error") or ""),
        })
    state["managed_installs"] = managed_installs
    accepted = []
    for entry in raw_state.get("accepted_unverified", []):
        if not isinstance(entry, dict):
            continue
        accepted.append({
            "source_url": str(entry.get("source_url") or ""),
            "digest": str(entry.get("digest") or "").lower(),
            "remembered_at": int(entry.get("remembered_at") or 0),
        })
    state["accepted_unverified"] = accepted
    return state

def save_ffmpeg_state(state):
    try:
        normalized = load_ffmpeg_state()
        normalized.update({
            "preferred_storage_mode": normalize_storage_mode(state.get("preferred_storage_mode")),
            "preferred_custom_path": str(state.get("preferred_custom_path") or "").strip(),
            "managed_installs": state.get("managed_installs", []),
            "accepted_unverified": state.get("accepted_unverified", []),
        })
        APP_DATA.mkdir(parents=True, exist_ok=True)
        state_file = APP_DATA / 'ffmpeg_state.json'
        with open(state_file, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, ensure_ascii=False)
        return True
    except OSError as exc:
        logging.error(f"Failed to save FFmpeg state: {exc}")
        return False


def is_source_previously_accepted(source_meta):
    """Check ffmpeg_state for previously remembered unverified sources that match this source_meta.

    Matching uses source URL or a computed digest if present.
    """
    try:
        ffmpeg_state = load_ffmpeg_state()
        accepted = ffmpeg_state.get("accepted_unverified", []) or []
        source_url = str(source_meta.get("url") or "")
        source_digest = str(source_meta.get("digest") or "").lower()
        for entry in accepted:
            if entry.get("source_url") and entry.get("source_url") == source_url:
                return True
            if entry.get("digest") and source_digest and entry.get("digest") == source_digest:
                return True
        return False
    except OSError:
        return False


def record_accepted_unverified_source(source_meta):
    """Persist a remembered acceptance of an unverified source into ffmpeg_state.

    Stores: source_url, digest, remembered_at
    """
    try:
        ffmpeg_state = load_ffmpeg_state()
        accepted = ffmpeg_state.get("accepted_unverified", []) or []
        source_url = str(source_meta.get("url") or "")
        source_digest = str(source_meta.get("digest") or "").lower()
        entry = {"source_url": source_url, "digest": source_digest, "remembered_at": int(time.time())}
        for existing in accepted:
            if existing.get("source_url") == entry["source_url"] or (entry["digest"] and existing.get("digest") == entry["digest"]):
                return True
        accepted.append(entry)
        ffmpeg_state["accepted_unverified"] = accepted
        return save_ffmpeg_state(ffmpeg_state)
    except OSError as exc:
        logging.error(f"Failed to record accepted unverified source: {exc}")
        return False

def get_script_path():
    script_file = globals().get("__file__")
    if not script_file:
        return None
    script_text = str(script_file).strip()
    if not script_text or (script_text.startswith("<") and script_text.endswith(">")):
        return None
    try:
        return Path(script_text).resolve()
    except OSError:
        return Path(script_text)

def get_script_dir():
    script_path = get_script_path()
    if script_path is not None:
        try:
            return script_path.parent
        except OSError:
            pass
    return Path.cwd()

def is_embedded_wrapper_runtime():
    script_path = get_script_path()
    if script_path is None:
        return True
    try:
        temp_dir = Path(tempfile.gettempdir()).resolve()
    except OSError:
        temp_dir = None
    if script_path.name.startswith("mnemosyne_runtime_"):
        return temp_dir is None or script_path.parent == temp_dir
    return False

def get_launcher_dir():
    raw_path = os.environ.get(LAUNCHER_DIR_ENV, "").strip()
    if raw_path and is_embedded_wrapper_runtime():
        try:
            launcher_dir = Path(raw_path).resolve()
            if launcher_dir.exists():
                return launcher_dir
        except OSError:
            pass
    return get_script_dir()

def get_managed_ffmpeg_binary_names():
    return ["ffmpeg.exe", "ffprobe.exe"] if IS_WINDOWS else ["ffmpeg", "ffprobe"]

def get_ffmpeg_marker_path(install_dir):
    return Path(install_dir) / MANAGED_FFMPEG_MARKER

def get_session_ffmpeg_dir():
    return get_runtime_work_dir("bin")

def get_preferred_parent_for_write_check(path):
    path = Path(path)
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            break
        probe = probe.parent
    return probe

def is_directory_writable(path):
    probe = get_preferred_parent_for_write_check(path)
    try:
        return os.access(str(probe), os.W_OK)
    except OSError:
        return False

def get_recommended_ffmpeg_storage_mode():
    return "session"

def resolve_ffmpeg_install_dir(storage_mode, custom_path=""):
    storage_mode = normalize_storage_mode(storage_mode) or get_recommended_ffmpeg_storage_mode()
    if storage_mode == "portable":
        return get_launcher_dir() / "bin"
    if storage_mode == "session":
        return get_session_ffmpeg_dir()
    if storage_mode == "custom":
        custom_path = str(custom_path or "").strip()
        if not custom_path:
            raise ValueError("Custom FFmpeg storage requires a destination path.")
        return Path(custom_path).expanduser()
    return BIN_DIR

def describe_storage_mode(storage_mode):
    labels = {
        "appdata": "AppData",
        "portable": "Portable",
        "session": "Runtime Folder",
        "custom": "Custom Path",
    }
    storage_mode = normalize_storage_mode(storage_mode)
    return labels.get(storage_mode, "Unknown")

def format_bytes(size):
    size = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024

def has_enough_space(path, required_bytes):
    try:
        usage = shutil.disk_usage(str(get_preferred_parent_for_write_check(path)))
        return usage.free >= required_bytes, usage.free
    except Exception as e:
        logging.error(f"Disk space check failed for {path}: {e}")
        return False, 0

def warn_if_space_is_low(path, required_bytes, label):
    ok, free = has_enough_space(path, required_bytes)
    if ok:
        return True
    print(f" {C.ERROR}[!] Not enough free space for {label}.{C.RESET}")
    print(f"     Needed: {format_bytes(required_bytes)} | Free: {format_bytes(free)}")
    return False

def write_managed_ffmpeg_marker(install_dir, state_entry):
    marker_path = get_ffmpeg_marker_path(install_dir)
    payload = {
        "app": APP_NAME,
        "install_path": str(Path(install_dir)),
        "storage_mode": state_entry.get("storage_mode", ""),
        "source_identity": state_entry.get("source_identity", ""),
        "created_at": int(state_entry.get("created_at") or int(time.time())),
        "verification_status": state_entry.get("verification_status", "verified"),
    }
    with open(marker_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

def upsert_managed_ffmpeg_install(install_dir, storage_mode, source_identity, ffmpeg_state=None, verification_status="verified"):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    install_dir = str(Path(install_dir).resolve())
    now = int(time.time())
    retained = [entry for entry in ffmpeg_state.get("managed_installs", []) if entry.get("install_path") != install_dir]
    state_entry = {
        "install_path": install_dir,
        "storage_mode": normalize_storage_mode(storage_mode),
        "source_identity": str(source_identity or ""),
        "created_at": now,
        "last_used_at": now,
        "verification_status": str(verification_status or "verified"),
        "last_validation_error": "",
    }
    retained.append(state_entry)
    ffmpeg_state["managed_installs"] = retained
    ffmpeg_state["preferred_storage_mode"] = state_entry["storage_mode"]
    ffmpeg_state["preferred_custom_path"] = install_dir if state_entry["storage_mode"] == "custom" else ""
    try:
        Path(install_dir).mkdir(parents=True, exist_ok=True)
        write_managed_ffmpeg_marker(install_dir, state_entry)
    except OSError as exc:
        logging.warning(f"Could not write FFmpeg marker into {install_dir}: {exc}")
    save_ffmpeg_state(ffmpeg_state)
    return state_entry

def prune_missing_ffmpeg_state_entries(ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    changed = False
    retained = []
    binaries = get_managed_ffmpeg_binary_names()
    for entry in ffmpeg_state.get("managed_installs", []):
        install_dir = Path(entry.get("install_path", ""))
        if not install_dir.exists():
            changed = True
            continue
        if not all((install_dir / binary_name).exists() for binary_name in binaries):
            changed = True
            continue
        retained.append(entry)
    if changed:
        ffmpeg_state["managed_installs"] = retained
        save_ffmpeg_state(ffmpeg_state)
    return ffmpeg_state

def touch_managed_ffmpeg_install(install_dir, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    install_dir = str(Path(install_dir).resolve())
    changed = False
    for entry in ffmpeg_state.get("managed_installs", []):
        if entry.get("install_path") == install_dir:
            entry["last_used_at"] = int(time.time())
            changed = True
            break
    if changed:
        save_ffmpeg_state(ffmpeg_state)

def remove_managed_ffmpeg_install(entry, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    install_dir = Path(entry.get("install_path", ""))
    removed_any = False
    for name in tuple(get_managed_ffmpeg_binary_names()) + (MANAGED_FFMPEG_MARKER,):
        target = install_dir / name
        if not target.exists():
            continue
        try:
            target.unlink()
            removed_any = True
        except OSError as exc:
            logging.warning(f"Could not remove managed FFmpeg artifact {target}: {exc}")
    try:
        if install_dir.exists() and not any(install_dir.iterdir()):
            install_dir.rmdir()
    except OSError:
        pass
    retained = [item for item in ffmpeg_state.get("managed_installs", []) if item.get("install_path") != str(install_dir.resolve())]
    if len(retained) != len(ffmpeg_state.get("managed_installs", [])):
        ffmpeg_state["managed_installs"] = retained
        save_ffmpeg_state(ffmpeg_state)
    return removed_any

def get_stale_managed_ffmpeg_installs(ffmpeg_state=None, inactivity_days=STALE_FFMPEG_DAYS):
    ffmpeg_state = prune_missing_ffmpeg_state_entries(ffmpeg_state)
    cutoff = int(time.time()) - int(inactivity_days * 86400)
    stale = []
    for entry in ffmpeg_state.get("managed_installs", []):
        last_used_at = int(entry.get("last_used_at") or entry.get("created_at") or 0)
        if last_used_at and last_used_at <= cutoff:
            stale.append(entry)
    return stale

def prompt_stale_ffmpeg_cleanup(ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    stale = get_stale_managed_ffmpeg_installs(ffmpeg_state)
    if not stale or not supports_interactive_input():
        return
    print(f" {C.WARNING}[FFMPEG] Found {len(stale)} managed FFmpeg install(s) unused for {STALE_FFMPEG_DAYS}+ days.{C.RESET}")
    for entry in stale:
        install_dir = Path(entry["install_path"])
        age_days = max(1, int((time.time() - (entry.get("last_used_at") or entry.get("created_at") or int(time.time()))) / 86400))
        print(f"    - {describe_storage_mode(entry.get('storage_mode'))}: {install_dir} ({age_days} day(s) idle)")
    answer = safe_input(f" {C.PRIMARY}>> Clean up these managed FFmpeg binaries now? (Y/N): {C.RESET}", "n").strip().lower()
    if answer not in {"y", "yes"}:
        return
    removed = 0
    for entry in stale:
        if remove_managed_ffmpeg_install(entry, ffmpeg_state):
            removed += 1
    if removed:
        print(f" {C.SUCCESS}[+] Cleaned up {removed} managed FFmpeg install(s).{C.RESET}")

def build_ffmpeg_preferences(ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    storage_mode = normalize_storage_mode(ffmpeg_state.get("preferred_storage_mode")) or get_recommended_ffmpeg_storage_mode()
    return {
        "auto_download": bool(ffmpeg_state.get("preferred_auto_download", DEFAULT_CONFIG["auto_download_ffmpeg"])),
        "storage_mode": storage_mode,
        "custom_install_path": str(ffmpeg_state.get("preferred_custom_path") or ""),
    }

def persist_ffmpeg_preferences(ffmpeg_preferences, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    ffmpeg_state["preferred_auto_download"] = bool(ffmpeg_preferences.get("auto_download"))
    ffmpeg_state["preferred_storage_mode"] = normalize_storage_mode(ffmpeg_preferences.get("storage_mode"))
    ffmpeg_state["preferred_custom_path"] = (
        str(ffmpeg_preferences.get("custom_install_path") or "").strip()
        if ffmpeg_state["preferred_storage_mode"] == "custom"
        else ""
    )
    return save_ffmpeg_state(ffmpeg_state)

def normalize_system_ffmpeg_policy(value):
    policy = str(value or DEFAULT_CONFIG["system_ffmpeg_policy"]).strip().lower()
    if policy not in VALID_SYSTEM_FFMPEG_POLICIES:
        return DEFAULT_CONFIG["system_ffmpeg_policy"]
    return policy

def supports_interactive_input(stream=None):
    stream = stream or getattr(sys, "stdin", None)
    if stream is None:
        return False
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False

def safe_input(prompt, default=""):
    try:
        return input(prompt)
    except (EOFError, OSError) as exc:
        logging.debug(f"Input unavailable; using default response: {exc}")
        return default

def _iter_unique_base_dirs(*paths):
    seen = set()
    for raw_path in paths:
        if raw_path is None:
            continue
        try:
            path = Path(raw_path).resolve()
        except OSError:
            path = Path(raw_path)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        yield path

def workspace_key(path):
    path = Path(path)
    try:
        return str(path.resolve())
    except OSError:
        return str(path)

def is_temp_workspace_control_file(path):
    return Path(path).name in {TEMP_WORKSPACE_MARKER, TEMP_WORKSPACE_LOCK}

def is_path_in_temp_workspace(path):
    return TEMP_WORKSPACE_NAME in Path(path).parts

def try_acquire_workspace_lock(lock_path):
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, 'a+b')
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"1")
            handle.flush()
        handle.seek(0)
        if IS_WINDOWS:
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle
    except OSError:
        try:
            handle.close()
        except OSError:
            pass
        return None

def release_workspace_lock(handle):
    if handle is None:
        return
    try:
        if IS_WINDOWS:
            import msvcrt
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        handle.close()
    except OSError:
        pass

def current_session_workspace(parent_dir):
    return Path(parent_dir) / TEMP_WORKSPACE_NAME / SESSION_ID

def release_managed_workspace(workspace):
    with TEMP_WORKSPACE_INIT_LOCK:
        handle = TEMP_WORKSPACE_LOCKS.pop(workspace_key(workspace), None)
    release_workspace_lock(handle)

def get_temp_workspace(parent_dir):
    workspace = current_session_workspace(parent_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    key = workspace_key(workspace)
    with TEMP_WORKSPACE_INIT_LOCK:
        if key not in TEMP_WORKSPACE_LOCKS:
            lock_handle = try_acquire_workspace_lock(workspace / TEMP_WORKSPACE_LOCK)
            if lock_handle is None:
                raise RuntimeError(f"Could not acquire temporary workspace lock for {workspace}")
            TEMP_WORKSPACE_LOCKS[key] = lock_handle
        marker = workspace / TEMP_WORKSPACE_MARKER
        if not marker.exists():
            marker.write_text(json.dumps({
                "app": APP_NAME,
                "session_id": SESSION_ID,
                "pid": os.getpid(),
                "created_at": int(time.time()),
            }, indent=2, ensure_ascii=False), encoding='utf-8')
    return workspace

def iter_temp_workspaces(base_dir, recursive=False):
    base_dir = Path(base_dir)
    if recursive:
        candidates = base_dir.rglob(TEMP_WORKSPACE_MARKER)
        seen = set()
        for marker in candidates:
            workspace = marker.parent
            if workspace.parent.name != TEMP_WORKSPACE_NAME:
                continue
            key = workspace_key(workspace)
            if key in seen:
                continue
            seen.add(key)
            yield workspace
        return
    workspace_root = base_dir / TEMP_WORKSPACE_NAME
    if not workspace_root.exists():
        return
    for marker in workspace_root.glob(f"*/{TEMP_WORKSPACE_MARKER}"):
        workspace = marker.parent
        if workspace.parent == workspace_root:
            yield workspace

def is_temp_workspace(path):
    path = Path(path)
    return path.parent.name == TEMP_WORKSPACE_NAME and (path / TEMP_WORKSPACE_MARKER).exists()

def iter_video_backups(base_dir, recursive=False):
    base_dir = Path(base_dir)
    pattern = base_dir.rglob("*") if recursive else base_dir.glob("*")
    for path in pattern:
        if not path.is_file():
            continue
        suffixes = [suffix.lower() for suffix in path.suffixes]
        if len(suffixes) < 2 or suffixes[-1] != ".bak":
            continue
        if suffixes[-2] in VIDEO_EXTENSIONS:
            yield path

def get_backup_target_path(path):
    path = Path(path)
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes and suffixes[-1] == ".bak":
        return path.with_suffix('')
    return path

def get_transaction_journal_path(path):
    source_path = get_backup_target_path(path)
    return source_path.with_name(source_path.name + TRANSACTION_JOURNAL_SUFFIX)

def load_transaction_journal(path):
    journal_path = get_transaction_journal_path(path)
    if not journal_path.exists():
        return None
    try:
        with open(journal_path, 'r', encoding='utf-8') as journal_file:
            return json.load(journal_file)
    except OSError as exc:
        logging.warning(f"Could not read transaction journal {journal_path}: {exc}")
        return {
            "stage": "journal_unreadable",
            "last_error": str(exc),
            "journal_path": str(journal_path),
        }

def write_transaction_journal(path, **updates):
    source_path = get_backup_target_path(path)
    journal_path = get_transaction_journal_path(source_path)
    payload = {
        "app": APP_NAME,
        "version": VERSION,
        "session_id": SESSION_ID,
        "source_path": str(source_path),
        "updated_at": int(time.time()),
    }
    existing = load_transaction_journal(source_path)
    if existing:
        payload.update(existing)
    payload.update(updates)
    payload["source_path"] = str(source_path)
    payload["updated_at"] = int(time.time())
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        with open(journal_path, 'w', encoding='utf-8') as journal_file:
            json.dump(payload, journal_file, indent=2, ensure_ascii=False)
        return journal_path
    except OSError as exc:
        logging.warning(f"Could not write transaction journal {journal_path}: {exc}")
        return None

def clear_transaction_journal(path):
    journal_path = get_transaction_journal_path(path)
    try:
        if journal_path.exists():
            journal_path.unlink()
    except OSError as exc:
        logging.warning(f"Could not remove transaction journal {journal_path}: {exc}")

def build_conflict_preserve_path(path, label):
    path = Path(path)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    stem = path.stem or path.name
    candidate = path.with_name(f"{stem}.{label}-{timestamp}{path.suffix}")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{stem}.{label}-{timestamp}-{counter}{path.suffix}")
        counter += 1
    return candidate

def summarize_transaction_journal(journal):
    if not journal:
        return ""
    stage = str(journal.get("stage") or "unknown").strip()
    verification = journal.get("verification") or {}
    verification_bits = []
    if "metadata_ok" in verification:
        verification_bits.append("metadata=ok" if verification.get("metadata_ok") else "metadata=fail")
    if "decode_ok" in verification:
        verification_bits.append("decode=ok" if verification.get("decode_ok") else "decode=fail")
    frame_mode = verification.get("frame_check")
    if frame_mode:
        verification_bits.append(f"frames={frame_mode}")
    summary = f"stage={stage}"
    if verification_bits:
        summary += " | " + ", ".join(verification_bits)
    if journal.get("last_error"):
        summary += f" | error={journal['last_error']}"
    return summary

def restore_backup_with_mode(backup_path, mode):
    backup_path = Path(backup_path)
    source_path = get_backup_target_path(backup_path)
    preserved_path = None
    delete_preserved_after_restore = False

    if source_path.exists():
        if mode == "restore":
            logging.error(f"Restore conflict for {backup_path}: current file exists at {source_path}")
            return False, None
        label = "rescued-current" if mode == "restore_and_preserve_current" else "overwrite-hold"
        preserved_path = build_conflict_preserve_path(source_path, label)
        try:
            source_path.rename(preserved_path)
        except OSError as exc:
            logging.error(f"Could not preserve current file {source_path} before restore: {exc}")
            return False, None
        delete_preserved_after_restore = mode == "overwrite_current"

    try:
        backup_path.rename(source_path)
    except OSError as exc:
        logging.error(f"Failed to restore backup {backup_path} -> {source_path}: {exc}")
        if preserved_path is not None and preserved_path.exists() and not source_path.exists():
            try:
                preserved_path.rename(source_path)
            except Exception as rollback_exc:
                logging.critical(
                    f"Could not roll back preserved current file {preserved_path} -> {source_path}: {rollback_exc}"
                )
        return False, preserved_path

    clear_transaction_journal(source_path)

    if delete_preserved_after_restore and preserved_path is not None and preserved_path.exists():
        try:
            preserved_path.unlink()
        except OSError as exc:
            logging.warning(f"Could not remove overwrite hold file {preserved_path}: {exc}")
    return True, preserved_path

def iter_video_files(base_dir, recursive=False):
    base_dir = Path(base_dir)
    pattern = base_dir.rglob("*") if recursive else base_dir.glob("*")
    for path in pattern:
        if not path.is_file():
            continue
        if is_path_in_temp_workspace(path):
            continue
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path

def iter_matching_paths(base_dir, pattern, recursive=False):
    base_dir = Path(base_dir)
    return base_dir.rglob(pattern) if recursive else base_dir.glob(pattern)

def iter_unique_target_dirs(target_dirs=None, work_dir=None):
    if target_dirs is None:
        target_dirs = [Path(work_dir) if work_dir else Path.cwd()]
    seen = set()
    for raw_dir in target_dirs:
        try:
            resolved = Path(raw_dir).resolve()
        except OSError:
            resolved = Path(raw_dir)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        yield resolved

def _cleanup_temp_files_single(work_dir, recursive=False, include_current_session=False):
    work_dir = Path(work_dir)
    count = 0
    workspace_roots = set()
    for workspace in iter_temp_workspaces(work_dir, recursive=recursive):
        workspace_roots.add(workspace.parent)
        if workspace.name == SESSION_ID:
            if not include_current_session:
                continue
            release_managed_workspace(workspace)
        else:
            probe_lock = try_acquire_workspace_lock(workspace / TEMP_WORKSPACE_LOCK)
            if probe_lock is None:
                continue
            release_workspace_lock(probe_lock)
        for entry in workspace.iterdir():
            if is_temp_workspace_control_file(entry):
                continue
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                else:
                    entry.unlink()
                count += 1
            except OSError:
                pass
        try:
            for control_name in (TEMP_WORKSPACE_MARKER, TEMP_WORKSPACE_LOCK):
                control_file = workspace / control_name
                if control_file.exists():
                    control_file.unlink()
            workspace.rmdir()
        except OSError:
            pass
    for workspace_root in workspace_roots:
        try:
            if workspace_root.exists() and not any(workspace_root.iterdir()):
                workspace_root.rmdir()
        except OSError:
            pass
    return count

def cleanup_temp_files(work_dir=None, recursive=False, include_current_session=False, target_dirs=None):
    total = 0
    for base_dir in iter_unique_target_dirs(target_dirs=target_dirs, work_dir=work_dir):
        total += _cleanup_temp_files_single(base_dir, recursive=recursive, include_current_session=include_current_session)
    return total

def _count_temp_files_single(work_dir, recursive=False):
    work_dir = Path(work_dir)
    count = 0
    for workspace in iter_temp_workspaces(work_dir, recursive=recursive):
        for entry in workspace.iterdir():
            if not is_temp_workspace_control_file(entry):
                count += 1
    return count

def count_temp_files(work_dir=None, recursive=False, target_dirs=None):
    total = 0
    for base_dir in iter_unique_target_dirs(target_dirs=target_dirs, work_dir=work_dir):
        total += _count_temp_files_single(base_dir, recursive=recursive)
    return total

def audit_orphaned_backups(recursive=False, auto_cleanup=True, target_dirs=None):
    target_dirs = list(iter_unique_target_dirs(target_dirs=target_dirs))
    t_count = cleanup_temp_files(recursive=recursive, target_dirs=target_dirs) if auto_cleanup else 0
    remaining_temp_files = count_temp_files(recursive=recursive, target_dirs=target_dirs) if not auto_cleanup else 0
    if t_count > 0: print(f" {C.INFO}[+] Auto-cleaned {t_count} temporary file(s).{C.RESET}")
    baks = []
    seen_baks = set()
    for base_dir in target_dirs:
        for backup_path in iter_video_backups(base_dir, recursive=recursive):
            key = workspace_key(backup_path)
            if key in seen_baks:
                continue
            seen_baks.add(key)
            baks.append(backup_path)
    baks.sort()
    if not baks:
        if remaining_temp_files > 0:
            print(f" {C.INFO}[+] Auto-cleanup is disabled. {remaining_temp_files} temporary file(s) are being preserved.{C.RESET}")
        elif t_count == 0:
            print(f" {C.SUCCESS}[+] HEALTH CHECK: System is clean.{C.RESET}")
        return True
    print(f" {C.WARNING}[!] GLOBAL RESCUE: Found {len(baks)} orphaned backup files.{C.RESET}")
    for b in baks:
        label = b
        for base_dir in target_dirs:
            try:
                label = b.relative_to(base_dir)
                break
            except ValueError:
                continue
        print(f"     {C.MUTED}- {label}{C.RESET}")
        current_file = get_backup_target_path(b)
        if current_file.exists():
            print(f"       {C.WARNING}current file also exists: {current_file.name}{C.RESET}")
        journal_summary = summarize_transaction_journal(load_transaction_journal(b))
        if journal_summary:
            print(f"       {C.INFO}journal: {journal_summary}{C.RESET}")
    if not supports_interactive_input():
        logging.error("Orphaned backup recovery requires interactive input.")
        print(f" {C.ERROR}[!] Non-interactive mode cannot decide whether to restore or purge backups.{C.RESET}")
        return False
    print(f" {C.PRIMARY}[RESCUE] Choose one action for all listed backups:{C.RESET}")
    print(f"    [R] Restore only when target path is empty")
    print(f"    [K] Restore and preserve current file under a timestamped name")
    print(f"    [O] Overwrite current file with backup")
    print(f"    [P] Purge backups permanently")
    print(f"    [S] Skip for now and stop before processing")
    ans = safe_input(f" {C.PRIMARY}>> Choice (R/K/O/P/S): {C.RESET}", "s").strip().lower()
    if ans == 'p':
        print(f"\n {C.ERROR}[!] WARNING: {len(baks)} backup file(s) will be PERMANENTLY deleted!{C.RESET}")
        print(f" {C.WARNING}    This cannot be undone. Type 'PURGE' to confirm:{C.RESET}")
        confirm = safe_input(f" {C.PRIMARY}>> {C.RESET}", "").strip()
        if confirm == 'PURGE':
            success = True
            for b in baks:
                try:
                    b.unlink()
                    clear_transaction_journal(b)
                except Exception as e:
                    logging.warning(f"Could not purge backup {b}: {e}")
                    success = False
            if success:
                print(f" {C.SUCCESS}[+] {len(baks)} backup file(s) permanently deleted.{C.RESET}")
            return success
        else:
            print(f" {C.INFO}[+] Cancelled. Backup files are preserved.{C.RESET}")
            return False
    if ans in {'r', 'k', 'o'}:
        mode_map = {
            'r': "restore",
            'k': "restore_and_preserve_current",
            'o': "overwrite_current",
        }
        success = True
        for b in baks:
            restored, preserved_path = restore_backup_with_mode(b, mode_map[ans])
            if not restored:
                success = False
                continue
            if preserved_path is not None and preserved_path.exists() and ans == 'k':
                print(f" {C.INFO}[+] Preserved current file as {preserved_path.name}{C.RESET}")
        if success:
            print(f" {C.SUCCESS}[+] Backup recovery completed successfully.{C.RESET}")
        else:
            print(f" {C.ERROR}[!] Some backups could not be restored safely. Processing will stop.{C.RESET}")
        return success
    print(f" {C.INFO}[+] Rescue skipped. Resolve backups before processing new files.{C.RESET}")
    return False

def load_config():
    config = DEFAULT_CONFIG.copy()
    for cfg in get_config_files():
        if not cfg.exists():
            continue
        try:
            with open(cfg, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logging.warning(f"Could not load config from {cfg}: {e}")
    return normalize_saved_config(config)

def build_saveable_config(config):
    to_save = {}
    for key in SAVEABLE_CONFIG_KEYS:
        if key in config:
            to_save[key] = config[key]
    return to_save

def save_config(config):
    try:
        to_save = build_saveable_config(config)
        APP_DATA.mkdir(parents=True, exist_ok=True)
        with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=4, ensure_ascii=False)
        return True
    except (OSError, AttributeError, ValueError, TypeError) as e:
        logging.error(f"Failed to save config: {e}")
        return False

def get_profile_label(profile_id):
    profile_id = normalize_profile_id(profile_id)
    return PROFILE_PRESETS[profile_id].get("label") or profile_id

def draw_box_line(text, width=70, color=C.WHITE, align='center'):
    box = get_box_chars()
    if align == 'center': stripped = text.center(width)
    elif align == 'left': stripped = text.ljust(width)
    else: stripped = text.rjust(width)
    print(f" {C.PRIMARY}{box['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{box['v']}{C.RESET}")

def draw_separator(width=70, type='mid'):
    box = get_box_chars()
    if type == 'top': l, r, m = box['tl'], box['tr'], box['h']
    elif type == 'bot': l, r, m = box['bl'], box['br'], box['h']
    else: l, r, m = box['ml'], box['mr'], box['h']
    print(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")

def get_ticker_msg():
    messages = get_ticker_messages()
    idx = int(time.time() / 15) % len(messages)
    return messages[idx]

def draw_logo():
    output = []
    ascii_with_version = ASCII_ART.format(version=VERSION)
    for line in ascii_with_version.strip('\n').split('\n'):
        if line.strip(): output.append(f"{C.PRIMARY} {line}{C.RESET}")
    output.append("")
    return "\n".join(output)

def draw_header(config, codec_name, briefing=None, width=70):
    output = []
    width = max(44, int(width))
    box = get_box_chars()
    l, r, m = box['tl'], box['tr'], box['h']
    output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
    
    def box_line(text, color=C.WHITE, align='center'):
        text = ellipsize_text(text, width)
        visible_len = len(strip_ansi(text))
        pad = max(0, width - visible_len)
        if align == 'center':
            left = pad // 2; right = pad - left
            stripped = ' ' * left + text + ' ' * right
        elif align == 'left':
            stripped = text + ' ' * pad
        else:
            stripped = ' ' * pad + text
        return f" {C.PRIMARY}{box['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{box['v']}{C.RESET}"

    output.append(box_line(f"The Keeper of Digital Memory v{VERSION}", C.BOLD + C.WHITE))
    
    l, r, m = box['ml'], box['mr'], box['h']
    sep = f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}"
    output.append(sep)
    
    if briefing:
        output.append(box_line("MISSION BRIEFING", C.BOLD + C.PRIMARY))
        output.append(box_line(f"Queue: {briefing['count']} videos | Skip: {briefing['skip']} (Optimized)", C.WHITE))
        output.append(box_line(f"Total Size: {briefing['size']:.1f} MB", C.WHITE))
        output.append(sep)
        output.append(box_line(f"RES: {config['target_height']}p  FPS: {config['target_fps']}  ENC: {codec_name}", C.INFO))
        output.append(sep)
        output.append(box_line(get_ticker_msg(), C.WARNING))
    else:
        output.append(box_line("Copyright (C) 2026 Mejensi", C.MUTED))
        output.append(box_line("Licensed under GNU GPL v3.0", C.MUTED))
        output.append(sep)
        c_info = f"RES: {config['target_height']}p  FPS: {config['target_fps']}  BIT: {config['video_bitrate']}"
        e_info = f"ENC: {codec_name}  WRK: {config['max_workers']}"
        output.append(box_line(c_info, C.INFO))
        output.append(box_line(e_info, C.INFO))
        output.append(sep)
        output.append(box_line(get_ticker_msg(), C.WARNING))
    
    output.append(sep)
    output.append(box_line("Press CTRL+C anytime to exit safely", C.ERROR))
    
    l, r, m = box['bl'], box['br'], box['h']
    output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
    return "\n".join(output)

def render_progress(label, percent, fps, speed, size_stats, eta="", label_width=20, bar_width=30, detail_width=None):
    label_width = max(8, int(label_width))
    bar_width = max(10, int(bar_width))
    detail_width = max(16, int(detail_width or max(label_width + bar_width, 32)))
    label = ellipsize_text(label, label_width)
    w = bar_width
    f, e = int(w * percent / 100), w - int(w * percent / 100)
    bar_char, bg_char, check_icon, arrow_icon, pipe_icon = get_progress_glyphs()
    
    if percent >= 100: bar_color = C.SUCCESS
    elif percent >= 50: bar_color = C.INFO
    else: bar_color = C.PRIMARY
    
    bar = f"{bar_color}{bar_char*f}{C.RESET}{C.MUTED}{bg_char*e}{C.RESET}"
    if percent >= 100:
        detail_text = ellipsize_text(size_stats, detail_width)
        return f" {C.SUCCESS}{check_icon}{C.RESET} {C.WHITE}{label:<{label_width}}{C.RESET} {bar} {C.SUCCESS}DONE{C.RESET}\n   {C.MUTED}{pipe_icon} {detail_text}{C.RESET}"
    else:
        fps_disp = fps if fps != "-" else "..."
        spd_disp = speed if speed != "0X" else "..."
        eta_disp = f" | {eta}" if eta else ""
        detail_text = ellipsize_text(f"{spd_disp} | {fps_disp} fps{eta_disp}", detail_width)
        return f" {C.PRIMARY}{arrow_icon}{C.RESET} {C.WHITE}{label:<{label_width}}{C.RESET} {bar} {C.INFO}{percent:5.1f}%{C.RESET}\n   {C.MUTED}{pipe_icon} {detail_text}{C.RESET}"

class WorkerStats:
    def __init__(self):
        self.stats = {}
        self.starts = {}
    def update(self, wid, fn, pct, fps, speed, size_stats=""):
        with LOCK:
            if wid not in self.starts: self.starts[wid] = time.time()
            self.stats[wid] = {'fn': fn, 'pct': pct, 'fps': fps, 'speed': speed, 'size': size_stats, 'start': self.starts[wid]}
    def get_all(self):
        with LOCK: return self.stats.copy()
    def remove_worker(self, wid):
        with LOCK:
            self.stats.pop(wid, None)
            self.starts.pop(wid, None)

# NOTE on st_ctime cross-platform behavior (FIX #13 documentation):
#   Windows  — path.stat().st_ctime returns the file CREATION time (correct for SetFileTime)
#   Linux/macOS — st_ctime is the inode CHANGE time, NOT creation time.
#   restore_file_metadata() already guards with `if platform.system() == "Windows":`,
#   so SetFileTime is only called on Windows where ctime == creation time.
#   On POSIX systems only atime/mtime are restored via os.utime(), which is the correct behaviour.
def get_file_metadata(path): return (path.stat().st_ctime, path.stat().st_atime, path.stat().st_mtime)
def restore_file_metadata(path, metadata):
    ctime, atime, mtime = metadata
    os.utime(path, (atime, mtime))
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes
            ts = int((ctime + 11644473600) * 10000000)
            ft = wintypes.FILETIME(ts & 0xFFFFFFFF, ts >> 32)
            h = ctypes.windll.kernel32.CreateFileW(str(path), 0x40000000 | 0x0100, 0, None, 3, 0, None)
            if h != -1:
                ctypes.windll.kernel32.SetFileTime(h, ctypes.byref(ft), None, None)
                ctypes.windll.kernel32.CloseHandle(h)
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logging.debug(f"Could not set Windows creation time for {path}: {e}")
    # On Linux/macOS: creation time cannot be set via standard Python APIs.
    # os.utime() above correctly restores atime and mtime, which is the best we can do.

def parse_fps(raw_value):
    text = str(raw_value or "").strip()
    if not text:
        return 0.0
    try:
        if "/" in text:
            num, den = text.split("/", 1)
            num_f, den_f = float(num), float(den)
            return (num_f / den_f) if den_f else 0.0
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0

def parse_ratio(raw_value):
    text = str(raw_value or "").strip()
    if not text or text.upper() in {"N/A", "UNKNOWN"}:
        return None
    try:
        if ":" in text:
            num, den = text.split(":", 1)
            num_f, den_f = float(num), float(den)
            if num_f <= 0.0 or den_f <= 0.0:
                return None
            return num_f / den_f
        if "/" in text:
            num, den = text.split("/", 1)
            num_f, den_f = float(num), float(den)
            if num_f <= 0.0 or den_f <= 0.0:
                return None
            return num_f / den_f
        value = float(text)
        return value if value > 0.0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None

def parse_bitrate(raw_value):
    if raw_value is None:
        return None
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    text = str(raw_value).strip().lower()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([kmg])', text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {'k': 1000, 'm': 1000_000, 'g': 1000_000_000}
    return int(value * multipliers[unit])

def parse_int(raw_value, default=0):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default

def parse_float(raw_value, default=None):
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return default

def normalize_tag_value(raw_value):
    return str(raw_value or "").strip()

def normalize_stream_language(stream):
    tags = stream.get("tags", {}) or {}
    language = str(tags.get("language") or "").strip().lower()
    return language or "und"

def normalize_stream_disposition(stream):
    disposition = stream.get("disposition", {}) or {}
    return {
        "default": parse_int(disposition.get("default"), 0),
        "forced": parse_int(disposition.get("forced"), 0),
    }

def build_audio_stream_descriptor(stream):
    tags = stream.get("tags", {}) or {}
    descriptor = normalize_stream_disposition(stream)
    descriptor.update(
        {
            "codec": stream.get("codec_name", ""),
            "language": normalize_stream_language(stream),
            "channels": parse_int(stream.get("channels"), 0),
            "sample_rate": parse_int(stream.get("sample_rate"), 0),
            "bitrate": parse_bitrate(stream.get("bit_rate")),
            "title": normalize_tag_value(tags.get("title")),
        }
    )
    return descriptor

def build_copy_stream_descriptor(stream):
    tags = stream.get("tags", {}) or {}
    descriptor = normalize_stream_disposition(stream)
    descriptor.update(
        {
            "codec": stream.get("codec_name", ""),
            "language": normalize_stream_language(stream),
            "title": normalize_tag_value(tags.get("title")),
            "filename": normalize_tag_value(tags.get("filename")),
            "mimetype": normalize_tag_value(tags.get("mimetype")),
        }
    )
    return descriptor

def get_chapter_time(chapter, key):
    time_value = parse_float(chapter.get(f"{key}_time"), None)
    if time_value is not None:
        return time_value
    tick_value = parse_float(chapter.get(key), None)
    time_base = parse_ratio(chapter.get("time_base"))
    if tick_value is None or time_base is None:
        return None
    return tick_value * time_base

def build_chapter_descriptor(chapter):
    tags = chapter.get("tags", {}) or {}
    return {
        "title": normalize_tag_value(tags.get("title")),
        "start_time": get_chapter_time(chapter, "start"),
        "end_time": get_chapter_time(chapter, "end"),
    }

def get_media_info(path, timeout=15, count_frames=False):
    try:
        if count_frames:
            quick_info = get_media_info(path, timeout=timeout, count_frames=False)
            duration = float(quick_info.get("duration", 0.0) or 0.0)
            timeout = max(timeout, min(MAX_FFMPEG_TIMEOUT_SEC, int(duration * 2.0) + 60))
        cmd = [FFPROBE_CMD, "-v", "error"]
        if count_frames:
            cmd.append("-count_frames")
        cmd.extend([
            "-show_format",
            "-show_streams",
            "-show_chapters",
            "-of", "json", str(path)
        ])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        format_info = data.get("format", {})
        chapters = data.get("chapters", [])
        raw_video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        stream_type_counts = {stream_type: 0 for stream_type in STREAM_TYPES}
        for stream in streams:
            codec_type = stream.get("codec_type", "")
            if codec_type in stream_type_counts:
                stream_type_counts[codec_type] += 1

        video_streams = []
        for stream in raw_video_streams:
            frame_count = -1
            for frame_key in ("nb_frames", "nb_read_frames"):
                frame_raw = stream.get(frame_key)
                if str(frame_raw or "").isdigit():
                    frame_count = int(frame_raw)
                    break
            if stream.get("disposition", {}).get("attached_pic") != 1:
                video_streams.append({
                    "index": int(stream.get("index") or 0),
                    "codec": stream.get("codec_name", ""),
                    "width": int(stream.get("width") or 0),
                    "height": int(stream.get("height") or 0),
                    "fps": parse_fps(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
                    "frame_count": frame_count,
                    "bitrate": parse_bitrate(stream.get("bit_rate")),
                    "pix_fmt": stream.get("pix_fmt", ""),
                    "sample_aspect_ratio": parse_ratio(stream.get("sample_aspect_ratio")),
                    "display_aspect_ratio": parse_ratio(stream.get("display_aspect_ratio")),
                    "language": normalize_stream_language(stream),
                    **normalize_stream_disposition(stream),
                })
        main_video = video_streams[0] if video_streams else None

        parsed_audio = [build_audio_stream_descriptor(stream) for stream in audio_streams]
        parsed_subtitles = [build_copy_stream_descriptor(stream) for stream in streams if stream.get("codec_type") == "subtitle"]
        parsed_data = [build_copy_stream_descriptor(stream) for stream in streams if stream.get("codec_type") == "data"]
        parsed_attachments = [build_copy_stream_descriptor(stream) for stream in streams if stream.get("codec_type") == "attachment"]
        parsed_chapters = [build_chapter_descriptor(chapter) for chapter in chapters]

        return {
            "duration": float(format_info.get("duration") or 0.0),
            "format_bitrate": parse_bitrate(format_info.get("bit_rate")),
            "video_codec": (main_video or {}).get("codec", ""),
            "width": int((main_video or {}).get("width") or 0),
            "height": int((main_video or {}).get("height") or 0),
            "fps": float((main_video or {}).get("fps") or 0.0),
            "frame_count": int((main_video or {}).get("frame_count", -1) or -1),
            "video_bitrate": (main_video or {}).get("bitrate"),
            "video_pix_fmt": (main_video or {}).get("pix_fmt", ""),
            "video_sample_aspect_ratio": (main_video or {}).get("sample_aspect_ratio"),
            "video_display_aspect_ratio": (main_video or {}).get("display_aspect_ratio"),
            "video_streams": video_streams,
            "audio_streams": parsed_audio,
            "subtitle_streams": parsed_subtitles,
            "data_streams": parsed_data,
            "attachment_streams": parsed_attachments,
            "video_stream_count": len(video_streams),
            "total_video_stream_count": len(raw_video_streams),
            "audio_stream_count": stream_type_counts["audio"],
            "subtitle_stream_count": stream_type_counts["subtitle"],
            "data_stream_count": stream_type_counts["data"],
            "attachment_stream_count": stream_type_counts["attachment"],
            "chapter_count": len(chapters),
            "chapters": parsed_chapters,
            "stream_type_counts": stream_type_counts,
            "has_video": main_video is not None,
        }
    except Exception:
        return {}

def build_scale_filter(target_height, use_vaapi=False):
    target_height = int(target_height)
    if use_vaapi:
        return f"format=nv12,hwupload,scale_vaapi=w=-2:h={target_height}:force_original_aspect_ratio=decrease"
    height_expr = f"min(ih\\,{target_height})"
    width_expr = f"trunc({height_expr}*dar/2)*2"
    return f"scale={width_expr}:{height_expr},setsar=1"

def get_expected_output_fps(input_info, config):
    input_fps = float(input_info.get("fps", 0.0) or 0.0)
    target_fps = float(config["target_fps"])
    return min(input_fps, target_fps) if input_fps > 0.0 else target_fps

def build_video_filter_chain(input_info, config, use_vaapi=False):
    filters = []
    input_fps = float(input_info.get("fps", 0.0) or 0.0)
    if input_fps <= 0.0 or input_fps > (config['target_fps'] + 0.5):
        filters.append(f"fps={config['target_fps']}")
    filters.append(build_scale_filter(config['target_height'], use_vaapi=use_vaapi))
    return ",".join(filters)

def find_vaapi_device():
    if platform.system() != "Linux":
        return None
    dri_dir = Path("/dev/dri")
    if not dri_dir.exists():
        return None
    render_nodes = sorted(dri_dir.glob("renderD*"))
    return str(render_nodes[0]) if render_nodes else None

DEFAULT_FFMPEG_DOWNLOADS = {
    "Windows": [
        {
            "kind": "archive",
            "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
            "archive_name": "ffmpeg-master-latest-win64-gpl.zip",
            "checksum_algorithm": "sha256",
            "checksum_url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256",
            "checksum_name": "ffmpeg-master-latest-win64-gpl.zip",
        },
        {
            "kind": "archive",
            "url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
            "archive_name": "ffmpeg-release-essentials.zip",
            "checksum_algorithm": "sha256",
            "checksum_url": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256",
            "checksum_name": "ffmpeg-release-essentials.zip",
        },
    ],
    "Linux": [
        {
            "kind": "archive",
            "url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
            "archive_name": "ffmpeg-master-latest-linux64-gpl.tar.xz",
            "checksum_algorithm": "sha256",
            "checksum_url": "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256",
            "checksum_name": "ffmpeg-master-latest-linux64-gpl.tar.xz",
        },
        {
            "kind": "archive",
            "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
            "archive_name": "ffmpeg-release-amd64-static.tar.xz",
            "checksum_algorithm": "md5",
            "checksum_url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz.md5",
            "checksum_name": "ffmpeg-release-amd64-static.tar.xz",
        },
    ],
    "Darwin": {
        "kind": "evermeet",
        "assets": [
            {
                "url": "https://evermeet.cx/ffmpeg/getrelease/zip",
                "archive_name": "ffmpeg-release.zip",
                "signature_url": "https://evermeet.cx/ffmpeg/getrelease/zip/sig",
                "signature_name": "ffmpeg-release.zip.sig",
                "binary_name": "ffmpeg",
            },
            {
                "url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip",
                "archive_name": "ffprobe-release.zip",
                "signature_url": "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip/sig",
                "signature_name": "ffprobe-release.zip.sig",
                "binary_name": "ffprobe",
            },
        ],
    },
}

def validate_single_ffmpeg_download_source(platform_name, source):
    if not isinstance(source, dict):
        raise ValueError(f"FFmpeg source entry for {platform_name} must be an object.")
    kind = source.get("kind")
    if kind == "archive":
        for field in ("url", "archive_name", "checksum_algorithm"):
            if not source.get(field):
                raise ValueError(f"FFmpeg archive source for {platform_name} is missing {field}.")
        if not source.get("digest") and not (source.get("checksum_url") and source.get("checksum_name")):
            raise ValueError(
                f"FFmpeg archive source for {platform_name} must define digest or checksum_url/checksum_name."
            )
    elif kind == "evermeet":
        assets = source.get("assets")
        if not isinstance(assets, list) or not assets:
            raise ValueError(f"Evermeet source for {platform_name} must define assets.")
        for asset in assets:
            for field in ("url", "archive_name", "signature_url", "signature_name", "binary_name"):
                if not asset.get(field):
                    raise ValueError(f"Evermeet asset for {platform_name} is missing {field}.")
    else:
        raise ValueError(f"Unsupported FFmpeg source kind for {platform_name}: {kind}")

def validate_ffmpeg_download_sources(sources):
    if not isinstance(sources, dict):
        raise ValueError("FFmpeg source manifest must be a JSON object.")
    for platform_name, source_entry in sources.items():
        source_list = source_entry if isinstance(source_entry, list) else [source_entry]
        if not source_list:
            raise ValueError(f"FFmpeg source entry for {platform_name} must not be empty.")
        for source in source_list:
            validate_single_ffmpeg_download_source(platform_name, source)

def iter_platform_ffmpeg_sources(platform_name=None):
    platform_name = platform_name or platform.system()
    source_entry = DEFAULT_FFMPEG_DOWNLOADS.get(platform_name)
    if not source_entry:
        return []
    if isinstance(source_entry, list):
        return list(source_entry)
    return [source_entry]

FFMPEG_DOWNLOADS = json.loads(json.dumps(DEFAULT_FFMPEG_DOWNLOADS))

def set_ffmpeg_commands(ffmpeg_path, ffprobe_path):
    global FFMPEG_CMD, FFPROBE_CMD
    ffmpeg_path = Path(ffmpeg_path).resolve()
    ffprobe_path = Path(ffprobe_path).resolve()
    FFMPEG_CMD = str(ffmpeg_path)
    FFPROBE_CMD = str(ffprobe_path)
    path_env = os.environ.get("PATH", "")
    bin_dir = str(ffmpeg_path.parent)
    path_parts = [part for part in path_env.split(os.pathsep) if part]
    if not path_parts or path_parts[0] != bin_dir:
        os.environ["PATH"] = bin_dir if not path_env else bin_dir + os.pathsep + path_env

def validate_binary_command(binary_path, expected_prefix):
    try:
        result = subprocess.run(
            [str(binary_path), "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=8,
        )
    except Exception:
        return False
    if result.returncode != 0:
        return False
    output = (result.stdout or result.stderr or "").lower()
    return expected_prefix in output

def validate_ffmpeg_pair(ffmpeg_path, ffprobe_path):
    return (
        validate_binary_command(ffmpeg_path, "ffmpeg version")
        and validate_binary_command(ffprobe_path, "ffprobe version")
    )

def iter_ffmpeg_candidate_pairs(ffmpeg_state=None):
    exe_name = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
    probe_name = "ffprobe.exe" if IS_WINDOWS else "ffprobe"
    ffmpeg_state = prune_missing_ffmpeg_state_entries(ffmpeg_state)
    managed_dirs = []
    for entry in ffmpeg_state.get("managed_installs", []):
        managed_dirs.append((f"managed:{entry['storage_mode']}", Path(entry["install_path"]), entry))
    launcher_dir = get_launcher_dir()
    script_dir = get_script_dir()
    if launcher_dir != script_dir:
        managed_dirs.append(("launcher/bin", launcher_dir / "bin", None))
    managed_dirs.extend([
        ("runtime/bin", get_session_ffmpeg_dir(), None),
        ("script/bin", script_dir / "bin", None),
        ("app/bin", BIN_DIR, None),
    ])
    seen = set()
    for label, directory, managed_entry in managed_dirs:
        try:
            resolved_directory = directory.resolve()
        except Exception:
            resolved_directory = directory
        key = str(resolved_directory)
        if key in seen:
            continue
        seen.add(key)
        ffmpeg_path = directory / exe_name
        ffprobe_path = directory / probe_name
        if ffmpeg_path.exists() and ffprobe_path.exists():
            if managed_entry and managed_entry.get("verification_status") == "user_override_unverified":
                if not validate_ffmpeg_pair(ffmpeg_path, ffprobe_path):
                    managed_entry["last_validation_error"] = "Unverified managed FFmpeg failed validation on startup."
                    remove_managed_ffmpeg_install(managed_entry, ffmpeg_state)
                    continue
            yield {
                "ffmpeg_path": ffmpeg_path,
                "ffprobe_path": ffprobe_path,
                "origin": "managed",
                "label": label,
                "managed_entry": managed_entry,
            }
    system_ffmpeg = shutil.which("ffmpeg")
    system_ffprobe = shutil.which("ffprobe")
    if system_ffmpeg and system_ffprobe:
        system_ffmpeg_path = Path(system_ffmpeg)
        system_ffprobe_path = Path(system_ffprobe)
        system_dir = system_ffmpeg_path.parent
        try:
            system_key = str(system_dir.resolve())
        except Exception:
            system_key = str(system_dir)
        try:
            ffprobe_key = str(system_ffprobe_path.parent.resolve())
        except Exception:
            ffprobe_key = str(system_ffprobe_path.parent)
        if system_key != ffprobe_key:
            logging.warning(
                f"Skipping split PATH FFmpeg candidate pair: {system_ffmpeg_path} | {system_ffprobe_path}"
            )
        elif system_key not in seen:
            yield {
                "ffmpeg_path": system_ffmpeg_path,
                "ffprobe_path": system_ffprobe_path,
                "origin": "system",
                "label": "PATH",
                "managed_entry": None,
            }

def allow_system_ffmpeg_candidate(candidate, policy=None):
    policy = normalize_system_ffmpeg_policy(policy)
    if policy == "allow":
        return True
    if policy == "deny":
        logging.info(
            "Skipping system FFmpeg candidate because system_ffmpeg_policy=deny: "
            f"{candidate['ffmpeg_path']} | {candidate['ffprobe_path']}"
        )
        return False
    if not supports_interactive_input():
        logging.warning(
            "Skipping system FFmpeg candidate because system_ffmpeg_policy=prompt "
            "and stdin is not interactive."
        )
        return False
    answer = safe_input(
        f"{C.PRIMARY}>> Use system FFmpeg from PATH?\n"
        f"   FFmpeg: {candidate['ffmpeg_path']}\n"
        f"   FFprobe: {candidate['ffprobe_path']}\n"
        f"   (Y/N): {C.RESET}",
        "n",
    ).strip().lower()
    return answer in {"y", "yes"}

def compute_file_digest(path, algorithm):
    hasher = hashlib.new(algorithm)
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest().lower()

def parse_checksum_file(text, target_name):
    target_name = os.path.basename(target_name)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        digest = parts[0].strip().lower()
        candidate_name = os.path.basename(parts[-1].lstrip("*").strip())
        if candidate_name == target_name:
            return digest
    return None

def format_download_error(exc):
    import urllib.error
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code} {exc.reason}"
    if isinstance(exc, urllib.error.URLError):
        return str(exc.reason)
    return str(exc)

def powershell_download(url, destination):
    escaped_url = url.replace("'", "''")
    escaped_dest = str(destination).replace("'", "''")
    ps_cmd = (
        "$ProgressPreference = 'SilentlyContinue'; "
        "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        f"Invoke-WebRequest -UseBasicParsing -MaximumRedirection 10 -Uri '{escaped_url}' -OutFile '{escaped_dest}' -UserAgent 'Mozilla/5.0'"
    )
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_cmd],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=180,
    )
    if result.returncode == 0:
        return True
    logging.error(f"PowerShell download failed for {url}: {format_recent_output((result.stderr or result.stdout or '').splitlines())}")
    return False

def download_url_to_file(url, destination, show_progress=False):
    import urllib.error
    import urllib.request
    import ssl

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    def python_download():
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(destination, 'wb') as out_file:
            total = int(response.info().get('Content-Length', -1))
            bytes_read = 0
            while True:
                chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                out_file.write(chunk)
                bytes_read += len(chunk)
                if show_progress and total > 0:
                    pct = min(100.0, (bytes_read / total) * 100.0)
                    done = int(40 * pct / 100.0)
                    bar = "#" * done + "." * (40 - done)
                    sys.stdout.write(f"\r{C.INFO}[PROGRESS]{C.RESET} {bar} {pct:5.1f}%")
                    sys.stdout.flush()

    try:
        python_download()
        return True
    except Exception as e:
        logging.warning(f"Python download failed for {url}: {format_download_error(e)}")
        is_ssl_error = isinstance(e, ssl.SSLError) or (
            isinstance(e, urllib.error.URLError) and isinstance(e.reason, ssl.SSLError)
        )
        if IS_WINDOWS:
            print(f"\n{C.WARNING}[RETRY] Python download failed, attempting PowerShell fallback...{C.RESET}")
            return powershell_download(url, destination)
        if is_ssl_error:
            print(f"\n{C.ERROR}[SSL ERROR] Cannot verify download certificate. Aborted for security.{C.RESET}")
            return False
        return False

def download_text(url):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.read().decode('utf-8', errors='replace')
    except OSError as exc:
        logging.error(f"Text download failed for {url}: {format_download_error(exc)}")
        return None

def verify_download_checksum(archive_path, checksum_url, algorithm, checksum_name):
    checksum_text = download_text(checksum_url)
    if not checksum_text:
        logging.error(f"Checksum file could not be downloaded: {checksum_url}")
        return False
    expected = parse_checksum_file(checksum_text, checksum_name)
    if not expected:
        logging.error(f"Checksum entry not found for {checksum_name}")
        return False
    actual = compute_file_digest(archive_path, algorithm)
    if actual != expected.lower():
        logging.error(f"Checksum mismatch for {checksum_name}: expected {expected.lower()}, got {actual}")
        return False
    return True

def verify_download_manifest_entry(archive_path, source):
    algorithm = str(source.get("checksum_algorithm") or "sha256").strip().lower()
    checksum_url = str(source.get("checksum_url") or "").strip()
    checksum_name = str(source.get("checksum_name") or source.get("archive_name") or Path(archive_path).name).strip()
    if checksum_url:
        if not verify_download_checksum(archive_path, checksum_url, algorithm, checksum_name):
            return False
    expected = str(source.get("digest") or "").strip().lower()
    if expected:
        actual = compute_file_digest(archive_path, algorithm)
        return actual == expected
    if not checksum_url:
        logging.error(f"Digest missing from FFmpeg source manifest for {source.get('archive_name', archive_path.name)}")
        return False
    return True

def extract_binaries_from_archive(archive_path, binary_names, destination_dir):
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    targets = {name.lower(): destination_dir / name for name in binary_names}
    found = set()
    archive_name = archive_path.name.lower()
    if archive_name.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive_path, 'r') as archive:
            for member in archive.infolist():
                member_name = os.path.basename(member.filename)
                key = member_name.lower()
                if key not in targets:
                    continue
                with archive.open(member) as src, open(targets[key], 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                if not IS_WINDOWS:
                    targets[key].chmod(0o755)
                found.add(key)
    elif archive_name.endswith(".tar.xz"):
        import tarfile
        with tarfile.open(archive_path, 'r:xz') as archive:
            for member in archive.getmembers():
                member_name = os.path.basename(member.name)
                key = member_name.lower()
                if key not in targets or not member.isfile():
                    continue
                src = archive.extractfile(member)
                if src is None:
                    continue
                with src, open(targets[key], 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                targets[key].chmod(0o755)
                found.add(key)
    else:
        raise RuntimeError(f"Unsupported archive type: {archive_path.name}")
    missing = [name for name in binary_names if name.lower() not in found]
    if missing:
        raise RuntimeError(f"Missing binaries after extraction: {', '.join(missing)}")

def install_binaries_atomically(staged_dir, binary_names, install_dir=None):
    staged_dir = Path(staged_dir)
    install_dir = Path(install_dir) if install_dir else BIN_DIR
    missing = [name for name in binary_names if not (staged_dir / name).exists()]
    if missing:
        raise RuntimeError(f"Staged binaries missing: {', '.join(missing)}")

    install_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = install_dir.parent / f"{install_dir.name}.bak.{SESSION_ID}"
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    had_existing_install = install_dir.exists()

    try:
        if had_existing_install:
            install_dir.rename(backup_dir)
        staged_dir.rename(install_dir)
    except OSError:
        if had_existing_install and backup_dir.exists() and not install_dir.exists():
            try:
                backup_dir.rename(install_dir)
            except OSError as restore_error:
                logging.critical(f"FFmpeg install rollback failed: {restore_error}")
        raise
    finally:
        if staged_dir.exists():
            shutil.rmtree(staged_dir, ignore_errors=True)

    if had_existing_install and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)

def verify_evermeet_signature(archive_path, signature_path):
    gpg = shutil.which("gpg") or shutil.which("gpg2")
    if not gpg:
        print(f"{C.ERROR}[ERROR] Secure macOS auto-download requires GPG for signature verification.{C.RESET}")
        print(f"{C.INFO}Install FFmpeg manually or install GPG and retry.{C.RESET}")
        return False
    gnupg_home = get_runtime_work_dir(f"gpg_{SESSION_ID}")
    try:
        key_path = Path(gnupg_home) / "evermeet.asc"
        if not download_url_to_file(EVERMEET_GPG_KEY_URL, key_path, show_progress=False):
            return False
        import_result = subprocess.run(
            [gpg, "--batch", "--homedir", str(gnupg_home), "--import", str(key_path)],
            capture_output=True,
            text=True,
        )
        if import_result.returncode != 0:
            logging.error(import_result.stderr.strip())
            return False
        fingerprint_result = subprocess.run(
            [gpg, "--batch", "--homedir", str(gnupg_home), "--with-colons", "--fingerprint"],
            capture_output=True,
            text=True,
        )
        if EVERMEET_GPG_FINGERPRINT not in fingerprint_result.stdout.replace(":", "").upper():
            logging.error("Evermeet signing key fingerprint mismatch")
            return False
        verify_result = subprocess.run(
            [gpg, "--batch", "--homedir", str(gnupg_home), "--verify", str(signature_path), str(archive_path)],
            capture_output=True,
            text=True,
        )
        if verify_result.returncode != 0:
            logging.error(verify_result.stderr.strip())
            return False
        return True
    finally:
        shutil.rmtree(gnupg_home, ignore_errors=True)

def prompt_ffmpeg_storage_choice(ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    preferred = normalize_storage_mode(ffmpeg_state.get("preferred_storage_mode")) or get_recommended_ffmpeg_storage_mode()
    choice_map = {"1": "appdata", "2": "portable", "3": "session", "4": "custom"}
    default_choice = next((key for key, value in choice_map.items() if value == preferred), "1")
    print(f" {C.PRIMARY}[FFMPEG] Choose where managed FFmpeg should be stored:{C.RESET}")
    print(f"    [1] AppData (persistent, recommended)")
    print(f"    [2] Portable launcher bin (persistent)")
    print(f"    [3] Temp / Session (current run only)")
    print(f"    [4] Custom Path")
    while True:
        answer = safe_input(f" {C.PRIMARY}>> Choice [Default={default_choice}]: {C.RESET}", default_choice).strip() or default_choice
        if answer not in choice_map:
            print(f" {C.ERROR}[!] Invalid choice.{C.RESET}")
            continue
        storage_mode = choice_map[answer]
        custom_path = ""
        if storage_mode == "custom":
            custom_path = safe_input(f" {C.PRIMARY}>> Custom FFmpeg folder path: {C.RESET}", "").strip()
            if not custom_path:
                print(f" {C.ERROR}[!] Custom path cannot be empty.{C.RESET}")
                continue
        return storage_mode, custom_path

def check_ffmpeg(ffmpeg_state=None):
    return check_ffmpeg_with_policy(DEFAULT_CONFIG["system_ffmpeg_policy"], ffmpeg_state=ffmpeg_state)

def check_ffmpeg_with_policy(system_ffmpeg_policy=None, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    for candidate in iter_ffmpeg_candidate_pairs(ffmpeg_state):
        ffmpeg_path = candidate["ffmpeg_path"]
        ffprobe_path = candidate["ffprobe_path"]
        if candidate["origin"] == "system" and not allow_system_ffmpeg_candidate(candidate, system_ffmpeg_policy):
            continue
        if not validate_ffmpeg_pair(ffmpeg_path, ffprobe_path):
            logging.warning(
                f"Ignoring invalid FFmpeg candidate pair ({candidate['label']}): "
                f"{ffmpeg_path} | {ffprobe_path}"
            )
            continue
        set_ffmpeg_commands(ffmpeg_path, ffprobe_path)
        logging.info(
            f"Selected FFmpeg pair ({candidate['label']}): {ffmpeg_path} | {ffprobe_path}"
        )
        managed_entry = candidate.get("managed_entry")
        if managed_entry is not None:
            touch_managed_ffmpeg_install(Path(managed_entry["install_path"]), ffmpeg_state)
        return True
    return False


def ensure_ffmpeg(auto_download=None, system_ffmpeg_policy=None, storage_mode="", custom_install_path="", ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    if auto_download is None:
        auto_download = DEFAULT_CONFIG["auto_download_ffmpeg"]
    runtime_dir = get_session_ffmpeg_dir()
    binary_names = get_managed_ffmpeg_binary_names()
    runtime_pair_exists = all((runtime_dir / name).exists() for name in binary_names)
    if runtime_pair_exists and check_ffmpeg_with_policy("allow", ffmpeg_state=ffmpeg_state):
        return True
    if auto_download:
        storage_mode = normalize_storage_mode(storage_mode) or "session"
        custom_install_path = str(custom_install_path or "")
        if download_ffmpeg(storage_mode=storage_mode, custom_install_path=custom_install_path, ffmpeg_state=ffmpeg_state):
            return True
    if check_ffmpeg_with_policy(system_ffmpeg_policy, ffmpeg_state=ffmpeg_state):
        return True
    print(f"\n{C.WARNING} {get_warning_symbol()}  FFmpeg Not Found{C.RESET}\n")
    if not supports_interactive_input():
        print(f"{C.ERROR}[ERROR] FFmpeg could not be downloaded or found on this computer.{C.RESET}")
        return False
    if safe_input(f"{C.PRIMARY}>> Try downloading FFmpeg again? (Y/N): {C.RESET}", "n").strip().lower() != 'y':
        return False
    if not storage_mode:
        storage_mode, custom_install_path = prompt_ffmpeg_storage_choice(ffmpeg_state)
    return download_ffmpeg(storage_mode=storage_mode, custom_install_path=custom_install_path, ffmpeg_state=ffmpeg_state)

def extract_ffmpeg_source(source, temp_dir, install_stage_dir, binary_names, allow_unverified=False):
    if source["kind"] == "archive":
        archive_path = Path(temp_dir) / source["archive_name"]
        if not download_url_to_file(source["url"], archive_path, show_progress=True):
            raise RuntimeError("download failed")
        if not allow_unverified:
            print(f"\n{C.INFO}[VERIFY] Verifying download integrity...{C.RESET}")
            if not verify_download_manifest_entry(archive_path, source):
                raise RuntimeError("checksum verification failed")
        else:
            print(f"\n{C.WARNING}[VERIFY] Integrity verification bypassed by explicit user override.{C.RESET}")
        print(f"{C.INFO}[EXTRACT] Extracting binaries...{C.RESET}")
        extract_binaries_from_archive(archive_path, binary_names, install_stage_dir)
        return
    for asset in source["assets"]:
        archive_path = Path(temp_dir) / asset["archive_name"]
        signature_path = Path(temp_dir) / asset["signature_name"]
        if not download_url_to_file(asset["url"], archive_path, show_progress=True):
            raise RuntimeError(f"download failed for {asset['binary_name']}")
        if not allow_unverified:
            sig_url = asset["signature_url"]
            if not download_url_to_file(sig_url, signature_path, show_progress=False):
                # Fallback: scrape evermeet homepage for current version and build direct sig URL
                try:
                    index_page = download_text("https://evermeet.cx/ffmpeg/")
                    archive_name = asset["binary_name"]  # ffmpeg or ffprobe
                    import re
                    sig_pattern = re.compile(rf'href="({re.escape(archive_name)}-[\d.-]+[^"]*\.zip\.sig)"')
                    match = sig_pattern.search(index_page)
                    if match:
                        direct_sig_url = f"https://evermeet.cx/ffmpeg/{match.group(1)}"
                        logging.info(f"Falling back to direct signature URL: {direct_sig_url}")
                        if not download_url_to_file(direct_sig_url, signature_path, show_progress=False):
                            raise RuntimeError(f"signature download failed for {asset['binary_name']}")
                    else:
                        raise RuntimeError(f"signature download failed for {asset['binary_name']}")
                except RuntimeError:
                    raise
                except Exception as e:
                    raise RuntimeError(f"signature download failed for {asset['binary_name']}: {e}")
            print(f"\n{C.INFO}[VERIFY] Verifying signed archive {asset['binary_name']}...{C.RESET}")
            if not verify_evermeet_signature(archive_path, signature_path):
                raise RuntimeError(f"signature verification failed for {asset['binary_name']}")
        else:
            print(f"\n{C.WARNING}[VERIFY] Signature verification bypassed by explicit user override.{C.RESET}")
        print(f"{C.INFO}[EXTRACT] Extracting {asset['binary_name']}...{C.RESET}")
        extract_binaries_from_archive(archive_path, [asset["binary_name"]], install_stage_dir)

def validate_staged_ffmpeg_install(stage_dir, binary_names):
    stage_dir = Path(stage_dir)
    ffmpeg_path = stage_dir / binary_names[0]
    ffprobe_path = stage_dir / binary_names[1]
    if not validate_ffmpeg_pair(ffmpeg_path, ffprobe_path):
        return False
    original_ffmpeg, original_ffprobe = FFMPEG_CMD, FFPROBE_CMD
    try:
        set_ffmpeg_commands(ffmpeg_path, ffprobe_path)
        return bool(_test_encoder("libx264"))
    finally:
        globals()["FFMPEG_CMD"] = original_ffmpeg
        globals()["FFPROBE_CMD"] = original_ffprobe

def prompt_unverified_ffmpeg_override(failed_sources):
    """Prompt user with Accept-once / Accept-and-remember options when verification fails.

    Returns:
        'remember' -> user accepted and wants to remember this source
        'once' -> user accepted once
        False -> user declined
    """
    if not supports_interactive_input():
        return False
    print(f"\n{C.ERROR}[SECURITY] FFmpeg downloads could not be verified from trusted sources.{C.RESET}")
    for item in failed_sources:
        print(f"    - {item}{C.RESET}")
    print(f"{C.WARNING}Continuing with an unverified archive may install tampered or corrupt binaries.{C.RESET}")
    print(f"{C.INFO}Mnemosyne will still quarantine, validate, and atomically roll back failed binaries.{C.RESET}")
    print("")
    print("Options:\n  1) Accept once (install this time only)\n  2) Accept and remember this source (avoid future prompts)\n  3) Decline")
    while True:
        answer = safe_input(f" {C.PRIMARY}>> Choose 1, 2, or 3: {C.RESET}", "3").strip()
        if answer == "1":
            return 'once'
        if answer == "2":
            return 'remember'
        if answer == "3":
            return False
        print(f"{C.WARNING}Invalid choice. Enter 1, 2 or 3.{C.RESET}")

def install_staged_ffmpeg(install_stage_dir, install_dir, binary_names, storage_mode, source, ffmpeg_state, verification_status="verified"):
    if not validate_staged_ffmpeg_install(install_stage_dir, binary_names):
        raise RuntimeError("Downloaded FFmpeg binaries failed validation")
    install_binaries_atomically(install_stage_dir, binary_names, install_dir)
    source_identity = source.get("url") or source.get("kind") or platform.system()
    upsert_managed_ffmpeg_install(
        install_dir,
        storage_mode,
        source_identity,
        ffmpeg_state,
        verification_status=verification_status,
    )

def download_ffmpeg(storage_mode="", custom_install_path="", ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    sources = iter_platform_ffmpeg_sources()
    if not sources:
        return False
    print(f"\n{C.INFO}[DOWNLOAD] Fetching FFmpeg...{C.RESET}")
    storage_mode = normalize_storage_mode(storage_mode) or get_recommended_ffmpeg_storage_mode()
    install_dir = resolve_ffmpeg_install_dir(storage_mode, custom_install_path)
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    FFMPEG_DOWNLOAD_SIZE_BYTES = 800 * 1024 * 1024  # 800 MB for FFmpeg download
    ffmpeg_space_needed = FFMPEG_DOWNLOAD_SIZE_BYTES
    if not warn_if_space_is_low(install_dir.parent, ffmpeg_space_needed, "FFmpeg download"):
        return False
    binary_names = get_managed_ffmpeg_binary_names()
    failed_sources = []
    for index, source in enumerate(sources, start=1):
        install_stage_dir = install_dir.parent / f"{install_dir.name}.stage.{SESSION_ID}.{index}"
        if install_stage_dir.exists():
            shutil.rmtree(install_stage_dir, ignore_errors=True)
        temp_dir = get_runtime_work_dir(f"ffmpeg_download_{SESSION_ID}_{index}")
        try:
            # If this source was previously accepted by the user as unverified, allow unverified install automatically
            allow_unverified = bool(is_source_previously_accepted(source))
            if allow_unverified:
                logging.info(f"Using previously-accepted unverified source: {source.get('url') or source.get('kind')}")
            extract_ffmpeg_source(source, temp_dir, install_stage_dir, binary_names, allow_unverified=allow_unverified)
            verification_status = "verified" if not allow_unverified else "user_override_remembered"
            install_staged_ffmpeg(install_stage_dir, install_dir, binary_names, storage_mode, source, ffmpeg_state, verification_status=verification_status)
            return check_ffmpeg_with_policy("allow", ffmpeg_state=ffmpeg_state)
        except Exception as exc:
            failed_sources.append(f"{source.get('url') or source.get('kind')}: {exc}")
            print(f"{C.WARNING}[WARN] FFmpeg source failed: {exc}{C.RESET}")
        finally:
            if install_stage_dir.exists():
                shutil.rmtree(install_stage_dir, ignore_errors=True)
            if 'temp_dir' in locals() and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
    prompt_result = prompt_unverified_ffmpeg_override(failed_sources)
    if not prompt_result:
        return False
    source = sources[0]
    if prompt_result == 'remember':
        try:
            record_accepted_unverified_source(source)
        except Exception:
            pass
    install_stage_dir = install_dir.parent / f"{install_dir.name}.unverified.{SESSION_ID}"
    if install_stage_dir.exists():
        shutil.rmtree(install_stage_dir, ignore_errors=True)
    temp_dir = get_runtime_work_dir(f"ffmpeg_unverified_{SESSION_ID}")
    try:
        extract_ffmpeg_source(source, temp_dir, install_stage_dir, binary_names, allow_unverified=True)
        install_staged_ffmpeg(
            install_stage_dir,
            install_dir,
            binary_names,
            storage_mode,
            source,
            ffmpeg_state,
            verification_status="user_override_unverified",
        )
        return check_ffmpeg_with_policy("allow", ffmpeg_state=ffmpeg_state)
    except Exception as exc:
        print(f"\n{C.ERROR}[ERROR] Unverified FFmpeg failed quarantine validation: {exc}{C.RESET}")
        return False
    finally:
        if install_stage_dir.exists():
            shutil.rmtree(install_stage_dir, ignore_errors=True)
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def _test_encoder(codec, return_details=False):
    """Run a 1-second null encode to confirm the encoder is functional."""
    details = {"cmd": [], "returncode": None, "stderr_tail": "n/a"}
    try:
        cmd = [FFMPEG_CMD, "-f", "lavfi", "-i", "nullsrc=s=256x256:r=30", "-t", "1"]
        if codec == "h264_vaapi":
            vaapi_device = find_vaapi_device()
            if not vaapi_device:
                details["stderr_tail"] = "VAAPI requested but no render node was found."
                return (False, details) if return_details else False
            cmd.extend([
                "-vaapi_device", vaapi_device,
                "-filter:v", "format=nv12,hwupload",
                "-c:v", codec, "-f", "null", "-"
            ])
        else:
            cmd.extend(["-pix_fmt", "yuv420p", "-c:v", codec, "-f", "null", "-"])
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15
        )
        details = {
            "cmd": cmd,
            "returncode": r.returncode,
            "stderr_tail": format_recent_output((r.stderr or r.stdout or "").splitlines(), max_lines=8),
        }
        success = r.returncode == 0
        if return_details:
            return success, details
        if not success and codec != "libx264":
            logging.warning(f"Encoder probe failed for {codec}: {details['stderr_tail']}")
        return success
    except Exception as e:
        details["stderr_tail"] = str(e)
        return (False, details) if return_details else False

def detect_gpu_codec(force_codec=None):
    logging.info(f"Encoder discovery using FFmpeg: {FFMPEG_CMD} | FFprobe: {FFPROBE_CMD}")
    if force_codec and force_codec != 'auto':
        try:
            r = subprocess.run([FFMPEG_CMD, "-encoders"], capture_output=True, text=True, timeout=5)
            logging.info(f"Forced codec requested: {force_codec}")
            available = force_codec in r.stdout
            success, details = _test_encoder(force_codec, return_details=True)
            logging.info(f"Forced codec probe for {force_codec}: {'PASS' if success else 'FAIL'}")
            if not success:
                logging.warning(f"Forced codec {force_codec} probe failed: {details['stderr_tail']}")
            if available and success:
                logging.info(f"Selected forced encoder: {force_codec}")
                return (force_codec, f"{force_codec.upper()} [FORCED]")
            logging.warning(f"Forced codec {force_codec} is unavailable or failed probe; continuing with auto detection")
        except Exception as e:
            logging.warning(f"Forced codec detection failed for {force_codec}: {e}")
    try:
        r = subprocess.run([FFMPEG_CMD, "-encoders"], capture_output=True, text=True, timeout=5)
        e = r.stdout
        candidates = [
            ("h264_nvenc",        "NVIDIA (NVENC)"),
            ("h264_amf",          "AMD (AMF)"),
            ("h264_qsv",          "Intel QuickSync"),
            ("h264_videotoolbox", "Apple VideoToolbox"),
            ("h264_vaapi",        "VAAPI"),
        ]
        available = [codec for codec, _name in candidates if codec in e]
        logging.info(
            "Available hardware encoder candidates: "
            + (", ".join(available) if available else "none")
        )
        for codec, name in candidates:
            if codec not in e:
                logging.info(f"Encoder candidate {codec}: NOT PRESENT")
                continue
            success, details = _test_encoder(codec, return_details=True)
            logging.info(f"Encoder candidate {codec}: {'PASS' if success else 'FAIL'}")
            if not success:
                logging.warning(f"Encoder candidate {codec} failed probe: {details['stderr_tail']}")
                continue
            logging.info(f"Selected encoder: {name}")
            return (codec, name)
    except Exception as e:
        logging.warning(f"Hardware encoder discovery failed: {e}")
    logging.info("Falling back to CPU encoder: libx264")
    return ("libx264", "CPU (x264)")

worker_stats = WorkerStats()

def comparable_audio_stream(stream):
    return {
        "language": stream.get("language", "und"),
        "default": int(stream.get("default", 0) or 0),
        "forced": int(stream.get("forced", 0) or 0),
        "channels": int(stream.get("channels", 0) or 0),
        "sample_rate": int(stream.get("sample_rate", 0) or 0),
        "title": stream.get("title", ""),
    }

def comparable_copy_stream(stream):
    return {
        "codec": stream.get("codec", ""),
        "language": stream.get("language", "und"),
        "default": int(stream.get("default", 0) or 0),
        "forced": int(stream.get("forced", 0) or 0),
        "title": stream.get("title", ""),
        "filename": stream.get("filename", ""),
        "mimetype": stream.get("mimetype", ""),
    }

def compare_audio_streams(in_info, out_info, config):
    in_audio = [comparable_audio_stream(stream) for stream in in_info.get("audio_streams", [])]
    out_audio = [comparable_audio_stream(stream) for stream in out_info.get("audio_streams", [])]
    if in_audio != out_audio:
        return False
    target_audio_bitrate = parse_bitrate(config.get('audio_bitrate'))
    if target_audio_bitrate is None:
        return True
    for stream in out_info.get("audio_streams", []):
        bitrate = stream.get("bitrate")
        if bitrate is not None and bitrate > target_audio_bitrate:
            return False
    return True

def compare_copy_streams(in_info, out_info, key):
    in_streams = [comparable_copy_stream(stream) for stream in in_info.get(key, [])]
    out_streams = [comparable_copy_stream(stream) for stream in out_info.get(key, [])]
    return in_streams == out_streams

def compare_chapters(in_info, out_info):
    in_chapters = in_info.get("chapters", []) or []
    out_chapters = out_info.get("chapters", []) or []
    if len(in_chapters) != len(out_chapters):
        return False
    for in_chapter, out_chapter in zip(in_chapters, out_chapters):
        if normalize_tag_value(in_chapter.get("title")) != normalize_tag_value(out_chapter.get("title")):
            return False
        for key in ("start_time", "end_time"):
            in_time = in_chapter.get(key)
            out_time = out_chapter.get(key)
            if in_time is None or out_time is None:
                if in_time != out_time:
                    return False
                continue
            if abs(float(in_time) - float(out_time)) > 0.05:
                return False
    return True

def should_skip_video(vpath, config, info=None):
    try:
        info = info or get_media_info(vpath, timeout=10)
        if not info.get("has_video"):
            return False
        if int(info.get("video_stream_count", 0) or 0) != 1:
            return False

        target_video_bitrate = parse_bitrate(config.get('video_bitrate'))
        target_audio_bitrate = parse_bitrate(config.get('audio_bitrate'))

        video_ok = (
            info.get("video_codec") == "h264" and
            info.get("video_pix_fmt") == TARGET_PIXEL_FORMAT and
            0 < info.get("height", 0) <= config['target_height'] and
            0 < info.get("fps", 0.0) <= config['target_fps']
        )
        if not video_ok or target_video_bitrate is None:
            return False

        video_bitrate = info.get("video_bitrate")
        if video_bitrate is None or video_bitrate > target_video_bitrate:
            return False

        for audio_stream in info.get("audio_streams", []):
            if audio_stream.get("codec") != "aac":
                return False
            bitrate = audio_stream.get("bitrate")
            if target_audio_bitrate is not None and (bitrate is None or bitrate > target_audio_bitrate):
                return False
        return True
    except Exception as e:
        logging.debug(f"should_skip_video check failed for {vpath}: {e}")
        return False

def normalize_stream_counts(info):
    counts = info.get("stream_type_counts", {}) or {}
    return {stream_type: int(counts.get(stream_type, 0) or 0) for stream_type in STREAM_TYPES}

def get_video_display_ratio(info):
    ratio = info.get("video_display_aspect_ratio")
    if isinstance(ratio, (int, float)) and ratio > 0.0:
        return float(ratio)
    width = int(info.get("width", 0) or 0)
    height = int(info.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    ratio = width / height
    sample_ratio = info.get("video_sample_aspect_ratio")
    if isinstance(sample_ratio, (int, float)) and sample_ratio > 0.0:
        ratio *= float(sample_ratio)
    return ratio if ratio > 0.0 else None

def get_expected_frame_count(in_info, config):
    in_frames = int(in_info.get("frame_count", -1) or -1)
    in_fps = float(in_info.get("fps", 0.0) or 0.0)
    expected_fps = get_expected_output_fps(in_info, config)
    if in_frames < 0 or in_fps <= 0.0 or expected_fps <= 0.0:
        return -1
    return max(1, int(round(in_frames * (expected_fps / in_fps))))

def verify_media_decode(path, info=None):
    info = info or {}
    duration = float(info.get("duration", 0.0) or 0.0)
    timeout = min(MAX_FFMPEG_TIMEOUT_SEC, max(MIN_DECODE_TIMEOUT_SEC, int(duration * DECODE_TIMEOUT_MULTIPLIER) + DECODE_TIMEOUT_ADDEND)) if duration > 0.0 else BASE_DECODE_TIMEOUT_SEC
    cmd = [
        FFMPEG_CMD,
        "-nostdin",
        "-v", "error",
        "-i", str(path),
        "-map", "0:v?",
        "-map", "0:a?",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
        )
    except Exception as exc:
        logging.warning(f"verify_media_decode: decode probe failed for {path}: {exc}")
        return False
    if result.returncode != 0:
        logging.warning(
            f"verify_media_decode: decode failed for {path}: "
            f"{format_recent_output((result.stderr or result.stdout or '').splitlines(), max_lines=8)}"
        )
        return False
    return True

def verify_output(inp, outp, config, return_details=False):
    details = {
        "metadata_ok": False,
        "decode_ok": False,
        "frame_check": "disabled" if not config.get('verify_frames', True) else "decode_only",
    }
    if not outp.exists() or outp.stat().st_size < MIN_VALID_VIDEO_BYTES:
        return (False, details) if return_details else False
    try:
        frame_probe = bool(config.get('verify_frames', True))
        in_info = get_media_info(inp, count_frames=frame_probe)
        out_info = get_media_info(outp, count_frames=frame_probe)
        if int(in_info.get("video_stream_count", 0) or 0) != 1 or int(out_info.get("video_stream_count", 0) or 0) != 1:
            logging.warning(
                f"verify_output: unsupported video-stream topology for {inp.name} "
                f"(in={in_info.get('video_stream_count', 0)}, out={out_info.get('video_stream_count', 0)})"
            )
            return (False, details) if return_details else False

        in_d = in_info.get("duration", 0.0)
        out_d = out_info.get("duration", 0.0)
        if in_d <= 0.0 or out_d <= 0.0:
            logging.warning(f"verify_output: could not read duration of source {inp.name}")
            return (False, details) if return_details else False

        duration_tolerance = min(1.0, max(DURATION_TOLERANCE_MIN, in_d * DURATION_TOLERANCE_RATIO))
        duration_ratio = out_d / in_d if in_d > 0.0 else 0.0
        dur_ok = abs(in_d - out_d) <= duration_tolerance and DURATION_RATIO_MIN <= duration_ratio <= DURATION_RATIO_MAX
        codec_ok = out_info.get("video_codec") == "h264"
        pix_fmt_ok = out_info.get("video_pix_fmt") == TARGET_PIXEL_FORMAT

        input_height = in_info.get("height", 0)
        max_expected_height = min(input_height, config['target_height']) if input_height > 0 else config['target_height']
        height_ok = 0 < out_info.get("height", 0) <= max_expected_height
        width_ok = int(out_info.get("width", 0) or 0) > 0

        display_ratio_ok = True
        input_display_ratio = get_video_display_ratio(in_info)
        output_display_ratio = get_video_display_ratio(out_info)
        if input_display_ratio and output_display_ratio:
            ratio_delta = abs(output_display_ratio - input_display_ratio)
            display_ratio_ok = ratio_delta <= max(ASPECT_RATIO_TOLERANCE, input_display_ratio * ASPECT_RATIO_TOLERANCE)

        geometry_ok = True
        output_height = int(out_info.get("height", 0) or 0)
        output_width = int(out_info.get("width", 0) or 0)
        if input_display_ratio and output_height > 0 and output_width > 0:
            expected_width = max(2, int(round((output_height * input_display_ratio) / 2.0) * 2))
            geometry_tolerance = max(2, int(expected_width * GEOMETRY_TOLERANCE_RATIO))
            geometry_ok = abs(output_width - expected_width) <= geometry_tolerance

        expected_fps = get_expected_output_fps(in_info, config)
        out_fps = float(out_info.get("fps", 0.0) or 0.0)
        fps_ok = 0 < out_fps <= (expected_fps + 0.5)
        if in_info.get("fps", 0.0) > 0.0:
            fps_ok = fps_ok and out_fps >= max(1.0, expected_fps - 1.0)

        audio_ok = compare_audio_streams(in_info, out_info, config)
        subtitle_ok = compare_copy_streams(in_info, out_info, "subtitle_streams")
        data_ok = compare_copy_streams(in_info, out_info, "data_streams")
        attachment_ok = compare_copy_streams(in_info, out_info, "attachment_streams")
        stream_ok = audio_ok and subtitle_ok and data_ok and attachment_ok
        chapter_ok = compare_chapters(in_info, out_info)

        if not stream_ok:
            logging.warning(
                f"verify_output: stream comparison failed for {inp.name}: "
                f"audio_ok={audio_ok}, subtitle_ok={subtitle_ok}, "
                f"data_ok={data_ok}, attachment_ok={attachment_ok}"
            )
            if not audio_ok:
                in_audio = [comparable_audio_stream(s) for s in in_info.get("audio_streams", [])]
                out_audio = [comparable_audio_stream(s) for s in out_info.get("audio_streams", [])]
                logging.warning(
                    f"verify_output: audio mismatch for {inp.name}: "
                    f"in={in_audio}, out={out_audio}"
                )

        frame_ok = True
        expected_frames = get_expected_frame_count(in_info, config)
        out_frames = out_info.get("frame_count", -1)
        if config.get('verify_frames', True) and expected_frames != -1 and out_frames != -1:
            frame_tolerance = max(3, int(expected_frames * FRAME_TOLERANCE_RATIO))
            frame_ok = abs(out_frames - expected_frames) <= frame_tolerance
            details["frame_check"] = "counted"
        elif config.get('verify_frames', True):
            logging.warning(f"verify_output: frame counts unavailable for strict comparison on {inp.name}; decode gate remains required")

        metadata_ok = (
            dur_ok and codec_ok and pix_fmt_ok and fps_ok and height_ok and width_ok and display_ratio_ok and geometry_ok
            and stream_ok and chapter_ok and frame_ok
        )
        details.update(
            {
                "metadata_ok": metadata_ok,
                "duration_ok": dur_ok,
                "codec_ok": codec_ok,
                "pix_fmt_ok": pix_fmt_ok,
                "fps_ok": fps_ok,
                "height_ok": height_ok,
                "width_ok": width_ok,
                "display_ratio_ok": display_ratio_ok,
                "geometry_ok": geometry_ok,
                "stream_ok": stream_ok,
                "chapter_ok": chapter_ok,
                "frame_ok": frame_ok,
                "expected_frames": expected_frames,
                "output_frames": out_frames,
            }
        )
        if not metadata_ok:
            failed_checks = [
                key for key in (
                    "duration_ok", "codec_ok", "pix_fmt_ok", "fps_ok",
                    "height_ok", "width_ok", "display_ratio_ok", "geometry_ok",
                    "stream_ok", "chapter_ok", "frame_ok",
                )
                if not details.get(key, False)
            ]
            logging.warning(
                f"verify_output metadata check failed for {inp.name}: "
                f"failed checks: {', '.join(failed_checks)} | "
                f"duration_ratio={duration_ratio:.4f}, "
                f"expected_frames={expected_frames}, output_frames={out_frames}"
            )
        # If frame counting was already performed successfully, the file has
        # already been fully decoded — skip redundant decode verification.
        if details.get("frame_check") == "counted" and out_frames > 0:
            details["decode_ok"] = True
        elif metadata_ok:
            details["decode_ok"] = verify_media_decode(outp, out_info)
        success = details["metadata_ok"] and details["decode_ok"]
        return (success, details) if return_details else success
    except Exception as exc:
        details["last_error"] = str(exc)
        return (False, details) if return_details else False

def process_video(wid, vpath, codec, config):
    fn = vpath.name
    s_fps, s_speed, pct = "-", "0X", 0.0
    worker_stats.update(wid, fn, 0.0, s_fps, s_speed, "")
    logging.info(f"[Worker {wid}] Started processing: {fn}")

    try:
        input_info = get_media_info(vpath)
        if not input_info.get("has_video"):
            logging.error(f"Could not identify a primary video stream for {fn}")
            worker_stats.update(wid, fn, 0.0, "-", "0X", "Unreadable video stream")
            return False
        if int(input_info.get("video_stream_count", 0) or 0) != 1:
            count = int(input_info.get("video_stream_count", 0) or 0)
            logging.error(f"Unsupported multi-video-stream input for {fn}: found {count} real video streams")
            worker_stats.update(wid, fn, 0.0, "-", "0X", "Multi-video streams unsupported")
            return False

        if should_skip_video(vpath, config, info=input_info):
            logging.info(f"Skipping (Already Optimized): {vpath.name}")
            worker_stats.update(wid, fn, 100.0, "SKIPPED", "0X", "Already Optimized")
            return 2 # SKIPPED

        meta = get_file_metadata(vpath) if config.get('preserve_metadata', True) else None
        start_size = vpath.stat().st_size
        unique_suffix = f"{threading.get_ident()}_{int(time.time() * 1000)}"
        temp_workspace = get_temp_workspace(vpath.parent)
        tmp = temp_workspace / f"{unique_suffix}_{fn}"
        dur = input_info.get("duration", 0.0) or 1.0
        vaapi_device = None
        recent_output = []
        logging.info(f"[Worker {wid}] Using codec {codec} for {fn}")
        if codec == "h264_vaapi":
            vaapi_device = find_vaapi_device()
            if not vaapi_device:
                logging.warning(f"VAAPI requested but no render node found for {fn}, falling back to CPU")
                worker_stats.update(wid, fn, 0.0, "-", "0X", "Retrying with CPU...")
                return process_video(wid, vpath, "libx264", config)

        cmd = [FFMPEG_CMD, "-nostdin", "-y"]
        if vaapi_device:
            cmd.extend(["-vaapi_device", vaapi_device])
        cmd.extend([
            "-i", str(vpath),
            "-map", "0",
            "-map_metadata", "0",
            "-map_chapters", "0",
            "-c", "copy",
            "-c:v:0", codec
        ])

        if "nvenc" in codec:
            cmd.extend(["-rc:v:0", "vbr", "-cq:v:0", "24", "-preset:v:0", "p4"])
        elif "libx264" in codec:
            cmd.extend(["-b:v:0", config['video_bitrate'], "-preset:v:0", config.get("x264_preset", "medium")])
            if config.get("ffmpeg_threads"):
                cmd.extend(["-threads:v:0", str(config["ffmpeg_threads"])])
        else:
            cmd.extend(["-b:v:0", config['video_bitrate']])

        vf_chain = build_video_filter_chain(input_info, config, use_vaapi=bool(vaapi_device))
        cmd.extend([
            "-filter:v:0", vf_chain,
            "-pix_fmt:v:0", TARGET_PIXEL_FORMAT,
            "-c:a", "aac", "-b:a", config['audio_bitrate'],
            "-c:s", "copy", "-c:d", "copy", "-c:t", "copy",
            "-metadata", f"encoder={APP_NAME} v{VERSION}",
            "-progress", "-", "-nostats", str(tmp)
        ])
        
        if IS_WINDOWS:
            # CREATE_NEW_PROCESS_GROUP = 0x00000200
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=0x00000200)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        PROCESS_MGR.register(proc)
        try:
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None: break
                if line:
                    recent_output.append(line.rstrip())
                    if len(recent_output) > 20:
                        recent_output.pop(0)
                if "out_time_ms=" in line:
                    try:
                        micros = float(line.split("out_time_ms=")[1].split()[0])
                        new_pct = min(99.9, ((micros / 1_000_000.0) / dur) * 100); pct = new_pct
                        worker_stats.update(wid, fn, pct, s_fps, s_speed)
                    except Exception as e:
                        logging.debug(f"Failed to parse FFmpeg progress for {fn}: {e}")
                elif "out_time=" in line:
                    try:
                        ts = line.split("out_time=")[1].split()[0]
                        h, m, s = map(float, ts.split(':'))
                        new_pct = min(99.9, ((h*3600 + m*60 + s) / dur) * 100); pct = new_pct
                        worker_stats.update(wid, fn, pct, s_fps, s_speed)
                    except Exception as e:
                        logging.debug(f"Failed to parse FFmpeg progress for {fn}: {e}")
                elif "fps=" in line:
                    try:
                        s_fps = line.split("fps=")[1].split()[0]
                        worker_stats.update(wid, fn, pct, s_fps, s_speed)
                    except Exception as e:
                        logging.debug(f"Failed to parse FFmpeg FPS for {fn}: {e}")
                elif "speed=" in line:
                    try:
                        s_speed = line.split("speed=")[1].split()[0]
                        worker_stats.update(wid, fn, pct, s_fps, s_speed)
                    except Exception as e:
                        logging.debug(f"Failed to parse FFmpeg speed for {fn}: {e}")
        finally:
            PROCESS_MGR.unregister(proc)
            try:
                if proc.stdout:
                    proc.stdout.close()
            except OSError:
                pass
        if proc.returncode != 0:
            if codec != "libx264":
                logging.warning(
                    f"Hardware encoding failed for {fn} with {codec} (exit {proc.returncode}). "
                    f"Recent FFmpeg output: {format_recent_output(recent_output)}"
                )
                worker_stats.update(wid, fn, 0.0, "-", "0X", "Retrying with CPU...")
                return process_video(wid, vpath, "libx264", config)
            logging.error(
                f"Encoding failed for {fn} with {codec} (exit {proc.returncode}). "
                f"Recent FFmpeg output: {format_recent_output(recent_output)}"
            )
            return False

        verified, verification_details = verify_output(vpath, tmp, config, return_details=True)
        if not verified:
            logging.warning(f"Pre-swap verification failed for {fn} — discarding temp file")
            try: tmp.unlink()
            except (subprocess.SubprocessError, OSError) as e:
                logging.debug(f"Could not discard temp file for {fn}: {e}")
            if codec != "libx264":
                logging.warning(f"Verification failed for hardware output on {fn}; retrying with CPU-safe yuv420p encode")
                worker_stats.update(wid, fn, 0.0, "-", "0X", "Retrying with CPU...")
                return process_video(wid, vpath, "libx264", config)
            return False

        end_size = tmp.stat().st_size
        size_diff = (1 - (end_size / start_size)) * 100 if start_size > 0 else 0.0
        size_stats = f"{start_size/1024/1024:.1f}MB -> {end_size/1024/1024:.1f}MB ({size_diff:.0f}% saved)"
        write_transaction_journal(
            vpath,
            stage="verified_ready_to_swap",
            temp_output_path=str(tmp),
            codec=codec,
            verification=verification_details,
        )

        bak = vpath.with_suffix(vpath.suffix + '.bak')
        if bak.exists():
            logging.error(f"Stale backup already exists for {fn}; rescue is required before reprocessing")
            worker_stats.update(wid, fn, 0.0, "-", "0X", "Backup rescue required")
            try: tmp.unlink()
            except (subprocess.SubprocessError, OSError) as e:
                logging.debug(f"Could not discard temp file for {fn}: {e}")
            clear_transaction_journal(vpath)
            return False

        # Step 1: Back up the original
        try:
            write_transaction_journal(
                vpath,
                stage="renaming_original_to_backup",
                backup_path=str(bak),
            )
            vpath.rename(bak)
            write_transaction_journal(
                vpath,
                stage="backup_created",
                backup_path=str(bak),
            )
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logging.error(f"Could not rename original to .bak for {fn}: {e}")
            try: tmp.unlink()
            except OSError as e2:
                logging.debug(f"Could not discard temp file for {fn}: {e2}")
            clear_transaction_journal(vpath)
            return False

        # Step 2: Move temp file into place
        try:
            write_transaction_journal(vpath, stage="placing_verified_output", backup_path=str(bak))
            tmp.rename(vpath)
            write_transaction_journal(vpath, stage="swap_complete", backup_path=str(bak))
        except (OSError, AttributeError, ValueError, TypeError) as e:
            logging.error(f"Could not move temp file to {fn}: {e}")
            write_transaction_journal(vpath, stage="swap_restore_attempt", backup_path=str(bak), last_error=str(e))
            restored = False
            try:
                bak.rename(vpath)  # Restore original
                restored = True
            except OSError as restore_error:
                write_transaction_journal(
                    vpath,
                    stage="swap_restore_failed",
                    backup_path=str(bak),
                    last_error=str(restore_error),
                )
            try: tmp.unlink()
            except OSError as e3:
                logging.debug(f"Could not discard temp file during swap restore for {fn}: {e3}")
            if restored:
                clear_transaction_journal(vpath)
            return False

        # Step 3: Restore original timestamps (non-fatal if it fails)
        if meta is not None:
            try:
                restore_file_metadata(vpath, meta)
            except (subprocess.SubprocessError, OSError) as e:
                logging.warning(f"Metadata restore failed for {fn} (file is intact): {e}")

        # Step 4: Final size check, then delete backup
        if vpath.exists() and vpath.stat().st_size > MIN_VALID_VIDEO_BYTES:
            try:
                bak.unlink()
                clear_transaction_journal(vpath)
            except (subprocess.SubprocessError, OSError) as e:
                write_transaction_journal(
                    vpath,
                    stage="backup_cleanup_failed",
                    backup_path=str(bak),
                    last_error=str(e),
                )
                logging.warning(f"Could not delete .bak for {fn}: {e} — will be cleaned next run")
        else:
            logging.error(f"Post-swap size check failed for {fn} — restoring backup")
            write_transaction_journal(vpath, stage="post_swap_size_check_failed", backup_path=str(bak))
            try:
                vpath.unlink()
                bak.rename(vpath)
                clear_transaction_journal(vpath)
            except OSError as e2:
                write_transaction_journal(
                    vpath,
                    stage="recovery_failed",
                    backup_path=str(bak),
                    last_error=str(e2),
                )
                logging.critical(f"RECOVERY FAILED for {fn}: {e2} — manual intervention required")
            return False
            
        worker_stats.update(wid, fn, 100.0, "0", "0", size_stats)
        return 1 # SUCCESS
    except (OSError, AttributeError, ValueError, TypeError) as e:
        logging.error(f"Process error for {fn}: {e}")
        if 'tmp' in locals() and tmp.exists(): tmp.unlink()
        return 0 # FAILED

def normalize_worker_count(value):
    max_cap = max(1, os.cpu_count() or 1)
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError("Worker count must be a whole number.")
    if count < 1 or count > max_cap:
        raise ValueError(f"Worker count must be between 1 and {max_cap}.")
    return count

def update_display(total, completed, codec_name, config):
    stats = worker_stats.get_all()
    in_progress = [wid for wid in sorted(stats.keys()) if 0 < stats[wid]['pct'] < 100]
    cols, rows = get_terminal_dimensions()
    completed = min(completed, total)
    o_pct = (completed / total * 100) if total > 0 else 0

    if not supports_live_dashboard() or cols < MIN_LIVE_DASHBOARD_WIDTH or rows < MIN_LIVE_DASHBOARD_HEIGHT:
        compact_parts = [f"[Progress] {completed}/{total} done ({o_pct:.1f}%)", f"active {len(in_progress)}"]
        for wid in in_progress[:2]:
            s = stats[wid]
            compact_parts.append(
                f"W{wid} {ellipsize_text(s['fn'], 18)} {s['pct']:.1f}% {s['speed']}"
            )
        if len(in_progress) > 2:
            compact_parts.append(f"+{len(in_progress) - 2} more")
        snapshot = ellipsize_text(" | ".join(compact_parts), max(24, cols - 1))
        emit_compact_dashboard(snapshot, completed, total)
        return

    dashboard_width = max(44, min(70, cols - 5))
    box = draw_header(config, codec_name, width=dashboard_width)
    header_lines = len(box.splitlines())
    max_display_workers = max(1, min(6, (rows - header_lines - 3) // 3))
    display_workers = in_progress[:max_display_workers]
    label_width = max(12, min(22, dashboard_width - 34))
    bar_width = max(10, min(30, dashboard_width - label_width - 14))
    detail_width = max(24, dashboard_width - 4)
    buffer = [""]

    for wid in display_workers:
        s = stats[wid]
        fn_short = ellipsize_text(s['fn'], label_width)
        eta_str = ""
        if 0 < s['pct'] < 100 and 'start' in s:
            elapsed = time.time() - s['start']
            if s['pct'] > 1:
                rem = (elapsed / (s['pct'] / 100)) - elapsed
                m, s_v = divmod(int(rem), 60); eta_str = f"ETA: {m}m {s_v}s"
        buffer.append(
            render_progress(
                fn_short,
                s['pct'],
                s['fps'],
                s['speed'],
                s['size'],
                eta_str,
                label_width=label_width,
                bar_width=bar_width,
                detail_width=detail_width,
            )
        )
        buffer.append("")
    
    if len(in_progress) > max_display_workers:
        more_text = ellipsize_text(
            f"... and {len(in_progress) - max_display_workers} more active processes ...",
            dashboard_width + 2,
        )
        buffer.append(f" {C.MUTED}{more_text}{C.RESET}\n")

    buffer.append(f" {C.WHITE}{'=' * min(dashboard_width + 2, max(24, cols - 2))}{C.RESET}")
    summary_text = ellipsize_text(
        f"Total: {total} | Done: {completed} | Active: {len(in_progress)} | {o_pct:.1f}%",
        dashboard_width + 2,
    )
    buffer.append(f" {C.WHITE}{summary_text}{C.RESET}")
    render_live_dashboard(box + "\n".join(buffer))

def show_security_notice(log_msg, drive_type=None):
    clear_screen(); w = 70
    draw_separator(w, 'top')
    draw_box_line("SECURITY & TRANSPARENCY", w, C.BOLD + C.PRIMARY)
    draw_separator(w, 'mid')
    if drive_type == 2: # REMOVABLE
        draw_box_line(f"{get_warning_symbol()}  REMOVABLE MEDIA DETECTED", w, C.BOLD + C.WARNING)
        draw_box_line("IMPORTANT: Keep the device connected to prevent data loss.", w, C.WARNING)
        draw_separator(w, 'mid')
    draw_box_line("1. Local Processing: No data ever leaves your computer.", w, C.WHITE)
    draw_box_line(f"2. Logs: {log_msg}", w, C.WHITE)
    draw_box_line("3. Open Source: Full code transparency (GNU GPL v3.0)", w, C.WHITE)
    draw_box_line("4. Atomic Safety: Temporary files used to prevent data loss.", w, C.WHITE)
    draw_separator(w, 'mid')
    draw_box_line("Mnemosyne protects your privacy and your digital memory.", w, C.SUCCESS)
    draw_separator(w, 'bot')
    print("")
    if supports_interactive_input():
        safe_input(f" {C.PRIMARY}>> Press ENTER to continue...{C.RESET}")
    else:
        logging.info("Non-interactive stdin detected; continuing past the security notice without pause.")

def describe_worker_mode(config):
    if int(config.get("max_workers", 1) or 1) <= 1:
        return "Sequential"
    if int(config.get("max_workers", 1) or 1) == DEFAULT_CONFIG["max_workers"]:
        return "Parallel"
    return f"Custom ({config['max_workers']})"

def describe_sort_mode(sort_value):
    labels = {
        "name_az": "Name A-Z",
        "name_za": "Name Z-A",
        "size_desc": "Largest First",
        "size_asc": "Smallest First",
    }
    return labels.get(sort_value, "Name A-Z")

def describe_ffmpeg_preferences(ffmpeg_preferences):
    behavior = "Auto-download" if ffmpeg_preferences.get("auto_download") else "Ask First"
    storage_mode = normalize_storage_mode(ffmpeg_preferences.get("storage_mode")) or get_recommended_ffmpeg_storage_mode()
    label = describe_storage_mode(storage_mode)
    if storage_mode == "custom" and ffmpeg_preferences.get("custom_install_path"):
        label = f"{label}: {ffmpeg_preferences['custom_install_path']}"
    return f"{behavior} -> {label}"

def prompt_menu_choice(prompt, default_choice, valid_choices):
    valid_choices = {str(choice).lower() for choice in valid_choices}
    while True:
        answer = safe_input(f" {C.PRIMARY}>> {prompt} [Default={default_choice}]: {C.RESET}", str(default_choice)).strip().lower() or str(default_choice).lower()
        if answer in valid_choices:
            return answer
        print(f" {C.ERROR}[!] Invalid choice.{C.RESET}")

def configure_worker_mode(config):
    current_default = "1" if int(config.get("max_workers", 1) or 1) == 1 else ("2" if int(config.get("max_workers", 1) or 1) == DEFAULT_CONFIG["max_workers"] else "3")
    print(f"    [1] Sequential")
    print(f"    [2] Parallel")
    print(f"    [3] Custom Workers")
    mode_choice = prompt_menu_choice("Worker Mode", current_default, {"1", "2", "3"})
    if mode_choice == "1":
        config["max_workers"] = 1
        return
    if mode_choice == "2":
        config["max_workers"] = DEFAULT_CONFIG["max_workers"]
        return
    while True:
        worker_value = safe_input(
            f" {C.PRIMARY}>> Workers (1-{max(1, os.cpu_count() or 1)}) [Current={config['max_workers']}]: {C.RESET}",
            str(config["max_workers"]),
        ).strip()
        try:
            config["max_workers"] = normalize_worker_count(worker_value or config["max_workers"])
            return
        except ValueError as exc:
            print(f" {C.ERROR}[!] {exc}{C.RESET}")

def edit_ffmpeg_preferences(ffmpeg_preferences, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    print(f"    [1] Ask before download")
    print(f"    [2] Auto-download")
    auto_choice = prompt_menu_choice("FFmpeg download behavior", "1" if not ffmpeg_preferences.get("auto_download") else "2", {"1", "2"})
    ffmpeg_preferences["auto_download"] = auto_choice == "2"
    storage_mode, custom_path = prompt_ffmpeg_storage_choice(ffmpeg_state)
    ffmpeg_preferences["storage_mode"] = storage_mode
    ffmpeg_preferences["custom_install_path"] = custom_path

def edit_session_settings(context, ffmpeg_state=None):
    ffmpeg_state = ffmpeg_state or load_ffmpeg_state()
    config = context.session_config
    allow_scan_settings = not context.is_explicit_file_mode
    while True:
        clear_screen()
        print(draw_header(config, "Auto Detect"))
        print(f" {C.PRIMARY}[EDIT] Active settings{C.RESET}")
        print(f"    [1] Profile ({get_profile_label(config['profile_id'])})")
        print(f"    [2] Worker Mode ({describe_worker_mode(config)})")
        index = 3
        scan_choice = sort_choice = None
        if allow_scan_settings:
            scan_choice = str(index); index += 1
            sort_choice = str(index); index += 1
            print(f"    [{scan_choice}] Scan Scope ({'Recursive' if config.get('recursive') else 'Current Folder'})")
            print(f"    [{sort_choice}] Sort Order ({describe_sort_mode(config.get('sort'))})")
        log_choice = str(index); index += 1
        ffmpeg_choice = str(index)
        print(f"    [{log_choice}] Log File ({'Desktop' if config.get('desktop_log') else 'Temp'})")
        print(f"    [{ffmpeg_choice}] FFmpeg ({describe_ffmpeg_preferences(context.ffmpeg_preferences)})")
        print(f"    [S] Save global settings")
        print(f"    [B] Back")
        answer = safe_input(f" {C.PRIMARY}>> Choice: {C.RESET}", "b").strip().lower()
        if answer == "b":
            return
        if answer == "s":
            saved_config_ok = save_config(config)
            saved_ffmpeg_ok = persist_ffmpeg_preferences(context.ffmpeg_preferences, ffmpeg_state)
            if saved_config_ok and saved_ffmpeg_ok:
                print(f" {C.SUCCESS}[+] Settings saved globally.{C.RESET}")
            else:
                print(f" {C.ERROR}[!] Could not save all settings.{C.RESET}")
            time.sleep(1)
            continue
        if answer == "1":
            profile_ids = list(PROFILE_PRESETS.keys())
            for idx, profile_id in enumerate(profile_ids, start=1):
                print(f"    [{idx}] {get_profile_label(profile_id)}")
            current_default = str(profile_ids.index(normalize_profile_id(config.get("profile_id"))) + 1)
            profile_choice = prompt_menu_choice("Profile", current_default, {str(i) for i in range(1, len(profile_ids) + 1)})
            selected_profile = profile_ids[int(profile_choice) - 1]
            config["profile_id"] = selected_profile
            for key in PROFILE_KEYS:
                config[key] = PROFILE_PRESETS[selected_profile][key]
            continue
        if answer == "2":
            configure_worker_mode(config)
            continue
        if allow_scan_settings and answer == scan_choice:
            print(f"    [1] Current Folder")
            print(f"    [2] Recursive")
            config["recursive"] = prompt_menu_choice("Scan Scope", "2" if config.get("recursive") else "1", {"1", "2"}) == "2"
            continue
        if allow_scan_settings and answer == sort_choice:
            print(f"    [1] Name A-Z")
            print(f"    [2] Name Z-A")
            print(f"    [3] Largest First")
            print(f"    [4] Smallest First")
            sort_map = {"1": "name_az", "2": "name_za", "3": "size_desc", "4": "size_asc"}
            default_sort = next((choice for choice, value in sort_map.items() if value == config.get("sort")), "1")
            config["sort"] = sort_map[prompt_menu_choice("Sort Order", default_sort, set(sort_map.keys()))]
            continue
        if answer == log_choice:
            print(f"    [1] Temp")
            print(f"    [2] Desktop")
            config["desktop_log"] = prompt_menu_choice("Log location", "2" if config.get("desktop_log") else "1", {"1", "2"}) == "2"
            continue
        if answer == ffmpeg_choice:
            edit_ffmpeg_preferences(context.ffmpeg_preferences, ffmpeg_state)
            continue
        print(f" {C.ERROR}[!] Invalid choice.{C.RESET}")
        time.sleep(1)

def resolve_cli_input_paths(raw_paths):
    valid_files = []
    valid_dirs = []
    invalid_inputs = []
    seen = set()
    for raw_path in raw_paths:
        path = Path(raw_path)
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path
        key = workspace_key(resolved)
        if key in seen:
            continue
        seen.add(key)
        if not resolved.exists() or is_path_in_temp_workspace(resolved):
            invalid_inputs.append(resolved)
            continue
        if resolved.is_dir():
            valid_dirs.append(resolved)
            continue
        if resolved.is_file() and resolved.suffix.lower() in VIDEO_EXTENSIONS:
            valid_files.append(resolved)
            continue
        invalid_inputs.append(resolved)
    return valid_files, valid_dirs, invalid_inputs

def resolve_explicit_input_files(raw_paths):
    valid_files, valid_dirs, invalid_inputs = resolve_cli_input_paths(raw_paths)
    return valid_files, invalid_inputs + valid_dirs

def collect_removable_targets(paths):
    removable = []
    for path in paths:
        try:
            if get_drive_type(str(path)) == DRIVE_REMOVABLE:
                removable.append(path)
        except Exception:
            pass
    return removable

def build_run_context(args, parser):
    session_config = load_config()
    ffmpeg_state = load_ffmpeg_state()
    ffmpeg_preferences = build_ffmpeg_preferences(ffmpeg_state)
    explicit_paths = list(getattr(args, "paths", []) or [])
    valid_inputs, valid_dirs, invalid_inputs = resolve_cli_input_paths(explicit_paths)
    if valid_inputs:
        invalid_inputs.extend(valid_dirs)
    mode = "explicit-files" if valid_inputs or (explicit_paths and not valid_dirs) else "folder-scan"
    if args.workers is not None:
        try:
            session_config["max_workers"] = normalize_worker_count(args.workers)
        except ValueError as exc:
            parser.error(str(exc))
    if args.height is not None:
        if args.height < 1:
            parser.error("Target height must be at least 1.")
        session_config["target_height"] = args.height
    if args.desktop_log:
        session_config["desktop_log"] = True
    if args.recursive and mode != "explicit-files":
        session_config["recursive"] = True
    target_dirs = [path.parent for path in valid_inputs] if valid_inputs else (valid_dirs or [Path.cwd()] if mode == "folder-scan" else [])
    context = RunContext(
        mode=mode,
        input_files=valid_inputs,
        target_dirs=list(iter_unique_target_dirs(target_dirs=target_dirs)),
        invalid_inputs=invalid_inputs,
        removable_targets=collect_removable_targets(valid_inputs),
        session_config=session_config,
        saved_config_loaded=has_saved_config(),
        ffmpeg_preferences=ffmpeg_preferences,
    )
    if context.removable_targets and args.workers is None:
        context.session_config["max_workers"] = 1
    if mode == "explicit-files":
        context.session_config["recursive"] = False
    return context

def scan_videos_for_context(context, worker_override=False):
    config = context.session_config
    if context.is_explicit_file_mode:
        videos = list(context.input_files)
    else:
        videos = []
        seen_videos = set()
        for target_dir in context.target_dirs or [Path.cwd()]:
            for video in iter_video_files(target_dir, recursive=config.get("recursive", False)):
                key = workspace_key(video)
                if key in seen_videos:
                    continue
                seen_videos.add(key)
                videos.append(video)
        if config["sort"] == "name_az":
            videos.sort()
        elif config["sort"] == "name_za":
            videos.sort(reverse=True)
        elif config["sort"] == "size_desc":
            videos.sort(key=lambda x: x.stat().st_size, reverse=True)
        elif config["sort"] == "size_asc":
            videos.sort(key=lambda x: x.stat().st_size)
    total_in = 0
    skipped_pre = 0
    for video in videos:
        total_in += video.stat().st_size
        if should_skip_video(video, config):
            skipped_pre += 1
    context.target_dirs = list(iter_unique_target_dirs(target_dirs=[video.parent for video in videos] or context.target_dirs or [Path.cwd()]))
    context.removable_targets = collect_removable_targets(videos)
    if context.removable_targets and not worker_override:
        config["max_workers"] = 1
    return videos, total_in, skipped_pre

def render_run_summary(context, videos, total_in, skipped_pre):
    clear_screen()
    brief_data = {"count": len(videos), "skip": skipped_pre, "size": total_in / 1024 / 1024}
    print(draw_header(context.session_config, "Auto Detect", briefing=brief_data))
    if context.is_explicit_file_mode:
        draw_separator(70, "top")
        draw_box_line("DRAG-AND-DROP CONFIRMATION", 70, C.BOLD + C.PRIMARY)
        draw_box_line(f"Mode: Explicit Files | Targets: {len(context.target_dirs)} folders", 70, C.WHITE)
        draw_separator(70, "mid")
    else:
        draw_separator(70, "top")
        draw_box_line("FOLDER SCAN READY", 70, C.BOLD + C.PRIMARY)
        draw_box_line(
            f"Scope: {'Recursive' if context.session_config.get('recursive') else 'Current folder'} | Sort: {describe_sort_mode(context.session_config.get('sort'))}",
            70,
            C.WHITE,
        )
        draw_separator(70, "mid")
    draw_box_line(f"Profile: {get_profile_label(context.session_config['profile_id'])}", 70, C.INFO)
    draw_box_line(f"Workers: {describe_worker_mode(context.session_config)}", 70, C.INFO)
    draw_box_line(f"Logs: {'Desktop' if context.session_config.get('desktop_log') else 'Temp'}", 70, C.INFO)
    draw_box_line(f"FFmpeg: {describe_ffmpeg_preferences(context.ffmpeg_preferences)}", 70, C.INFO)
    if context.invalid_inputs:
        draw_separator(70, "mid")
        draw_box_line(f"Ignored Inputs: {len(context.invalid_inputs)} unsupported or missing item(s)", 70, C.WARNING)
    if context.session_config.get("show_drive_warnings", True) and context.removable_targets:
        draw_separator(70, "mid")
        draw_box_line("REMOVABLE MEDIA DETECTED", 70, C.WARNING)
        draw_box_line("Sequential mode is recommended to reduce interruption risk.", 70, C.WARNING)
    draw_separator(70, "bot")

def update_runtime_state(context):
    RUNTIME_STATE["recursive"] = bool(context.session_config.get("recursive", False) and not context.is_explicit_file_mode)
    RUNTIME_STATE["auto_cleanup"] = bool(context.session_config.get("auto_cleanup", True))
    RUNTIME_STATE["target_dirs"] = context.target_dirs or [Path.cwd()]

def handle_interrupt(sig=None, frame=None):
    logging.info("Interrupt received. Emergency shutdown...")
    PROCESS_MGR.kill_all()
    show_cursor()
    print(f"\n{C.WARNING}!!! MISSION ABORTED: SAFE EXIT INITIATED !!!{C.RESET}")
    recursive = bool(RUNTIME_STATE.get("recursive", False))
    target_dirs = RUNTIME_STATE.get("target_dirs") or [Path.cwd()]
    if RUNTIME_STATE.get("auto_cleanup", True):
        cleanup_temp_files(recursive=recursive, include_current_session=True, target_dirs=target_dirs)
    baks = []
    for base_dir in iter_unique_target_dirs(target_dirs=target_dirs):
        baks.extend(iter_video_backups(base_dir, recursive=recursive))
    if baks:
        print(f"{C.WARNING}[!] {len(baks)} backup file(s) remain — run Mnemosyne again to restore them safely.{C.RESET}")
    print(f"{C.INFO}Clean-up complete. You may now exit.{C.RESET}")
    os._exit(130)  # Hard exit — ensures all threads stop immediately

def register_signal_handlers():
    import signal
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, handle_interrupt)
        except (OSError, RuntimeError, ValueError):
            pass

def main():
    ensure_utf8_stdio()
    enable_ansi()
    interactive_mode = supports_interactive_input()
    register_signal_handlers()

    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{VERSION}", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='*', help='Video files to process, or folders to scan')
    parser.add_argument('-r', '--recursive', action='store_true', help='Search subfolders')
    parser.add_argument('-w', '--workers', type=int, help='Parallel threads')
    parser.add_argument('--height', type=int, help='Target height')
    parser.add_argument('--desktop-log', action='store_true', help='Log to Desktop')
    parser.add_argument('--codec', choices=['auto', 'h264_nvenc', 'h264_amf', 'h264_qsv', 'h264_videotoolbox', 'h264_vaapi', 'libx264'], default='auto')
    args = parser.parse_args()

    context = build_run_context(args, parser)
    ffmpeg_state = load_ffmpeg_state()
    update_runtime_state(context)

    log_file = setup_logging(desktop_mode=context.session_config.get('desktop_log', False))
    log_msg = str(log_file)
    show_security_notice(
        log_msg,
        DRIVE_REMOVABLE if context.session_config.get("show_drive_warnings", True) and context.removable_targets else None,
    )
    prompt_stale_ffmpeg_cleanup(ffmpeg_state)

    worker_override = args.workers is not None
    while True:
        log_file = setup_logging(desktop_mode=context.session_config.get("desktop_log", False))
        videos, total_in, skipped_pre = scan_videos_for_context(context, worker_override=worker_override)
        update_runtime_state(context)

        rescue_ok = audit_orphaned_backups(
            recursive=RUNTIME_STATE["recursive"],
            auto_cleanup=RUNTIME_STATE["auto_cleanup"],
            target_dirs=RUNTIME_STATE["target_dirs"],
        )
        if not rescue_ok:
            print(f" {C.ERROR}[!] Resolve orphaned backups interactively before continuing.{C.RESET}")
            return 1

        if not videos:
            clear_screen()
            print(draw_logo())
            if context.invalid_inputs:
                print(f" {C.WARNING}Ignored {len(context.invalid_inputs)} unsupported or missing input(s).{C.RESET}")
            if context.is_explicit_file_mode:
                print(f" {C.WARNING}No supported dropped video files were found.{C.RESET}")
                return 1
            if interactive_mode:
                if safe_input(f" {C.WARNING}No videos found. Press ENTER to retry...{C.RESET}", "q") == "q":
                    return 1
                continue
            print(f" {C.WARNING}No videos found in non-interactive mode. Exiting cleanly.{C.RESET}")
            return 1

        render_run_summary(context, videos, total_in, skipped_pre)
        process_space_needed = max(PROCESS_SPACE_MIN_BYTES, int(total_in * PROCESS_SPACE_MULTIPLIER))
        space_targets = list(iter_unique_target_dirs(target_dirs=[video.parent for video in videos]))
        low_space = [target for target in space_targets if not warn_if_space_is_low(target, process_space_needed, "video processing")]
        if low_space and not interactive_mode:
            return 1
        if low_space:
            answer = safe_input(f" {C.WARNING}Low free space detected. Continue anyway? (Y/N): {C.RESET}", "n").strip().lower()
            if answer not in {"y", "yes"}:
                return 1
        if not interactive_mode:
            logging.info("Non-interactive stdin detected; starting immediately with the current configuration.")
            break

        if context.is_explicit_file_mode:
            ans = safe_input(
                f"\n {C.SUCCESS}CONFIRM DRAG-AND-DROP RUN.{C.RESET} Press ENTER to confirm, 'E' to edit, 'S' to save, 'C' to cancel: ",
                "c",
            ).lower().strip()
            if ans == 'e':
                edit_session_settings(context, ffmpeg_state)
                continue
            if ans == 's':
                if save_config(context.session_config) and persist_ffmpeg_preferences(context.ffmpeg_preferences, ffmpeg_state):
                    print(f" {C.SUCCESS}[+] Settings saved for future runs.{C.RESET}")
                else:
                    print(f" {C.ERROR}[!] Settings could not be saved. Check write permissions.{C.RESET}")
                time.sleep(1)
                continue
            if ans == 'c':
                return 0
        else:
            ans = safe_input(
                f"\n {C.SUCCESS}READY TO ENGAGE.{C.RESET} Press ENTER to start, 'E' to edit, 'S' to save, 'Q' to quit: ",
                "q",
            ).lower().strip()
            if ans in {'e', 'n'}:
                edit_session_settings(context, ffmpeg_state)
                continue
            if ans == 's':
                if save_config(context.session_config) and persist_ffmpeg_preferences(context.ffmpeg_preferences, ffmpeg_state):
                    print(f" {C.SUCCESS}[+] Settings saved for future runs.{C.RESET}")
                else:
                    print(f" {C.ERROR}[!] Settings could not be saved. Check write permissions.{C.RESET}")
                time.sleep(1)
                continue
            if ans == 'q':
                return 0
        break

    if not ensure_ffmpeg(
        context.ffmpeg_preferences.get("auto_download"),
        system_ffmpeg_policy=context.session_config.get("system_ffmpeg_policy"),
        storage_mode=context.ffmpeg_preferences.get("storage_mode"),
        custom_install_path=context.ffmpeg_preferences.get("custom_install_path"),
        ffmpeg_state=ffmpeg_state,
    ):
        return 1
    codec, codec_name = detect_gpu_codec(args.codec)

    start_t = time.time(); success = 0; failed = 0; skipped = 0
    clear_screen(); hide_cursor()
    try:
        with ThreadPoolExecutor(max_workers=context.session_config['max_workers']) as executor:
            futures = {
                executor.submit(
                    process_video,
                    (i % context.session_config['max_workers']) + 1,
                    v,
                    codec,
                    context.session_config,
                ): v
                for i, v in enumerate(videos)
            }
            while any(not f.done() for f in futures):
                completed = sum(1 for f in futures if f.done())
                update_display(len(videos), completed, codec_name, context.session_config)
                time.sleep(0.5)
            update_display(len(videos), len(videos), codec_name, context.session_config)
            for f in futures:
                res = f.result()
                if res == 1: success += 1
                elif res == 2: skipped += 1
                else: failed += 1
    finally:
        show_cursor()

    end_t = time.time(); total_t = end_t - start_t
    total_out = sum(v.stat().st_size for v in videos if v.exists())
    saved = total_in - total_out
    
    clear_screen(); print(draw_header(context.session_config, codec_name)); w = 70
    draw_separator(w, 'top'); draw_box_line("FINAL MISSION REPORT", w, C.BOLD + C.SUCCESS); draw_separator(w, 'mid')
    draw_box_line(f"Status: {success} Success | {skipped} Skipped | {failed} Failed", w)
    draw_box_line(f"Time: {int(total_t//60)}m {int(total_t%60)}s | Space Saved: {saved/1024/1024:.1f} MB", w)
    draw_separator(w, 'bot')
    if RUNTIME_STATE["auto_cleanup"]:
        cleanup_temp_files(
            recursive=RUNTIME_STATE["recursive"],
            include_current_session=True,
            target_dirs=RUNTIME_STATE["target_dirs"],
        )
    if failed:
        print(f"\n {C.WARNING}Mission completed with failures. Review the log before running on originals again.{C.RESET}")
    else:
        print(f"\n {C.SUCCESS}All operations completed successfully.{C.RESET}")
    return 0 if failed == 0 else 2

if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt:
        handle_interrupt()
    except Exception as e:
        logging.critical(f"FATAL: {e}"); logging.debug(traceback.format_exc())
        print(f"\n\n {C.ERROR}[X] Fatal error. Check logs.{C.RESET}"); sys.exit(1)
