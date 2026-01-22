# Mnemosyne - The Keeper of Digital Memory v1.1

Mnemosyne is a powerful, automated video compression engine designed for simplicity and absolute metadata preservation. It optimizes your video collection to 480p while ensuring your digital history remains intact.

### Features
- **Smart Compression**: Automatically optimizes videos to H.264 at 480p using hardware-accelerated encoders (NVENC, QSV, VideoToolbox) with automatic fallback to CPU.
- **Safety Bridge**: Uses an atomic file swap system to ensure zero data loss. Your original file is only replaced after the conversion is verified.
- **Timeline Preservation**: Unlike standard converters, Mnemosyne restores the original creation and modification timestamps to the new files.
- **Zero-Friction Portability**: All execution scripts are fully self-contained polyglots. They include the core engine source code internally for maximum portability.

### Instructions

#### Windows
Run **mnemosyne.bat**. It handles environment checks and can automatically install Python via winget if missing.

#### Linux & macOS
Run **bash mnemosyne.sh**. The script is fully self-contained. Ensure Python 3 is installed on your system.

### Legal & Attribution
This project is open-source software licensed under the **GNU General Public License v3.0**. 

Mnemosyne relies on **FFmpeg** for video processing. Please refer to [NOTICE.md](NOTICE.md) for full third-party attributions, license details, and the disclaimer of warranty.

Copyright (C) 2026 Mejensi.
