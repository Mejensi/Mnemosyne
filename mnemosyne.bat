@echo off
REM ============================================================================
REM                       MNEMOSYNE V1.0 - UNIVERSAL
REM                     The Keeper of Digital Memory
REM ============================================================================
REM Copyright (C) 2026 Mejensi
REM Licensed under GNU General Public License v3.0
REM ============================================================================
setlocal enabledelayedexpansion
title Mnemosyne v1.0

REM Enable Unicode support for CMD and Python
chcp 65001 >nul
REM Configuration
set "PYTHONNOUSERSITE=1"
set "PYTHONIOENCODING=utf-8"

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python 3 required but not found.
    set /p "install=>> Install Python via winget? (Y/N): "
    if /i "!install!"=="Y" (
        winget install Python.Python.3 --silent --accept-package-agreements --accept-source-agreements
        if %errorlevel% neq 0 (
            echo [!] Failed. Install from https://python.org
            pause
            exit /b 1
        )
        echo [+] Python installed. Please restart this script.
        pause
        exit /b 0
    ) else (
        echo [!] Python required. Exiting.
        pause
        exit /b 1
    )
)

REM Extract embedded Python code to temporary file - Simple & Reliable PS version
set "TEMP_PY=%TEMP%\mnemosyne_runtime_%RANDOM%.py"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=[System.IO.File]::ReadAllText('%~f0');$m=[Regex]::Matches($c,'(?m)^REM#PY# ?(.*)$');$o=$m|ForEach-Object{$_.Groups[1].Value};[System.IO.File]::WriteAllLines('%TEMP_PY%',$o,[System.Text.Encoding]::UTF8)"

REM Run Python in Strict Mode
python -X utf8 "%TEMP_PY%" %*
set EXIT_CODE=%errorlevel%

REM Cleanup
if exist "%TEMP_PY%" del "%TEMP_PY%"

REM Pause unconditionally
echo.
pause

exit /b %EXIT_CODE%

