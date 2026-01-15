# -*- coding: utf-8 -*-
"""
Mnemosyne V1.0 - The Keeper of Digital Memory
Copyright (C) 2026 Mejensi
Licensed under GNU GPL v3.0

This software relies on FFmpeg (https://ffmpeg.org) for video processing.
FFmpeg is licensed under the LGPL/GPL.
"""
import os, sys, platform, subprocess, shutil, time, datetime, json, argparse, threading, traceback, logging, random
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Tuple, Dict, List
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
    except: pass

VERSION, APP_NAME = "1.0", "Mnemosyne"
SYSTEM, IS_WINDOWS = platform.system(), platform.system() == "Windows"

# Setup Paths
if IS_WINDOWS:
    APP_DATA = Path(os.environ["APPDATA"]) / APP_NAME
else:
    APP_DATA = Path.home() / ".mnemosyne"

LOG_DIR = APP_DATA / "logs"
BIN_DIR = Path("bin")
CONFIG_FILE = Path("config.json")

# Configuration
DEFAULT_CONFIG = {
    "target_height": 480,
    "video_bitrate": "800k",
    "audio_bitrate": "128k",
    "target_fps": 30,
    "max_workers": max(1, os.cpu_count() // 2) if os.cpu_count() else 2,
    "recursive": False,
    "verify_frames": True,
    "auto_download_ffmpeg": True,
    "sort": "name_az",
    "desktop_log": True,
    "auto_cleanup": True,
    "show_drive_warnings": True,
    "preserve_metadata": True
}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m4v'}
LOCK = threading.Lock()

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
            for p in self.active_procs:
                try:
                    p.terminate()
                    try: p.wait(timeout=2)
                    except subprocess.TimeoutExpired: p.kill()
                except: pass
PROCESS_MGR = ProcessManager()

if IS_WINDOWS:
    DRIVE_FIXED = 3
    DRIVE_REMOVABLE = 2

# Aesthetics & UI
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
BOX = {
    'tl': '\u2554', # ╔
    'tr': '\u2557', # ╗
    'bl': '\u255a', # ╚
    'br': '\u255d', # ╝
    'h':  '\u2550', # ═
    'v':  '\u2551', # ║
    'ml': '\u2560', # ╠
    'mr': '\u2563'  # ╣
}

ASCII_ART = r"""
 __  __                                                    
|  \/  |____   ___ ____ ___   ___  ___ _   _ _ __   ___   
| |\/| | '_ \ / _ \ '_ ` _ \ / _ \/ __| | | | '_ \ / _ \  
| |  | | | | |  __/ | | | | | (_) \__ \ |_| | | | |  __/  
|_|  |_|_| |_|\___|_| |_| |_|\___/|___/\__, |_| |_|\___|  
                                       |___/ v{version}
"""

INFO_TICKER = [
    "✦ FFmpeg powers 90% of the world's video streaming.",
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
    "◈ Smart codec detection automatically selects best encoder.",
    "➤ Removable drive safety: Warnings prevent accidental disconnection."
]

# Logging setup
def setup_logging(debug=False, desktop_mode=False):
    if desktop_mode:
        desktop = Path.home() / "Desktop"
        if not desktop.exists(): desktop = Path.home()
        log_file = desktop / "Mnemosyne_Log.txt"
    else:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / "mnemosyne.log"
    
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    logger.handlers.clear()
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
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
    except: pass

def reset_cursor():
    # Home cursor and clear everything below it to prevent ghosting
    sys.stdout.write("\033[H")
    sys.stdout.flush()

def hide_cursor(): sys.stdout.write("\033[?25l"); sys.stdout.flush()
def show_cursor(): sys.stdout.write("\033[?25h"); sys.stdout.flush()

def clear_screen(): os.system('cls' if IS_WINDOWS else 'clear')

def get_drive_type(path):
    if not IS_WINDOWS: return 3
    try:
        import ctypes
        root = os.path.splitdrive(path)[0] + "\\"
        return ctypes.windll.kernel32.GetDriveTypeW(root)
    except: return 3 

def cleanup_temp_files(work_dir=None):
    work_dir = Path(work_dir) if work_dir else Path.cwd()
    count = 0
    for p in ["mnemosyne_tmp_*", "temp_*"]:
        for f in work_dir.glob(p):
            if p == "temp_*" and f.suffix.lower() not in VIDEO_EXTENSIONS: continue
            try: f.unlink(); count += 1
            except: pass
    return count

def audit_orphaned_backups():
    cwd = Path.cwd()
    t_count = cleanup_temp_files(cwd)
    if t_count > 0: print(f" {C.INFO}[+] Auto-cleaned {t_count} temporary file(s).{C.RESET}")
    baks = list(cwd.glob("*.bak"))
    if not baks:
        if t_count == 0: print(f" {C.SUCCESS}[+] HEALTH CHECK: System is clean.{C.RESET}")
        return
    print(f" {C.WARNING}[!] GLOBAL RESCUE: Found {len(baks)} orphaned backup files.{C.RESET}")
    ans = input(f" {C.PRIMARY}>> Restore (R) originals or Purge (P) backups? (R/P/Skip): {C.RESET}").lower()
    if ans == 'p':
        for b in baks: b.unlink()
        print(f" {C.SUCCESS}[+] Diagnostic Health Check [OK]{C.RESET}")
    elif ans == 'r':
        for b in baks:
            orig = b.with_suffix('')
            if orig.exists(): orig.unlink()
            b.rename(orig)
        print(f" {C.SUCCESS}[+] Restored {len(baks)} file(s).{C.RESET}")

def load_config():
    config = DEFAULT_CONFIG.copy()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config.update(json.load(f))
        except: pass
    return config

def save_config(config):
    try:
        to_save = {k: v for k, v in config.items() if k in DEFAULT_CONFIG}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(to_save, f, indent=4, ensure_ascii=False)
        return True
    except: return False

def draw_box_line(text, width=70, color=C.WHITE, align='center'):
    # Standard character width calculation (no wide emojis = stable 1:1 width)
    if align == 'center': stripped = text.center(width)
    elif align == 'left': stripped = text.ljust(width)
    else: stripped = text.rjust(width)
    print(f" {C.PRIMARY}{BOX['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{BOX['v']}{C.RESET}")

def draw_separator(width=70, type='mid'):
    if type == 'top': l, r, m = BOX['tl'], BOX['tr'], BOX['h']
    elif type == 'bot': l, r, m = BOX['bl'], BOX['br'], BOX['h']
    else: l, r, m = BOX['ml'], BOX['mr'], BOX['h']
    print(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")

def get_ticker_msg():
    idx = int(time.time() / 15) % len(INFO_TICKER)
    return INFO_TICKER[idx]

def draw_header(config, codec_name):
    output = []
    # ASCII Art with version
    ascii_with_version = ASCII_ART.format(version=VERSION)
    for line in ascii_with_version.strip('\n').split('\n'):
        if line.strip(): output.append(f"{C.PRIMARY} {line}{C.RESET}")
    output.append("")
    
    width = 70
    l, r, m = BOX['tl'], BOX['tr'], BOX['h']
    output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
    
    def box_line(text, color=C.WHITE, align='center'):
        if align == 'center': stripped = text.center(width)
        elif align == 'left': stripped = text.ljust(width)
        else: stripped = text.rjust(width)
        return f" {C.PRIMARY}{BOX['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{BOX['v']}{C.RESET}"

    output.append(box_line(f"The Keeper of Digital Memory v{VERSION}", C.BOLD + C.WHITE))
    
    l, r, m = BOX['ml'], BOX['mr'], BOX['h']
    sep = f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}"
    output.append(sep)
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
    
    l, r, m = BOX['bl'], BOX['br'], BOX['h']
    output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
    return "\n".join(output)

def render_progress(label, percent, fps, speed, size_stats, eta=""):
    w = 30
    f, e = int(w * percent / 100), w - int(w * percent / 100)
    bar_char, bg_char = '\u2588', '\u2591'
    check_icon, arrow_icon, pipe_icon = '\u2713', '\u27a4', '\u2514\u2500'
    
    if percent >= 100: bar_color = C.SUCCESS
    elif percent >= 50: bar_color = C.INFO
    else: bar_color = C.PRIMARY
    
    bar = f"{bar_color}{bar_char*f}{C.RESET}{C.MUTED}{bg_char*e}{C.RESET}"
    if percent >= 100:
        return f" {C.SUCCESS}{check_icon}{C.RESET} {C.WHITE}{label:<20}{C.RESET} {bar} {C.SUCCESS}DONE{C.RESET}\n   {C.MUTED}{pipe_icon} {size_stats}{C.RESET}"
    else:
        fps_disp = fps if fps != "-" else "..."
        spd_disp = speed if speed != "0X" else "..."
        eta_disp = f" | {eta}" if eta else ""
        return f" {C.PRIMARY}{arrow_icon}{C.RESET} {C.WHITE}{label:<20}{C.RESET} {bar} {C.INFO}{percent:5.1f}%{C.RESET}\n   {C.MUTED}{pipe_icon} {spd_disp} | {fps_disp} fps{eta_disp}{C.RESET}"

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

# Helper functions (metadata, ffmpeg)
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
        except: pass

FFMPEG_URLS = {"Windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", "Linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz", "Darwin": "https://evermeet.cx/ffmpeg/getrelease/zip"}

def check_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"): return True
    ffmpeg_bin = BIN_DIR / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
    ffprobe_bin = BIN_DIR / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
    if ffmpeg_bin.exists() and ffprobe_bin.exists():
        os.environ["PATH"] = str(BIN_DIR.absolute()) + os.pathsep + os.environ["PATH"]
        return True
    return False

def download_ffmpeg():
    url = FFMPEG_URLS.get(platform.system())
    if not url: return False
    BIN_DIR.mkdir(exist_ok=True)
    archive_ext = ".zip" if platform.system() in ["Windows", "Darwin"] else ".tar.xz"
    archive_path = BIN_DIR / f"ffmpeg{archive_ext}"
    print(f"\n{C.INFO}[DOWNLOAD] Fetching FFmpeg...{C.RESET}")
    try:
        import urllib.request
        def reporthook(b, b_size, total):
            if total > 0:
                pct = min(100, (b * b_size / total) * 100)
                bar = '█' * int(40 * pct / 100) + '░' * (40 - int(40 * pct / 100))
                print(f"\r{C.INFO}[PROGRESS]{C.RESET} {bar} {pct:5.1f}%", end='', flush=True)
        urllib.request.urlretrieve(url, archive_path, reporthook=reporthook)
        print(f"\n{C.INFO}[EXTRACT] Extracting binaries...{C.RESET}")
        if archive_ext == ".zip":
            import zipfile
            with zipfile.ZipFile(archive_path, 'r') as z:
                for m in z.namelist():
                    fn = os.path.basename(m)
                    if fn.lower() in ["ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"]:
                        with z.open(m) as src, open(BIN_DIR / fn, 'wb') as tgt:
                            shutil.copyfileobj(src, tgt)
                        if platform.system() != "Windows": (BIN_DIR / fn).chmod(0o755)
        else:
            import tarfile
            with tarfile.open(archive_path, 'r:xz') as tar:
                for m in tar.getmembers():
                    if m.name.endswith(("ffmpeg", "ffprobe")):
                        m.name = os.path.basename(m.name)
                        tar.extract(m, path=BIN_DIR)
                        (BIN_DIR / m.name).chmod(0o755)
        archive_path.unlink()
        os.environ["PATH"] = str(BIN_DIR.absolute()) + os.pathsep + os.environ["PATH"]
        return True
    except: return False

def ensure_ffmpeg(auto_download=True):
    if check_ffmpeg(): return True
    print(f"\n{C.WARNING} \u26a0  FFmpeg Not Found{C.RESET}\n")
    if not auto_download:
        if input(f"{C.PRIMARY}>> Download FFmpeg automatically? (Y/N): {C.RESET}").lower() != 'y': return False
    return download_ffmpeg()

def detect_gpu_codec(force_codec=None):
    if force_codec and force_codec != 'auto':
        try:
            r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5)
            if force_codec in r.stdout: return (force_codec, f"{force_codec.upper()} [FORCED]")
        except: pass
    try:
        r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5)
        e = r.stdout
        if "h264_nvenc" in e: return ("h264_nvenc", "NVIDIA (NVENC)")
        elif "h264_qsv" in e: return ("h264_qsv", "Intel QuickSync")
        elif "h264_videotoolbox" in e: return ("h264_videotoolbox", "Apple VideoToolbox")
        elif "h264_vaapi" in e: return ("h264_vaapi", "VAAPI")
        else: return ("libx264", "CPU (x264)")
    except: return ("libx264", "CPU (x264)")

