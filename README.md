# Mnemosyne - The Keeper of Digital Memory

**[English](#english) | [Türkçe](#türkçe)**

---

## English

### The Philosophy

Mnemosyne is a video transformation engine built to handle one thing well: converting your large video files into optimized, smaller versions while preserving the metadata that matters. Named after the Greek goddess of memory, it's designed for archivists and historians who care about keeping their digital timeline intact.

> "Memory is the scribe of the soul." — Aristotle

Most converters treat files as data. Mnemosyne treats them as memories. When you compress a video, we restore the exact timestamps it had before—creation date, modification date, access time. Everything stays where it should be.

**The core principle**: Local processing. No cloud, no telemetry, no compromise. What you process stays on your machine.

---

### Features

**Hardware Acceleration**
- NVIDIA NVENC (Constant Quality mode)
- Intel QuickSync
- Apple VideoToolbox  
- Linux VAAPI
- Automatic fallback to CPU encoding if needed

**Safety First**
- Atomic file operations—originals are never touched until conversion is verified
- Automatic backups (.bak files) during processing
- Frame verification for quality assurance
- Graceful shutdown with Ctrl+C

**What It Does**
- Converts video to H.264 in MP4 container with AAC audio
- Defaults to 480p resolution (configurable)
- Preserves all file timestamps post-conversion
- Multi-threaded processing for batch operations
- Real-time progress monitoring

---

### Installation

**Windows**
Double-click `mnemosyne.bat`. Python and FFmpeg will be installed automatically if missing.

**macOS / Linux**
```bash
chmod +x mnemosyne.sh
./mnemosyne.sh
```

Or run directly with Python:
```bash
python3 mnemosyne.py
```

---

### Configuration

Edit `config.json` to customize:
```json
{
    "target_height": 480,
    "video_bitrate": "800k",
    "audio_bitrate": "128k",
    "target_fps": 30,
    "max_workers": 4,
    "recursive": false,
    "verify_frames": true,
    "preserve_metadata": true
}
```

Command-line overrides:
- `-r, --recursive` — Search subfolders
- `-w, --workers` — Parallel threads (1-8)
- `--height` — Target resolution
- `--codec` — Force a specific encoder (auto/h264_nvenc/h264_qsv/libx264)
- `--desktop-log` — Write logs to Desktop instead of AppData

---

### Supported Formats

Input: MP4, MKV, AVI, MOV, FLV, WMV, WebM, TS, M4V  
Output: H.264 video + AAC audio in MP4 container

---

### How It Works

1. Scans for video files in current directory (or recursively)
2. Reads original file metadata (timestamps)
3. Converts using the best available hardware encoder
4. Verifies output integrity
5. Replaces original only after verification succeeds
6. Restores original timestamps to converted file
7. Cleans up temporary files

If anything fails, the original file stays untouched.

---

### License

GNU General Public License v3.0 — [LICENSE](LICENSE)

Copyright © 2026 Mejensi

---

## Türkçe

### Felsefe

Mnemosyne, büyük video dosyalarınızı optimize ederken bunlara ait meta verileri koruyan bir araçtır. Adını Anı Tanrıçası Mnemosyne'den alan bu yazılım, dijital arşivlerini saklamak ve zamanını korumak isteyen kişiler için tasarlanmıştır.

> "Hafıza, ruhun yazarıdır." — Aristoteles

Çoğu dönüştürücü dosyaları veri olarak görür. Mnemosyne onları anı olarak görür. Bir videoyu sıkıştırdığında, sahip olduğu tam zaman damgalarını (oluşturma, değiştirme, erişim) geri yükleriz. Dosya tarihçesi aynen kalır.

**Ana ilke**: Tümü lokal işlenir. Bulut yok, telemetri yok, ödün yok. Verileriniz makinenizde kalır.

---

### Özellikler

**Donanım Hızlandırması**
- NVIDIA NVENC (Sabit Kalite modu)
- Intel QuickSync
- Apple VideoToolbox
- Linux VAAPI
- Gerekirse otomatik CPU kodlamasına döner

**Güvenlik Öncelikli**
- Atomik dosya işlemleri—orijinal dosya doğrulama tamamlanana kadar dokunulmaz
- Dönüştürme sırasında otomatik yedeklemeler (.bak dosyaları)
- Kalite doğrulaması
- Ctrl+C ile güvenli kapatma

**Neler Yapar**
- Video'yu H.264 + AAC'ye MP4'e dönüştürür
- Varsayılan 480p (ayarlanabilir)
- Tüm dosya zaman damgalarını korur
- Batch işlemler için çok işlemli işleme
- Gerçek zamanlı ilerleme gösterisi

---

### Kurulum

**Windows**
`mnemosyne.bat` dosyasını çift tıklayın. Python ve FFmpeg otomatik yüklenir.

**macOS / Linux**
```bash
chmod +x mnemosyne.sh
./mnemosyne.sh
```

Ya da Python ile doğrudan:
```bash
python3 mnemosyne.py
```

---

### Yapılandırma

`config.json` dosyasını düzenleyin:
```json
{
    "target_height": 480,
    "video_bitrate": "800k",
    "audio_bitrate": "128k",
    "target_fps": 30,
    "max_workers": 4,
    "recursive": false,
    "verify_frames": true,
    "preserve_metadata": true
}
```

Komut satırı seçenekleri:
- `-r, --recursive` — Alt klasörleri tara
- `-w, --workers` — Paralel işlemler (1-8)
- `--height` — Hedef çözünürlük
- `--codec` — Kodlayıcı seç (auto/h264_nvenc/h264_qsv/libx264)
- `--desktop-log` — Logları Desktop'a yaz

---

### Desteklenen Formatlar

Giriş: MP4, MKV, AVI, MOV, FLV, WMV, WebM, TS, M4V  
Çıkış: H.264 video + AAC ses MP4 konteynerinde

---

### Nasıl Çalışır

1. Geçerli klasörde video dosyalarını tarar (veya recursive)
2. Orijinal dosya meta verilerini okur (zaman damgaları)
3. Mevcut en iyi donanım kodlayıcısını kullanarak dönüştürür
4. Çıkış bütünlüğünü doğrular
5. Doğrulama başarılı olduktan sonra orijinali değiştirir
6. Dönüştürülen dosyaya orijinal zaman damgalarını geri yükler
7. Geçici dosyaları temizler

Herhangi bir şey başarısız olursa orijinal dosya dokunulmaz kalır.

---

### Lisans

GNU General Public License v3.0 — [LICENSE](LICENSE)

Telif Hakkı © 2026 Mejensi

---

<p align="center">
  <strong>Status:</strong> Stable v1.0 | <strong>License:</strong> GPL v3.0
</p>
