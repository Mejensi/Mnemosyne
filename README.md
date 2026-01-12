# Mnemosyne

Mnemosyne is a tool designed to compress your video collection while preserving the original viewing experience. It scans your folders for video files and converts them to a standardized format (480p, optimized bitrate) to save disk space.

The main difference between Mnemosyne and other converters is its focus on preservation. It keeps the original file's creation and modification dates, so your timeline remains intact. It also uses a safety mechanism to ensure no data is lost during the conversion process; the original file is only replaced effectively after the new one is verified.

## Features

- **Space Saving**: Reduces file sizes significantly by converting to efficient 480p H.264.
- **Metadata Protection**: Copies the original creation and modification timestamps to the new file.
- **Safety First**: Uses temporary files and atomic swaps. If a conversion fails or is interrupted, your original file is untouched.
- **Smart Encoding**: Automatically detects your hardware (NVIDIA, Intel, Apple, or CPU) and chooses the best way to convert the video.
- **Recursive Scan**: Can process a single folder or search through all subfolders.

## How to Use

### Windows
Double-click `mnemosyne.bat`. If you don't have Python installed, it will offer to install it for you.

### Linux / macOS
Open a terminal and run `mnemosyne.sh`. You will need to have Python 3 and FFmpeg installed on your system.
```bash
bash mnemosyne.sh
```

## Requirements
- Python 3+
- FFmpeg (The Windows version can download this automatically)

## License
This project is licensed under the GNU General Public License v3.0.