worker_stats = WorkerStats()

def verify_output(inp, outp):
    if not outp.exists() or outp.stat().st_size < 10240: return False
    try:
        def get_meta(p):
            cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=nb_frames,width,height", "-of", "csv=p=0", str(p)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            parts = r.stdout.strip().split(',')
            return float(parts[0] if parts[0] else 0), int(parts[1] if len(parts) > 1 and parts[1] else -1)
        in_d, in_f = get_meta(inp)
        out_d, out_f = get_meta(outp)
        dur_ok = abs(in_d - out_d) < 2.0
        frm_ok = (in_f == -1 or out_f == -1 or abs(in_f - out_f) < 150)
        return dur_ok and frm_ok
    except: return False

def process_video(wid, vpath, codec, config):
    fn = vpath.name
    s_fps, s_speed, pct = "-", "0X", 0.0
    worker_stats.update(wid, fn, 0.0, s_fps, s_speed, "")
    logging.info(f"[Worker {wid}] Started processing: {fn}")
    try:
        meta = get_file_metadata(vpath)
        start_size = vpath.stat().st_size
        tmp = vpath.parent / f"mnemosyne_tmp_{wid}_{fn}"
        try:
            dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vpath)], capture_output=True, text=True).stdout.strip() or 1.0)
        except: dur = 1.0
        # Build command with Conditional Logic for Hardware vs Software Encoders
        cmd = ["ffmpeg", "-nostdin", "-y", "-i", str(vpath), "-c:v", codec]
        
        # 1. NVENC (NVIDIA): Use Constant Quality (CQ) mode
        if "nvenc" in codec:
            cmd.extend(["-rc", "vbr", "-cq", "24", "-preset", "p4"])
        # 2. CPU (libx264): Use Target Bitrate + Medium Preset
        elif "libx264" in codec:
            cmd.extend(["-b:v", config['video_bitrate'], "-preset", "medium"])
        # 3. Universal Safety Mode (Intel QSV, AMD, Apple, etc.): Use Bitrate Only
        # avoid specific presets that might crash other hardware encoders
        else:
            cmd.extend(["-b:v", config['video_bitrate']])

        # Common parameters (FPS, Audio, Resize, Metadata)
        cmd.extend([
            "-r", str(config['target_fps']),
            "-vf", f"scale=-2:{config['target_height']}",
            "-c:a", "aac", "-b:a", config['audio_bitrate'],
            "-metadata", f"encoder={APP_NAME} v{VERSION}",
            "-progress", "-", "-nostats", str(tmp)
        ])
        
        if IS_WINDOWS:
            # CREATE_NEW_PROCESS_GROUP = 0x00000200
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=0x00000200)
        else:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
        PROCESS_MGR.register(proc)
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None: break
            if "out_time=" in line:
                try:
                    ts = line.split("out_time=")[1].split()[0]
                    h, m, s = map(float, ts.split(':'))
                    new_pct = min(99.9, ((h*3600 + m*60 + s) / dur) * 100); pct = new_pct
                    worker_stats.update(wid, fn, pct, s_fps, s_speed)
                except: pass
            elif "fps=" in line:
                try:
                    s_fps = line.split("fps=")[1].split()[0]
                    s_speed = line.split("speed=")[1].split()[0]
                    worker_stats.update(wid, fn, pct, s_fps, s_speed)
                except: pass
        PROCESS_MGR.unregister(proc)
        if proc.returncode != 0:
            if codec != "libx264":
                logging.warning(f"Hardware encoding failed for {fn}, falling back to CPU")
                worker_stats.update(wid, fn, 0.0, "-", "0X", "Retrying with CPU...")
                return process_video(wid, vpath, "libx264", config)
            return False

        if config['verify_frames'] and not verify_output(vpath, tmp): return False
        
        end_size = tmp.stat().st_size
        size_diff = (1 - (end_size / start_size)) * 100
        size_stats = f"{start_size/1024/1024:.1f}MB -> {end_size/1024/1024:.1f}MB ({size_diff:.0f}% saved)"
        
        bak = vpath.with_suffix(vpath.suffix + '.bak')
        if bak.exists(): bak.unlink()
        try:
            vpath.rename(bak)
            tmp.rename(vpath)
            restore_file_metadata(vpath, meta)
            if vpath.exists() and vpath.stat().st_size > 10240: bak.unlink()
            else: raise Exception("Output verification fail after swap")
        except Exception as e:
            logging.error(f"File swap error: {e}")
            if bak.exists() and not vpath.exists(): bak.rename(vpath)
            return False
            
        worker_stats.update(wid, fn, 100.0, "0", "0", size_stats)
        return True
    except Exception as e:
        logging.error(f"Process error for {fn}: {e}")
        if 'tmp' in locals() and tmp.exists(): tmp.unlink()
        return False