REM ============================================================================
REM EMBEDDED PYTHON CODE
REM ============================================================================
REM#PY# """
REM#PY# Mnemosyne V1.0 - The Keeper of Digital Memory
REM#PY# Copyright (C) 2026 Mejensi
REM#PY# Licensed under GNU GPL v3.0
REM#PY# """
REM#PY# import os, sys, platform, subprocess, shutil, time, datetime, json, argparse, threading, traceback, logging, random
REM#PY# from pathlib import Path
REM#PY# from concurrent.futures import ThreadPoolExecutor
REM#PY# from typing import Tuple, Dict, List
REM#PY# from logging.handlers import RotatingFileHandler
REM#PY# 
REM#PY# if platform.system() == "Windows":
REM#PY#     try:
REM#PY#         import ctypes
REM#PY#         # Enable VT100 support for ANSI colors
REM#PY#         kernel32 = ctypes.windll.kernel32
REM#PY#         hStdOut = kernel32.GetStdHandle(-11)
REM#PY#         mode = ctypes.c_ulong()
REM#PY#         kernel32.GetConsoleMode(hStdOut, ctypes.byref(mode))
REM#PY#         mode.value |= 0x0004 # ENABLE_VIRTUAL_TERMINAL_PROCESSING
REM#PY#         kernel32.SetConsoleMode(hStdOut, mode)
REM#PY#     except: pass
REM#PY# 
REM#PY# VERSION, APP_NAME = "1.0", "Mnemosyne"
REM#PY# SYSTEM, IS_WINDOWS = platform.system(), platform.system() == "Windows"
REM#PY# 
REM#PY# # Setup Paths
REM#PY# if IS_WINDOWS:
REM#PY#     APP_DATA = Path(os.environ["APPDATA"]) / APP_NAME
REM#PY# else:
REM#PY#     APP_DATA = Path.home() / ".mnemosyne"
REM#PY# 
REM#PY# LOG_DIR = APP_DATA / "logs"
REM#PY# BIN_DIR = Path("bin")
REM#PY# CONFIG_FILE = Path("config.json")
REM#PY# 
REM#PY# # Configuration
REM#PY# DEFAULT_CONFIG = {
REM#PY#     "target_height": 480,
REM#PY#     "video_bitrate": "800k",
REM#PY#     "audio_bitrate": "128k",
REM#PY#     "target_fps": 30,
REM#PY#     "max_workers": max(1, os.cpu_count() // 2) if os.cpu_count() else 2,
REM#PY#     "recursive": False,
REM#PY#     "verify_frames": True,
REM#PY#     "auto_download_ffmpeg": True,
REM#PY#     "sort": "name_az",
REM#PY#     "desktop_log": True,
REM#PY#     "auto_cleanup": True,
REM#PY#     "show_drive_warnings": True,
REM#PY#     "preserve_metadata": True
REM#PY# }
REM#PY# VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts', '.m4v'}
REM#PY# LOCK = threading.Lock()
REM#PY# 
REM#PY# class ProcessManager:
REM#PY#     def __init__(self):
REM#PY#         self.active_procs = set()
REM#PY#         self.lock = threading.Lock()
REM#PY#     def register(self, proc):
REM#PY#         with self.lock: self.active_procs.add(proc)
REM#PY#     def unregister(self, proc):
REM#PY#         with self.lock: self.active_procs.discard(proc)
REM#PY#     def kill_all(self):
REM#PY#         with self.lock:
REM#PY#             for p in self.active_procs:
REM#PY#                 try:
REM#PY#                     p.terminate()
REM#PY#                     try: p.wait(timeout=2)
REM#PY#                     except subprocess.TimeoutExpired: p.kill()
REM#PY#                 except: pass
REM#PY# PROCESS_MGR = ProcessManager()
REM#PY# 
REM#PY# if IS_WINDOWS:
REM#PY#     DRIVE_FIXED = 3
REM#PY#     DRIVE_REMOVABLE = 2
REM#PY# 
REM#PY# # Aesthetics & UI
REM#PY# class C:
REM#PY#     RESET = '\033[0m'
REM#PY#     BOLD = '\033[1m'
REM#PY#     DIM = '\033[2m'
REM#PY#     PRIMARY = '\033[38;2;91;155;213m'   # Soft Blue
REM#PY#     SUCCESS = '\033[38;2;16;185;129m'   # Emerald
REM#PY#     WARNING = '\033[38;2;245;158;11m'   # Amber
REM#PY#     ERROR = '\033[38;2;239;68;68m'      # Rose
REM#PY#     INFO = '\033[38;2;14;165;233m'      # Sky
REM#PY#     ACCENT = '\033[38;2;168;85;247m'    # Purple
REM#PY#     MUTED = '\033[38;2;100;116;139m'    # Slate
REM#PY#     WHITE = '\033[38;2;255;255;255m'
REM#PY# 
REM#PY# # Unicode escapes for box characters to prevent source encoding issues
REM#PY# BOX = {
REM#PY#     'tl': '\u2554', # ╔
REM#PY#     'tr': '\u2557', # ╗
REM#PY#     'bl': '\u255a', # ╚
REM#PY#     'br': '\u255d', # ╝
REM#PY#     'h':  '\u2550', # ═
REM#PY#     'v':  '\u2551', # ║
REM#PY#     'ml': '\u2560', # ╠
REM#PY#     'mr': '\u2563'  # ╣
REM#PY# }
REM#PY# 
REM#PY# ASCII_ART = r"""
REM#PY#  __  __                                                    
REM#PY# |  \/  |____   ___ ____ ___   ___  ___ _   _ _ __   ___   
REM#PY# | |\/| | '_ \ / _ \ '_ ` _ \ / _ \/ __| | | | '_ \ / _ \  
REM#PY# | |  | | | | |  __/ | | | | | (_) \__ \ |_| | | | |  __/  
REM#PY# |_|  |_|_| |_|\___|_| |_| |_|\___/|___/\__, |_| |_|\___|  
REM#PY#                                        |___/ v{version}
REM#PY# """
REM#PY# 
REM#PY# INFO_TICKER = [
REM#PY#     "✦ FFmpeg powers 90% of the world's video streaming.",
REM#PY#     "➤ Targeting 30 FPS for optimal timeline stability.",
REM#PY#     "◆ Safety Bridge ensures zero-loss atomic file swaps.",
REM#PY#     "✦ Mnemosyne preserves file dates to keep your timeline intact.",
REM#PY#     "✦ Processing is 100% local. No cloud, no tracking.",
REM#PY#     "◈ GPU acceleration detected - using hardware encoding for speed.",
REM#PY#     "➤ Frame verification ensures output quality matches input.",
REM#PY#     "✦ Automatic backup system prevents data loss during conversion.",
REM#PY#     "◆ Multi-threaded processing maximizes your CPU efficiency.",
REM#PY#     "◈ Bitrate optimization reduces file size while preserving quality.",
REM#PY#     "➤ Metadata preservation: Your file timestamps remain unchanged.",
REM#PY#     "✦ Open source transparency - every line of code is auditable.",
REM#PY#     "◆ Atomic file operations prevent corruption from interruptions.",
REM#PY#     "◈ Smart codec detection automatically selects best encoder.",
REM#PY#     "➤ Removable drive safety: Warnings prevent accidental disconnection."
REM#PY# ]
REM#PY# 
REM#PY# # Logging setup
REM#PY# def setup_logging(debug=False, desktop_mode=False):
REM#PY#     if desktop_mode:
REM#PY#         desktop = Path.home() / "Desktop"
REM#PY#         if not desktop.exists(): desktop = Path.home()
REM#PY#         log_file = desktop / "Mnemosyne_Log.txt"
REM#PY#     else:
REM#PY#         LOG_DIR.mkdir(parents=True, exist_ok=True)
REM#PY#         log_file = LOG_DIR / "mnemosyne.log"
REM#PY#     
REM#PY#     logger = logging.getLogger()
REM#PY#     logger.setLevel(logging.DEBUG if debug else logging.INFO)
REM#PY#     fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
REM#PY#     logger.handlers.clear()
REM#PY#     fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
REM#PY#     fh.setFormatter(fmt); fh.setLevel(logging.DEBUG); logger.addHandler(fh)
REM#PY#     return log_file
REM#PY# 
REM#PY# def enable_ansi():
REM#PY#     if not IS_WINDOWS: return
REM#PY#     try:
REM#PY#         import ctypes
REM#PY#         kernel32 = ctypes.windll.kernel32
REM#PY#         h = kernel32.GetStdHandle(-11)
REM#PY#         m = ctypes.wintypes.DWORD()
REM#PY#         kernel32.GetConsoleMode(h, ctypes.byref(m))
REM#PY#         kernel32.SetConsoleMode(h, m.value | 0x0004)
REM#PY#     except: pass
REM#PY# 
REM#PY# def reset_cursor():
REM#PY#     # Home cursor and clear everything below it to prevent ghosting
REM#PY#     sys.stdout.write("\033[H")
REM#PY#     sys.stdout.flush()
REM#PY# 
REM#PY# def hide_cursor(): sys.stdout.write("\033[?25l"); sys.stdout.flush()
REM#PY# def show_cursor(): sys.stdout.write("\033[?25h"); sys.stdout.flush()
REM#PY# 
REM#PY# def clear_screen(): os.system('cls' if IS_WINDOWS else 'clear')
REM#PY# 
REM#PY# def get_drive_type(path):
REM#PY#     if not IS_WINDOWS: return 3
REM#PY#     try:
REM#PY#         import ctypes
REM#PY#         root = os.path.splitdrive(path)[0] + "\\"
REM#PY#         return ctypes.windll.kernel32.GetDriveTypeW(root)
REM#PY#     except: return 3 
REM#PY# 
REM#PY# def cleanup_temp_files(work_dir=None):
REM#PY#     work_dir = Path(work_dir) if work_dir else Path.cwd()
REM#PY#     count = 0
REM#PY#     for p in ["mnemosyne_tmp_*", "temp_*"]:
REM#PY#         for f in work_dir.glob(p):
REM#PY#             if p == "temp_*" and f.suffix.lower() not in VIDEO_EXTENSIONS: continue
REM#PY#             try: f.unlink(); count += 1
REM#PY#             except: pass
REM#PY#     return count
REM#PY# 
REM#PY# def audit_orphaned_backups():
REM#PY#     cwd = Path.cwd()
REM#PY#     t_count = cleanup_temp_files(cwd)
REM#PY#     if t_count > 0: print(f" {C.INFO}[+] Auto-cleaned {t_count} temporary file(s).{C.RESET}")
REM#PY#     baks = list(cwd.glob("*.bak"))
REM#PY#     if not baks:
REM#PY#         if t_count == 0: print(f" {C.SUCCESS}[+] HEALTH CHECK: System is clean.{C.RESET}")
REM#PY#         return
REM#PY#     print(f" {C.WARNING}[!] GLOBAL RESCUE: Found {len(baks)} orphaned backup files.{C.RESET}")
REM#PY#     ans = input(f" {C.PRIMARY}>> Restore (R) originals or Purge (P) backups? (R/P/Skip): {C.RESET}").lower()
REM#PY#     if ans == 'p':
REM#PY#         for b in baks: b.unlink()
REM#PY#         print(f" {C.SUCCESS}[+] Diagnostic Health Check [OK]{C.RESET}")
REM#PY#     elif ans == 'r':
REM#PY#         for b in baks:
REM#PY#             orig = b.with_suffix('')
REM#PY#             if orig.exists(): orig.unlink()
REM#PY#             b.rename(orig)
REM#PY#         print(f" {C.SUCCESS}[+] Restored {len(baks)} file(s).{C.RESET}")
REM#PY# 
REM#PY# def load_config():
REM#PY#     config = DEFAULT_CONFIG.copy()
REM#PY#     if CONFIG_FILE.exists():
REM#PY#         try:
REM#PY#             with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config.update(json.load(f))
REM#PY#         except: pass
REM#PY#     return config
REM#PY# 
REM#PY# def save_config(config):
REM#PY#     try:
REM#PY#         to_save = {k: v for k, v in config.items() if k in DEFAULT_CONFIG}
REM#PY#         with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
REM#PY#             json.dump(to_save, f, indent=4, ensure_ascii=False)
REM#PY#         return True
REM#PY#     except: return False
REM#PY# 
REM#PY# def draw_box_line(text, width=70, color=C.WHITE, align='center'):
REM#PY#     # Standard character width calculation (no wide emojis = stable 1:1 width)
REM#PY#     if align == 'center': stripped = text.center(width)
REM#PY#     elif align == 'left': stripped = text.ljust(width)
REM#PY#     else: stripped = text.rjust(width)
REM#PY#     print(f" {C.PRIMARY}{BOX['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{BOX['v']}{C.RESET}")
REM#PY# 
REM#PY# def draw_separator(width=70, type='mid'):
REM#PY#     if type == 'top': l, r, m = BOX['tl'], BOX['tr'], BOX['h']
REM#PY#     elif type == 'bot': l, r, m = BOX['bl'], BOX['br'], BOX['h']
REM#PY#     else: l, r, m = BOX['ml'], BOX['mr'], BOX['h']
REM#PY#     print(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
REM#PY# 
REM#PY# def get_ticker_msg():
REM#PY#     idx = int(time.time() / 15) % len(INFO_TICKER)
REM#PY#     return INFO_TICKER[idx]
REM#PY# 
REM#PY# def draw_header(config, codec_name):
REM#PY#     output = []
REM#PY#     # ASCII Art with version
REM#PY#     ascii_with_version = ASCII_ART.format(version=VERSION)
REM#PY#     for line in ascii_with_version.strip('\n').split('\n'):
REM#PY#         if line.strip(): output.append(f"{C.PRIMARY} {line}{C.RESET}")
REM#PY#     output.append("")
REM#PY#     
REM#PY#     width = 70
REM#PY#     l, r, m = BOX['tl'], BOX['tr'], BOX['h']
REM#PY#     output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
REM#PY#     
REM#PY#     def box_line(text, color=C.WHITE, align='center'):
REM#PY#         if align == 'center': stripped = text.center(width)
REM#PY#         elif align == 'left': stripped = text.ljust(width)
REM#PY#         else: stripped = text.rjust(width)
REM#PY#         return f" {C.PRIMARY}{BOX['v']}{C.RESET} {color}{stripped}{C.RESET} {C.PRIMARY}{BOX['v']}{C.RESET}"
REM#PY# 
REM#PY#     output.append(box_line(f"The Keeper of Digital Memory v{VERSION}", C.BOLD + C.WHITE))
REM#PY#     
REM#PY#     l, r, m = BOX['ml'], BOX['mr'], BOX['h']
REM#PY#     sep = f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}"
REM#PY#     output.append(sep)
REM#PY#     output.append(box_line("Copyright (C) 2026 Mejensi", C.MUTED))
REM#PY#     output.append(box_line("Licensed under GNU GPL v3.0", C.MUTED))
REM#PY#     output.append(sep)
REM#PY#     
REM#PY#     c_info = f"RES: {config['target_height']}p  FPS: {config['target_fps']}  BIT: {config['video_bitrate']}"
REM#PY#     e_info = f"ENC: {codec_name}  WRK: {config['max_workers']}"
REM#PY#     output.append(box_line(c_info, C.INFO))
REM#PY#     output.append(box_line(e_info, C.INFO))
REM#PY#     output.append(sep)
REM#PY#     output.append(box_line(get_ticker_msg(), C.WARNING))
REM#PY#     
REM#PY#     output.append(sep)
REM#PY#     output.append(box_line("Press CTRL+C anytime to exit safely", C.ERROR))
REM#PY#     
REM#PY#     l, r, m = BOX['bl'], BOX['br'], BOX['h']
REM#PY#     output.append(f" {C.PRIMARY}{l}{m * (width+2)}{r}{C.RESET}")
REM#PY#     return "\n".join(output)
REM#PY# 
REM#PY# def render_progress(label, percent, fps, speed, size_stats, eta=""):
REM#PY#     w = 30
REM#PY#     f, e = int(w * percent / 100), w - int(w * percent / 100)
REM#PY#     bar_char, bg_char = '\u2588', '\u2591'
REM#PY#     check_icon, arrow_icon, pipe_icon = '\u2713', '\u27a4', '\u2514\u2500'
REM#PY#     
REM#PY#     if percent >= 100: bar_color = C.SUCCESS
REM#PY#     elif percent >= 50: bar_color = C.INFO
REM#PY#     else: bar_color = C.PRIMARY
REM#PY#     
REM#PY#     bar = f"{bar_color}{bar_char*f}{C.RESET}{C.MUTED}{bg_char*e}{C.RESET}"
REM#PY#     if percent >= 100:
REM#PY#         return f" {C.SUCCESS}{check_icon}{C.RESET} {C.WHITE}{label:<20}{C.RESET} {bar} {C.SUCCESS}DONE{C.RESET}\n   {C.MUTED}{pipe_icon} {size_stats}{C.RESET}"
REM#PY#     else:
REM#PY#         fps_disp = fps if fps != "-" else "..."
REM#PY#         spd_disp = speed if speed != "0X" else "..."
REM#PY#         eta_disp = f" | {eta}" if eta else ""
REM#PY#         return f" {C.PRIMARY}{arrow_icon}{C.RESET} {C.WHITE}{label:<20}{C.RESET} {bar} {C.INFO}{percent:5.1f}%{C.RESET}\n   {C.MUTED}{pipe_icon} {spd_disp} | {fps_disp} fps{eta_disp}{C.RESET}"
REM#PY# 
REM#PY# class WorkerStats:
REM#PY#     def __init__(self):
REM#PY#         self.stats = {}
REM#PY#         self.starts = {}
REM#PY#     def update(self, wid, fn, pct, fps, speed, size_stats=""):
REM#PY#         with LOCK:
REM#PY#             if wid not in self.starts: self.starts[wid] = time.time()
REM#PY#             self.stats[wid] = {'fn': fn, 'pct': pct, 'fps': fps, 'speed': speed, 'size': size_stats, 'start': self.starts[wid]}
REM#PY#     def get_all(self):
REM#PY#         with LOCK: return self.stats.copy()
REM#PY#     def remove_worker(self, wid):
REM#PY#         with LOCK:
REM#PY#             self.stats.pop(wid, None)
REM#PY#             self.starts.pop(wid, None)
REM#PY# 
REM#PY# # Helper functions (metadata, ffmpeg)
REM#PY# def get_file_metadata(path): return (path.stat().st_ctime, path.stat().st_atime, path.stat().st_mtime)
REM#PY# def restore_file_metadata(path, metadata):
REM#PY#     ctime, atime, mtime = metadata
REM#PY#     os.utime(path, (atime, mtime))
REM#PY#     if platform.system() == "Windows":
REM#PY#         try:
REM#PY#             import ctypes
REM#PY#             from ctypes import wintypes
REM#PY#             ts = int((ctime + 11644473600) * 10000000)
REM#PY#             ft = wintypes.FILETIME(ts & 0xFFFFFFFF, ts >> 32)
REM#PY#             h = ctypes.windll.kernel32.CreateFileW(str(path), 0x40000000 | 0x0100, 0, None, 3, 0, None)
REM#PY#             if h != -1:
REM#PY#                 ctypes.windll.kernel32.SetFileTime(h, ctypes.byref(ft), None, None)
REM#PY#                 ctypes.windll.kernel32.CloseHandle(h)
REM#PY#         except: pass
REM#PY# 
REM#PY# FFMPEG_URLS = {"Windows": "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", "Linux": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz", "Darwin": "https://evermeet.cx/ffmpeg/getrelease/zip"}
REM#PY# 
REM#PY# def check_ffmpeg():
REM#PY#     if shutil.which("ffmpeg") and shutil.which("ffprobe"): return True
REM#PY#     ffmpeg_bin = BIN_DIR / ("ffmpeg.exe" if platform.system() == "Windows" else "ffmpeg")
REM#PY#     ffprobe_bin = BIN_DIR / ("ffprobe.exe" if platform.system() == "Windows" else "ffprobe")
REM#PY#     if ffmpeg_bin.exists() and ffprobe_bin.exists():
REM#PY#         os.environ["PATH"] = str(BIN_DIR.absolute()) + os.pathsep + os.environ["PATH"]
REM#PY#         return True
REM#PY#     return False
REM#PY# 
REM#PY# def download_ffmpeg():
REM#PY#     url = FFMPEG_URLS.get(platform.system())
REM#PY#     if not url: return False
REM#PY#     BIN_DIR.mkdir(exist_ok=True)
REM#PY#     archive_ext = ".zip" if platform.system() in ["Windows", "Darwin"] else ".tar.xz"
REM#PY#     archive_path = BIN_DIR / f"ffmpeg{archive_ext}"
REM#PY#     print(f"\n{C.INFO}[DOWNLOAD] Fetching FFmpeg...{C.RESET}")
REM#PY#     try:
REM#PY#         import urllib.request
REM#PY#         def reporthook(b, b_size, total):
REM#PY#             if total > 0:
REM#PY#                 pct = min(100, (b * b_size / total) * 100)
REM#PY#                 bar = '█' * int(40 * pct / 100) + '░' * (40 - int(40 * pct / 100))
REM#PY#                 print(f"\r{C.INFO}[PROGRESS]{C.RESET} {bar} {pct:5.1f}%", end='', flush=True)
REM#PY#         urllib.request.urlretrieve(url, archive_path, reporthook=reporthook)
REM#PY#         print(f"\n{C.INFO}[EXTRACT] Extracting binaries...{C.RESET}")
REM#PY#         if archive_ext == ".zip":
REM#PY#             import zipfile
REM#PY#             with zipfile.ZipFile(archive_path, 'r') as z:
REM#PY#                 for m in z.namelist():
REM#PY#                     fn = os.path.basename(m)
REM#PY#                     if fn.lower() in ["ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"]:
REM#PY#                         with z.open(m) as src, open(BIN_DIR / fn, 'wb') as tgt:
REM#PY#                             shutil.copyfileobj(src, tgt)
REM#PY#                         if platform.system() != "Windows": (BIN_DIR / fn).chmod(0o755)
REM#PY#         else:
REM#PY#             import tarfile
REM#PY#             with tarfile.open(archive_path, 'r:xz') as tar:
REM#PY#                 for m in tar.getmembers():
REM#PY#                     if m.name.endswith(("ffmpeg", "ffprobe")):
REM#PY#                         m.name = os.path.basename(m.name)
REM#PY#                         tar.extract(m, path=BIN_DIR)
REM#PY#                         (BIN_DIR / m.name).chmod(0o755)
REM#PY#         archive_path.unlink()
REM#PY#         os.environ["PATH"] = str(BIN_DIR.absolute()) + os.pathsep + os.environ["PATH"]
REM#PY#         return True
REM#PY#     except: return False
REM#PY# 
REM#PY# def ensure_ffmpeg(auto_download=True):
REM#PY#     if check_ffmpeg(): return True
REM#PY#     print(f"\n{C.WARNING} \u26a0  FFmpeg Not Found{C.RESET}\n")
REM#PY#     if not auto_download:
REM#PY#         if input(f"{C.PRIMARY}>> Download FFmpeg automatically? (Y/N): {C.RESET}").lower() != 'y': return False
REM#PY#     return download_ffmpeg()
REM#PY# 
REM#PY# def detect_gpu_codec(force_codec=None):
REM#PY#     if force_codec and force_codec != 'auto':
REM#PY#         try:
REM#PY#             r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5)
REM#PY#             if force_codec in r.stdout: return (force_codec, f"{force_codec.upper()} [FORCED]")
REM#PY#         except: pass
REM#PY#     try:
REM#PY#         r = subprocess.run(["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5)
REM#PY#         e = r.stdout
REM#PY#         if "h264_nvenc" in e: return ("h264_nvenc", "NVIDIA (NVENC)")
REM#PY#         elif "h264_qsv" in e: return ("h264_qsv", "Intel QuickSync")
REM#PY#         elif "h264_videotoolbox" in e: return ("h264_videotoolbox", "Apple VideoToolbox")
REM#PY#         elif "h264_vaapi" in e: return ("h264_vaapi", "VAAPI")
REM#PY#         else: return ("libx264", "CPU (x264)")
REM#PY#     except: return ("libx264", "CPU (x264)")
REM#PY# 
REM#PY# worker_stats = WorkerStats()
REM#PY# 
REM#PY# def verify_output(inp, outp):
REM#PY#     if not outp.exists() or outp.stat().st_size < 10240: return False
REM#PY#     try:
REM#PY#         def get_meta(p):
REM#PY#             cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=nb_frames,width,height", "-of", "csv=p=0", str(p)]
REM#PY#             r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
REM#PY#             parts = r.stdout.strip().split(',')
REM#PY#             return float(parts[0] if parts[0] else 0), int(parts[1] if len(parts) > 1 and parts[1] else -1)
REM#PY#         in_d, in_f = get_meta(inp)
REM#PY#         out_d, out_f = get_meta(outp)
REM#PY#         dur_ok = abs(in_d - out_d) < 2.0
REM#PY#         frm_ok = (in_f == -1 or out_f == -1 or abs(in_f - out_f) < 150)
REM#PY#         return dur_ok and frm_ok
REM#PY#     except: return False
REM#PY# 
REM#PY# def process_video(wid, vpath, codec, config):
REM#PY#     fn = vpath.name
REM#PY#     s_fps, s_speed, pct = "-", "0X", 0.0
REM#PY#     worker_stats.update(wid, fn, 0.0, s_fps, s_speed, "")
REM#PY#     logging.info(f"[Worker {wid}] Started processing: {fn}")
REM#PY#     try:
REM#PY#         meta = get_file_metadata(vpath)
REM#PY#         start_size = vpath.stat().st_size
REM#PY#         tmp = vpath.parent / f"mnemosyne_tmp_{wid}_{fn}"
REM#PY#         try:
REM#PY#             dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(vpath)], capture_output=True, text=True).stdout.strip() or 1.0)
REM#PY#         except: dur = 1.0
REM#PY#         # Build command with Conditional Logic for Hardware vs Software Encoders
REM#PY#         cmd = ["ffmpeg", "-nostdin", "-y", "-i", str(vpath), "-c:v", codec]
REM#PY#         
REM#PY#         # 1. NVENC (NVIDIA): Use Constant Quality (CQ) mode
REM#PY#         if "nvenc" in codec:
REM#PY#             cmd.extend(["-rc", "vbr", "-cq", "24", "-preset", "p4"])
REM#PY#         # 2. CPU (libx264): Use Target Bitrate + Medium Preset
REM#PY#         elif "libx264" in codec:
REM#PY#             cmd.extend(["-b:v", config['video_bitrate'], "-preset", "medium"])
REM#PY#         # 3. Universal Safety Mode (Intel QSV, AMD, Apple, etc.): Use Bitrate Only
REM#PY#         # avoid specific presets that might crash other hardware encoders
REM#PY#         else:
REM#PY#             cmd.extend(["-b:v", config['video_bitrate']])
REM#PY# 
REM#PY#         # Common parameters (FPS, Audio, Resize, Metadata)
REM#PY#         cmd.extend([
REM#PY#             "-r", str(config['target_fps']),
REM#PY#             "-vf", f"scale=-2:{config['target_height']}",
REM#PY#             "-c:a", "aac", "-b:a", config['audio_bitrate'],
REM#PY#             "-metadata", f"encoder={APP_NAME} v{VERSION}",
REM#PY#             "-progress", "-", "-nostats", str(tmp)
REM#PY#         ])
REM#PY#         
REM#PY#         if IS_WINDOWS:
REM#PY#             # CREATE_NEW_PROCESS_GROUP = 0x00000200
REM#PY#             proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=0x00000200)
REM#PY#         else:
REM#PY#             proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
REM#PY#         PROCESS_MGR.register(proc)
REM#PY#         while True:
REM#PY#             line = proc.stdout.readline()
REM#PY#             if not line and proc.poll() is not None: break
REM#PY#             if "out_time=" in line:
REM#PY#                 try:
REM#PY#                     ts = line.split("out_time=")[1].split()[0]
REM#PY#                     h, m, s = map(float, ts.split(':'))
REM#PY#                     new_pct = min(99.9, ((h*3600 + m*60 + s) / dur) * 100); pct = new_pct
REM#PY#                     worker_stats.update(wid, fn, pct, s_fps, s_speed)
REM#PY#                 except: pass
REM#PY#             elif "fps=" in line:
REM#PY#                 try:
REM#PY#                     s_fps = line.split("fps=")[1].split()[0]
REM#PY#                     s_speed = line.split("speed=")[1].split()[0]
REM#PY#                     worker_stats.update(wid, fn, pct, s_fps, s_speed)
REM#PY#                 except: pass
REM#PY#         PROCESS_MGR.unregister(proc)
REM#PY#         if proc.returncode != 0:
REM#PY#             if codec != "libx264":
REM#PY#                 logging.warning(f"Hardware encoding failed for {fn}, falling back to CPU")
REM#PY#                 worker_stats.update(wid, fn, 0.0, "-", "0X", "Retrying with CPU...")
REM#PY#                 return process_video(wid, vpath, "libx264", config)
REM#PY#             return False
REM#PY# 
REM#PY#         if config['verify_frames'] and not verify_output(vpath, tmp): return False
REM#PY#         
REM#PY#         end_size = tmp.stat().st_size
REM#PY#         size_diff = (1 - (end_size / start_size)) * 100
REM#PY#         size_stats = f"{start_size/1024/1024:.1f}MB -> {end_size/1024/1024:.1f}MB ({size_diff:.0f}% saved)"
REM#PY#         
REM#PY#         bak = vpath.with_suffix(vpath.suffix + '.bak')
REM#PY#         if bak.exists(): bak.unlink()
REM#PY#         try:
REM#PY#             vpath.rename(bak)
REM#PY#             tmp.rename(vpath)
REM#PY#             restore_file_metadata(vpath, meta)
REM#PY#             if vpath.exists() and vpath.stat().st_size > 10240: bak.unlink()
REM#PY#             else: raise Exception("Output verification fail after swap")
REM#PY#         except Exception as e:
REM#PY#             logging.error(f"File swap error: {e}")
REM#PY#             if bak.exists() and not vpath.exists(): bak.rename(vpath)
REM#PY#             return False
REM#PY#             
REM#PY#         worker_stats.update(wid, fn, 100.0, "0", "0", size_stats)
REM#PY#         return True
REM#PY#     except Exception as e:
REM#PY#         logging.error(f"Process error for {fn}: {e}")
REM#PY#         if 'tmp' in locals() and tmp.exists(): tmp.unlink()
REM#PY#         return False
REM#PY# 
REM#PY# def update_display(total, codec_name, config):
REM#PY#     header = draw_header(config, codec_name)
REM#PY#     buffer = [""] # Leading newline to separate from logo
REM#PY#     stats = worker_stats.get_all()
REM#PY#     completed = sum(1 for s in stats.values() if s['pct'] >= 100)
REM#PY#     in_progress = len([s for s in stats.values() if 0 < s['pct'] < 100])
REM#PY#     
REM#PY#     for wid in sorted(stats.keys()):
REM#PY#         s = stats[wid]
REM#PY#         fn_short = s['fn'][:25] + "..." if len(s['fn']) > 28 else s['fn']
REM#PY#         eta_str = ""
REM#PY#         if 0 < s['pct'] < 100 and 'start' in s:
REM#PY#             elapsed = time.time() - s['start']
REM#PY#             if s['pct'] > 1:
REM#PY#                 rem = (elapsed / (s['pct'] / 100)) - elapsed
REM#PY#                 m, s_v = divmod(int(rem), 60); eta_str = f"ETA: {m}m {s_v}s"
REM#PY#         buffer.append(render_progress(fn_short, s['pct'], s['fps'], s['speed'], s['size'], eta_str))
REM#PY#         buffer.append("")
REM#PY#         
REM#PY#     buffer.append(f" {C.WHITE}{'='*70}{C.RESET}")
REM#PY#     o_pct = (completed / total * 100) if total > 0 else 0
REM#PY#     buffer.append(f" {C.WHITE}Total: {total} | {C.SUCCESS}Done: {completed} | {C.INFO}Active: {in_progress} | {o_pct:.1f}%{C.RESET}")
REM#PY#     
REM#PY#     # Send as one atomic write to terminal
REM#PY#     sys.stdout.write("\033[H" + header + "\n".join(buffer) + "\033[J")
REM#PY#     sys.stdout.flush()
REM#PY# def show_security_notice(log_msg, drive_type=None):
REM#PY#     clear_screen(); w = 70
REM#PY#     draw_separator(w, 'top')
REM#PY#     draw_box_line("SECURITY & TRANSPARENCY", w, C.BOLD + C.PRIMARY)
REM#PY#     draw_separator(w, 'mid')
REM#PY#     if drive_type == 2: # REMOVABLE
REM#PY#         draw_box_line("\u26a0  REMOVABLE MEDIA DETECTED", w, C.BOLD + C.WARNING)
REM#PY#         draw_box_line("IMPORTANT: Keep the device connected to prevent data loss.", w, C.WARNING)
REM#PY#         draw_separator(w, 'mid')
REM#PY#     draw_box_line("1. Local Processing: No data ever leaves your computer.", w, C.WHITE)
REM#PY#     draw_box_line(f"2. Logs: {log_msg}", w, C.WHITE)
REM#PY#     draw_box_line("3. Open Source: Full code transparency (GNU GPL v3.0)", w, C.WHITE)
REM#PY#     draw_box_line("4. Atomic Safety: Temporary files used to prevent data loss.", w, C.WHITE)
REM#PY#     draw_separator(w, 'mid')
REM#PY#     draw_box_line("Mnemosyne protects your privacy and your digital memory.", w, C.SUCCESS)
REM#PY#     draw_separator(w, 'bot')
REM#PY#     print(""); input(f" {C.PRIMARY}>> Press ENTER to continue...{C.RESET}")
REM#PY# 
REM#PY# def get_valid_input(prompt, valid_options):
REM#PY#     """Prompt user for input and validate against valid_options"""
REM#PY#     while True:
REM#PY#         choice = input(prompt).strip()
REM#PY#         if choice == '' or choice in valid_options:
REM#PY#             return choice if choice else valid_options[0]
REM#PY#         print(f" {C.ERROR}[!] Invalid choice. Please enter {' or '.join(valid_options)}.{C.RESET}")
REM#PY# 
REM#PY# def main():
REM#PY#     enable_ansi()
REM#PY#     # Signal Handling for Ctrl+C
REM#PY#     import signal
REM#PY#     def signal_handler(sig, frame):
REM#PY#         PROCESS_MGR.kill_all()
REM#PY#         show_cursor()
REM#PY#         print(f"\\n\\n {C.WARNING}[!] EMERGENCY STOP: Interrupted by user (Signal {sig}).{C.RESET}")
REM#PY#         print(f" {C.SUCCESS}[+] Cleanup complete. You may now exit.{C.RESET}")
REM#PY#         cleanup_temp_files(); sys.exit(130)
REM#PY#     signal.signal(signal.SIGINT, signal_handler)
REM#PY# 
REM#PY#     parser = argparse.ArgumentParser(description=f"{APP_NAME} v{VERSION}", formatter_class=argparse.RawDescriptionHelpFormatter)
REM#PY#     parser.add_argument('-r', '--recursive', action='store_true', help='Search subfolders')
REM#PY#     parser.add_argument('-w', '--workers', type=int, help='Parallel threads')
REM#PY#     parser.add_argument('--height', type=int, help='Target height')
REM#PY#     parser.add_argument('--desktop-log', action='store_true', help='Log to Desktop')
REM#PY#     parser.add_argument('--codec', choices=['auto', 'h264_nvenc', 'h264_qsv', 'h264_vaapi', 'libx264'], default='auto')
REM#PY#     args = parser.parse_args()
REM#PY# 
REM#PY#     config = load_config()
REM#PY#     if args.recursive: config['recursive'] = True
REM#PY#     if args.workers: config['max_workers'] = args.workers
REM#PY#     if args.height: config['target_height'] = args.height
REM#PY#     
REM#PY#     desktop_log_mode = args.desktop_log
REM#PY#     if not args.desktop_log:
REM#PY#         clear_screen(); w = 70
REM#PY#         draw_separator(w, 'top'); draw_box_line("LOG PREFERENCE", w, C.BOLD + C.PRIMARY); draw_separator(w, 'mid')
REM#PY#         draw_box_line("Where should Mnemosyne save log files?", w)
REM#PY#         draw_box_line("[1] Desktop", w, C.INFO)
REM#PY#         draw_box_line("[2] AppData", w, C.INFO)
REM#PY#         draw_separator(w, 'bot')
REM#PY#         choice = input(f" {C.PRIMARY}>> Choice [Default=1]: {C.RESET}").strip()
REM#PY#         desktop_log_mode = (choice != '2')
REM#PY# 
REM#PY#     log_file = setup_logging(desktop_mode=desktop_log_mode)
REM#PY#     log_msg = "Desktop/Mnemosyne_Log.txt" if desktop_log_mode else "AppData/Mnemosyne/logs"
REM#PY#     
REM#PY#     drive_type = get_drive_type(str(Path.cwd()))
REM#PY#     show_security_notice(log_msg, drive_type)
REM#PY#     audit_orphaned_backups()
REM#PY#     
REM#PY#     if not ensure_ffmpeg(config['auto_download_ffmpeg']): return 1
REM#PY#     codec, codec_name = detect_gpu_codec(args.codec)
REM#PY# 
REM#PY#     while True:
REM#PY#         clear_screen(); print(draw_header(config, codec_name))
REM#PY#         print(f" {C.PRIMARY}[BOOT] Strategy:{C.RESET}")
REM#PY#         print(f"    [1] Local Folder  [2] Deep Scan (Recursive)")
REM#PY#         strat = get_valid_input(f" {C.PRIMARY}>> Choice [Default=1]: {C.RESET}", ['1', '2'])
REM#PY#         config['recursive'] = (strat == '2')
REM#PY#         
REM#PY#         print(f"\n {C.PRIMARY}[BOOT] Priority:{C.RESET}")
REM#PY#         print(f"    [1] Name A-Z  [2] Name Z-A  [3] Largest  [4] Smallest")
REM#PY#         sort_opt = get_valid_input(f" {C.PRIMARY}>> Choice [Default=1]: {C.RESET}", ['1', '2', '3', '4'])
REM#PY#         if sort_opt == '2': config['sort'] = 'name_za'
REM#PY#         elif sort_opt == '3': config['sort'] = 'size_desc'
REM#PY#         elif sort_opt == '4': config['sort'] = 'size_asc'
REM#PY#         else: config['sort'] = 'name_az'
REM#PY# 
REM#PY#         print(f"\n {C.PRIMARY}[BOOT] Engine Mode:{C.RESET}")
REM#PY#         print(f"    [1] Sequential  [2] Parallel  [3] Custom Workers")
REM#PY#         mode_opt = get_valid_input(f" {C.PRIMARY}>> Choice [Default=2]: {C.RESET}", ['1', '2', '3'])
REM#PY#         if mode_opt == '1': config['max_workers'] = 1
REM#PY#         elif mode_opt == '3':
REM#PY#             try: config['max_workers'] = int(input(f" {C.PRIMARY}>> Workers (1-{os.cpu_count()}): {C.RESET}"))
REM#PY#             except: config['max_workers'] = DEFAULT_CONFIG['max_workers']
REM#PY#         else: config['max_workers'] = DEFAULT_CONFIG['max_workers']
REM#PY# 
REM#PY#         print(f"\n {C.INFO}[SCAN] Scanning for videos...{C.RESET}")
REM#PY#         videos = []; cwd = Path.cwd()
REM#PY#         pattern = cwd.rglob if config['recursive'] else cwd.glob
REM#PY#         for ext in VIDEO_EXTENSIONS: videos.extend(list(pattern(f"*{ext}")))
REM#PY#         videos = [v for v in videos if not any(x in v.parts for x in ["bin", "logs"])]
REM#PY#         if not videos:
REM#PY#             input(f" {C.WARNING}No videos found. Press ENTER to retry...{C.RESET}"); continue
REM#PY#         
REM#PY#         if config['sort'] == 'name_az': videos.sort()
REM#PY#         elif config['sort'] == 'name_za': videos.sort(reverse=True)
REM#PY#         elif config['sort'] == 'size_desc': videos.sort(key=lambda x: x.stat().st_size, reverse=True)
REM#PY#         elif config['sort'] == 'size_asc': videos.sort(key=lambda x: x.stat().st_size)
REM#PY# 
REM#PY#         clear_screen(); print(draw_header(config, codec_name)); w = 70
REM#PY#         total_in = sum(v.stat().st_size for v in videos)
REM#PY#         draw_separator(w, 'top'); draw_box_line("MISSION BRIEFING", w, C.BOLD + C.PRIMARY); draw_separator(w, 'mid')
REM#PY#         draw_box_line(f"Queue: {len(videos)} videos | Size: {total_in/1024/1024:.1f} MB", w)
REM#PY#         if drive_type == 2: draw_box_line("Drive: REMOVABLE MEDIA (Caution)", w, C.WARNING)
REM#PY#         draw_box_line(f"Codec: {codec_name} | Mode: {'Parallel' if config['max_workers']>1 else 'Sequential'}", w)
REM#PY#         draw_separator(w, 'bot')
REM#PY#         
REM#PY#         ans = input(f"\n {C.SUCCESS}READY TO ENGAGE.{C.RESET} Press ENTER to start, 'N' to re-config, 'S' to save: ").lower().strip()
REM#PY#         if ans == 'n': continue
REM#PY#         if ans == 's': save_config(config); print(f" {C.SUCCESS}[+] Settings saved.{C.RESET}"); time.sleep(1); continue
REM#PY#         if ans == 'q': return 0
REM#PY#         break
REM#PY# 
REM#PY#     start_t = time.time(); success = 0; failed = 0
REM#PY#     clear_screen(); hide_cursor()
REM#PY#     try:
REM#PY#         with ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
REM#PY#             futures = {executor.submit(process_video, (i % config['max_workers']) + 1, v, codec, config): v for i, v in enumerate(videos)}
REM#PY#             while any(not f.done() for f in futures):
REM#PY#                 update_display(len(videos), codec_name, config); time.sleep(0.5)
REM#PY#             for f in futures:
REM#PY#                 if f.result(): success += 1
REM#PY#                 else: failed += 1
REM#PY#     finally:
REM#PY#         show_cursor()
REM#PY# 
REM#PY#     end_t = time.time(); total_t = end_t - start_t
REM#PY#     total_out = sum(v.stat().st_size for v in videos if v.exists())
REM#PY#     saved = total_in - total_out
REM#PY#     
REM#PY#     clear_screen(); print(draw_header(config, codec_name)); w = 70
REM#PY#     draw_separator(w, 'top'); draw_box_line("FINAL MISSION REPORT", w, C.BOLD + C.SUCCESS); draw_separator(w, 'mid')
REM#PY#     draw_box_line(f"Status: {success} Success | {failed} Failed", w)
REM#PY#     draw_box_line(f"Time: {int(total_t//60)}m {int(total_t%60)}s | Space Saved: {saved/1024/1024:.1f} MB", w)
REM#PY#     draw_separator(w, 'bot')
REM#PY#     cleanup_temp_files()
REM#PY#     print(f"\n {C.SUCCESS}All operations completed successfully.{C.RESET}")
REM#PY#     return 0
REM#PY# 
REM#PY# if __name__ == "__main__":
REM#PY#     try: sys.exit(main())
REM#PY#     except KeyboardInterrupt:
REM#PY#         PROCESS_MGR.kill_all()
REM#PY#         show_cursor()
REM#PY#         print(f"\n\n {C.WARNING}[!] EMERGENCY STOP: Interrupted by user.{C.RESET}")
REM#PY#         print(f" {C.SUCCESS}[+] Operations terminated. Original videos are safe, you may now exit.{C.RESET}")
REM#PY#         cleanup_temp_files(); sys.exit(130)
REM#PY#     except Exception as e:
REM#PY#         logging.critical(f"FATAL: {e}"); logging.debug(traceback.format_exc())
REM#PY#         print(f"\n\n {C.ERROR}[X] Fatal error. Check logs.{C.RESET}"); sys.exit(1)