def update_display(total, codec_name, config):
    header = draw_header(config, codec_name)
    buffer = [""] # Leading newline to separate from logo
    stats = worker_stats.get_all()
    completed = sum(1 for s in stats.values() if s['pct'] >= 100)
    in_progress = len([s for s in stats.values() if 0 < s['pct'] < 100])
    
    for wid in sorted(stats.keys()):
        s = stats[wid]
        fn_short = s['fn'][:25] + "..." if len(s['fn']) > 28 else s['fn']
        eta_str = ""
        if 0 < s['pct'] < 100 and 'start' in s:
            elapsed = time.time() - s['start']
            if s['pct'] > 1:
                rem = (elapsed / (s['pct'] / 100)) - elapsed
                m, s_v = divmod(int(rem), 60); eta_str = f"ETA: {m}m {s_v}s"
        buffer.append(render_progress(fn_short, s['pct'], s['fps'], s['speed'], s['size'], eta_str))
        buffer.append("")
        
    buffer.append(f" {C.WHITE}{'='*70}{C.RESET}")
    o_pct = (completed / total * 100) if total > 0 else 0
    buffer.append(f" {C.WHITE}Total: {total} | {C.SUCCESS}Done: {completed} | {C.INFO}Active: {in_progress} | {o_pct:.1f}%{C.RESET}")
    
    # Send as one atomic write to terminal
    sys.stdout.write("\033[H" + header + "\n".join(buffer) + "\033[J")
    sys.stdout.flush()

def show_security_notice(log_msg, drive_type=None):
    clear_screen(); w = 70
    draw_separator(w, 'top')
    draw_box_line("SECURITY & TRANSPARENCY", w, C.BOLD + C.PRIMARY)
    draw_separator(w, 'mid')
    if drive_type == 2: # REMOVABLE
        draw_box_line("\u26a0  REMOVABLE MEDIA DETECTED", w, C.BOLD + C.WARNING)
        draw_box_line("IMPORTANT: Keep the device connected to prevent data loss.", w, C.WARNING)
        draw_separator(w, 'mid')
    draw_box_line("1. Local Processing: No data ever leaves your computer.", w, C.WHITE)
    draw_box_line(f"2. Logs: {log_msg}", w, C.WHITE)
    draw_box_line("3. Open Source: Full code transparency (GNU GPL v3.0)", w, C.WHITE)
    draw_box_line("4. Atomic Safety: Temporary files used to prevent data loss.", w, C.WHITE)
    draw_separator(w, 'mid')
    draw_box_line("Mnemosyne protects your privacy and your digital memory.", w, C.SUCCESS)
    draw_separator(w, 'bot')
    print(""); input(f" {C.PRIMARY}>> Press ENTER to continue...{C.RESET}")

def main():
    enable_ansi()
    # Signal Handling for Ctrl+C
    import signal
    def signal_handler(sig, frame):
        PROCESS_MGR.kill_all()
        show_cursor()
        print(f"\n\n {C.WARNING}[!] EMERGENCY STOP: Interrupted by user (Signal {sig}).{C.RESET}")
        print(f" {C.SUCCESS}[+] Cleanup complete. You may now exit.{C.RESET}")
        cleanup_temp_files(); sys.exit(130)
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description=f"{APP_NAME} v{VERSION}", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-r', '--recursive', action='store_true', help='Search subfolders')
    parser.add_argument('-w', '--workers', type=int, help='Parallel threads')
    parser.add_argument('--height', type=int, help='Target height')
    parser.add_argument('--desktop-log', action='store_true', help='Log to Desktop')
    parser.add_argument('--codec', choices=['auto', 'h264_nvenc', 'h264_qsv', 'h264_vaapi', 'libx264'], default='auto')
    args = parser.parse_args()

    config = load_config()
    if args.recursive: config['recursive'] = True
    if args.workers: config['max_workers'] = args.workers
    if args.height: config['target_height'] = args.height
    
    desktop_log_mode = args.desktop_log
    if not args.desktop_log:
        clear_screen(); w = 70
        draw_separator(w, 'top'); draw_box_line("LOG PREFERENCE", w, C.BOLD + C.PRIMARY); draw_separator(w, 'mid')
        draw_box_line("Where should Mnemosyne save log files?", w)
        draw_box_line("[1] Desktop", w, C.INFO)
        draw_box_line("[2] AppData", w, C.INFO)
        draw_separator(w, 'bot')
        choice = input(f" {C.PRIMARY}>> Choice [Default=1]: {C.RESET}").strip()
        desktop_log_mode = (choice != '2')

    log_file = setup_logging(desktop_mode=desktop_log_mode)
    log_msg = "Desktop/Mnemosyne_Log.txt" if desktop_log_mode else "AppData/Mnemosyne/logs"
    
    drive_type = get_drive_type(str(Path.cwd()))
    show_security_notice(log_msg, drive_type)
    audit_orphaned_backups()
    
    if not ensure_ffmpeg(config['auto_download_ffmpeg']): return 1
    codec, codec_name = detect_gpu_codec(args.codec)

    def get_input(prompt, default_val, valid_choices=None):
        suffix = f" [Default={default_val}]: "
        while True:
            user_in = input(f" {C.PRIMARY}>> {prompt}{suffix}{C.RESET}").strip()
            val = user_in if user_in else default_val
            if not valid_choices or val in valid_choices:
                return val
            print(f" {C.ERROR}[!] Invalid choice '{val}'. Please select from {', '.join(valid_choices)}.{C.RESET}")

    while True:
        clear_screen(); print(draw_header(config, codec_name))
        
        # 1. Strategy
        print(f" {C.PRIMARY}[BOOT] Strategy:{C.RESET}")
        print(f"    [1] Local Folder  [2] Deep Scan (Recursive)")
        curr_rec = '2' if config['recursive'] else '1'
        strat = get_input("Choice", curr_rec, ['1', '2'])
        config['recursive'] = (strat == '2')
        
        # 2. Priority
        print(f"\n {C.PRIMARY}[BOOT] Priority:{C.RESET}")
        print(f"    [1] Name A-Z  [2] Name Z-A  [3] Largest  [4] Smallest")
        curr_sort = '1'
        if config['sort'] == 'name_za': curr_sort = '2'
        elif config['sort'] == 'size_desc': curr_sort = '3'
        elif config['sort'] == 'size_asc': curr_sort = '4'
        
        sort_opt = get_input("Choice", curr_sort, ['1', '2', '3', '4'])
        if sort_opt == '2': config['sort'] = 'name_za'
        elif sort_opt == '3': config['sort'] = 'size_desc'
        elif sort_opt == '4': config['sort'] = 'size_asc'
        else: config['sort'] = 'name_az'

        # 3. Engine Mode
        print(f"\n {C.PRIMARY}[BOOT] Engine Mode:{C.RESET}")
        print(f"    [1] Sequential  [2] Parallel  [3] Custom Workers")
        curr_mode = '2'
        if config['max_workers'] == 1: curr_mode = '1'
        
        mode_opt = get_input("Choice", curr_mode, ['1', '2', '3'])
        if mode_opt == '1': config['max_workers'] = 1
        elif mode_opt == '3':
            try: 
                w_in = input(f" {C.PRIMARY}>> Workers (1-{os.cpu_count()}) [Current={config['max_workers']}]: {C.RESET}")
                config['max_workers'] = int(w_in) if w_in else config['max_workers']
            except: pass # Keep existing on error
        elif mode_opt == '2':
             # Restore default parallel limit if switching back to parallel from sequential
             if config['max_workers'] == 1:
                 config['max_workers'] = DEFAULT_CONFIG['max_workers']

        print(f"\n {C.INFO}[SCAN] Scanning for videos...{C.RESET}")
        videos = []; cwd = Path.cwd()
        pattern = cwd.rglob if config['recursive'] else cwd.glob
        for ext in VIDEO_EXTENSIONS: videos.extend(list(pattern(f"*{ext}")))
        videos = [v for v in videos if not any(x in v.parts for x in ["bin", "logs"])]
        if not videos:
            input(f" {C.WARNING}No videos found. Press ENTER to retry...{C.RESET}"); continue
        
        if config['sort'] == 'name_az': videos.sort()
        elif config['sort'] == 'name_za': videos.sort(reverse=True)
        elif config['sort'] == 'size_desc': videos.sort(key=lambda x: x.stat().st_size, reverse=True)
        elif config['sort'] == 'size_asc': videos.sort(key=lambda x: x.stat().st_size)

        clear_screen(); print(draw_header(config, codec_name)); w = 70
        total_in = sum(v.stat().st_size for v in videos)
        draw_separator(w, 'top'); draw_box_line("MISSION BRIEFING", w, C.BOLD + C.PRIMARY); draw_separator(w, 'mid')
        draw_box_line(f"Queue: {len(videos)} videos | Size: {total_in/1024/1024:.1f} MB", w)
        if drive_type == 2: draw_box_line("Drive: REMOVABLE MEDIA (Caution)", w, C.WARNING)
        draw_box_line(f"Codec: {codec_name} | Mode: {'Parallel' if config['max_workers']>1 else 'Sequential'}", w)
        draw_separator(w, 'bot')
        
        ans = input(f"\n {C.SUCCESS}READY TO ENGAGE.{C.RESET} Press ENTER to start, 'N' to re-config, 'S' to save: ").lower().strip()
        if ans == 'n': continue
        if ans == 's': save_config(config); print(f" {C.SUCCESS}[+] Settings saved.{C.RESET}"); time.sleep(1); continue
        if ans == 'q': return 0
        break

    start_t = time.time(); success = 0; failed = 0
    clear_screen(); hide_cursor()
    try:
        with ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
            futures = {executor.submit(process_video, (i % config['max_workers']) + 1, v, codec, config): v for i, v in enumerate(videos)}
            while any(not f.done() for f in futures):
                update_display(len(videos), codec_name, config); time.sleep(0.5)
            for f in futures:
                if f.result(): success += 1
                else: failed += 1
    finally:
        show_cursor()

    end_t = time.time(); total_t = end_t - start_t
    total_out = sum(v.stat().st_size for v in videos if v.exists())
    saved = total_in - total_out
    
    clear_screen(); print(draw_header(config, codec_name)); w = 70
    draw_separator(w, 'top'); draw_box_line("FINAL MISSION REPORT", w, C.BOLD + C.SUCCESS); draw_separator(w, 'mid')
    draw_box_line(f"Status: {success} Success | {failed} Failed", w)
    draw_box_line(f"Time: {int(total_t//60)}m {int(total_t%60)}s | Space Saved: {saved/1024/1024:.1f} MB", w)
    draw_separator(w, 'bot')
    cleanup_temp_files()
    print(f"\n {C.SUCCESS}All operations completed successfully.{C.RESET}")
    return 0

if __name__ == "__main__":
    try: sys.exit(main())
    except KeyboardInterrupt:
        PROCESS_MGR.kill_all()
        show_cursor()
        print(f"\n\n {C.WARNING}[!] EMERGENCY STOP: Interrupted by user.{C.RESET}")
        print(f" {C.SUCCESS}[+] Operations terminated. Original videos are safe, you may now exit.{C.RESET}")
        cleanup_temp_files(); sys.exit(130)
    except Exception as e:
        logging.critical(f"FATAL: {e}"); logging.debug(traceback.format_exc())
        print(f"\n\n {C.ERROR}[X] Fatal error. Check logs.{C.RESET}"); sys.exit(1)
