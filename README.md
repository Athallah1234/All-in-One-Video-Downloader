<div align="center">

# 🎬 Video Downloader

**Aplikasi desktop downloader video & audio paling lengkap, bertenaga yt-dlp, PySide6, dan FFmpeg.**

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.7%2B-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-2025.1.15%2B-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://github.com/yt-dlp/yt-dlp)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-Required%20for%20conversion-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)
[![License](https://img.shields.io/badge/License-See%20LICENSE-blue?style=for-the-badge)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-brightgreen?style=for-the-badge)](#)

<br/>

> **Bukan sekadar downloader biasa.** Video Downloader menghadirkan kendali penuh atas setiap aspek unduhan — resolusi, codec, frame rate, bit depth, HDR, subtitle, metadata, integritas file, dan masih banyak lagi — semuanya dalam satu antarmuka grafis yang bersih, cepat, dan tangguh.

<br/>

[✨ Fitur Unggulan](#-fitur-unggulan) •
[⚡ Instalasi Cepat](#-instalasi-cepat) •
[🚀 Cara Pakai](#-cara-pakai) •
[⚙️ Pengaturan Lengkap](#️-pengaturan-lengkap) •
[🏗️ Build & Distribusi](#️-build--distribusi) •
[🧪 Testing](#-testing) •
[🗂️ Struktur Proyek](#️-struktur-proyek) •
[🔧 Troubleshooting](#-troubleshooting) •
[⚖️ Legal](#️-legal--kredit)

</div>

---

## ✨ Fitur Unggulan

### 🎯 Unduh Cerdas & Presisi Format

Tidak ada lagi tebak-tebakan soal format apa yang tersedia. Video Downloader membaca metadata langsung dari sumber melalui yt-dlp dan menampilkan hanya opsi yang benar-benar ada:

| Kategori | Pilihan yang Tersedia |
|---|---|
| **Resolusi Video** | 144p, 240p, 360p, 480p, 720p, 1080p, 1440p, 4K (2160p), 8K (4320p) |
| **Codec Video** | Auto, H.264/AVC, H.265/HEVC, VP9, AV1 |
| **Codec Audio** | Auto, AAC, Opus, Vorbis, MP3, FLAC |
| **Frame Rate** | Auto, 24, 25, 30, 48, 50, 60, 100, 120, 144, 240 fps |
| **Bit Depth** | Auto, 8-bit, 10-bit (HDR-capable), 12-bit (HDR-capable) |
| **Dynamic Range** | Auto, SDR, HDR (Best), HDR10, HDR10+, HDR12, HLG, Dolby Vision |
| **Container Output** | Auto, MP4, MKV, WebM, AVI, MOV |
| **Mode Unduh** | Video, Audio Only, Video Only, Thumbnail Only, Subtitle Only, Metadata Only |

> Format yang tidak tersedia di sumber secara otomatis dinonaktifkan di UI — Anda tidak akan pernah memilih format yang gagal.

---

### 📋 Manajemen Antrian & Download Bersamaan

- **Antrian multi-unduhan** dengan kontrol konkurensi yang bisa diatur
- **Pause / Resume kooperatif** per-item di batas transfer yt-dlp — status *Pausing* dan *Paused* yang jujur
- **Cancel instan** bahkan saat sedang dalam keadaan paused
- **Resume file parsial** — unduhan yang terputus dilanjutkan, bukan diulang dari awal
- **Retry otomatis** dengan kontrol `stop` jika terus gagal
- **ETA seluruh antrian** menggunakan simulasi slot yang sadar konkurensi, rata-rata kecepatan transfer bergulir, akuntansi progres aktif, dan waktu selesai wall-clock
- **Estimasi ukuran pra-unduh** dengan tingkat keyakinan: `exact` / `approximate` / `partial` / `unknown`, termasuk fallback dari bitrate, dan gate keras sebelum transfer dimulai

---

### 🎵 Pipeline Audio Lengkap

Untuk mode **Audio Only**, pipeline FFmpeg terurut secara deterministik:

1. *(Opsional)* Konversi format thumbnail (JPEG/PNG/WebP)
2. Ekstraksi audio dengan codec pilihan + kualitas yang ditentukan
3. *(Opsional)* Embed metadata & chapters
4. *(Opsional)* Embed cover art (MP3, M4A, FLAC, Opus)

Kontrol tambahan:
- Sample rate audio (misalnya 44100 Hz, 48000 Hz)
- Jumlah channel audio (mono, stereo, dll.)
- Sidecar cover art opsional
- Validasi container-aware untuk cover art

---

### 🎥 Pipeline Video Lengkap

Untuk mode **Video** dan **Video Only**, pipeline yang terurut:

1. *(Opsional)* Konversi format thumbnail sebelum unduhan
2. Remux ke container target (MP4, MKV, WebM, AVI, MOV)
3. *(Opsional)* Embed metadata, chapters, info JSON
4. *(Opsional)* Embed thumbnail/poster

Guard kompatibilitas live melindungi dari kombinasi tidak valid (misalnya thumbnail embedding di WebM/AVI).

---

### 🧮 Format Selector Cerdas (yt-dlp Native)

Di balik layar, aplikasi membangun format selector yt-dlp yang presisi berdasarkan pilihan Anda:

```
# Contoh selector yang dihasilkan otomatis:
bestvideo[height=1080][vcodec~='^(?:hev1|hvc1|hevc)'][fps>=29.5][fps<30.5][dynamic_range='HDR10']+bestaudio[acodec~='^(?:mp4a|aac)']
```

Selector ini mencerminkan **format ID eksak** dari metadata yt-dlp untuk single-video, dan filter berbasis properti untuk playlist.

---

### 📜 Playlist & Batch Download

#### Playlist / Channel
- Dialog pemilihan item playlist dengan **checklist per-video yang bisa dicari**
- Filter ketersediaan (hanya video yang bisa diunduh)
- Bulk selection tools (pilih semua, batalkan semua, balik pilihan)
- Batched rendering untuk playlist sangat besar
- Penambahan ke antrian **diblokir** hingga pilihan dikonfirmasi secara eksplisit
- Hanya indeks one-based yang dipilih yang dikirim ke yt-dlp

#### Batch URL (Multi-URL sekaligus)

- Mendukung custom `--extractor-args` per URL dengan format `URL<TAB>EXTRACTOR:ARG=VALUE`; nilai divalidasi, dipakai sejak Analyze hingga download, dan tidak ditampilkan dalam log.
- Input multi-baris atau import file `.txt` (UTF-8/UTF-16)
- Validasi & deduplikasi URL
- Analisis paralel yang dibatasi (bounded workers)
- Error per-URL yang ditampilkan dengan jelas
- Kontrol retry/stop individual
- Pemilihan hasil & konfigurasi playlist per-batch

---

### 🔍 Deteksi Duplikat

Sebelum masuk antrian, setiap URL dicek:
- **URL kanonik** dari yt-dlp
- **Identitas media** (extractor + media ID)
- Jika duplikat ditemukan → baris yang sudah ada difokuskan
- Override eksplisit tersedia
- Enforcement untuk batch
- Trimming overlap item playlist

---

### 🛡️ Verifikasi Integritas Post-Download

Setelah unduhan selesai, sebelum status berubah ke *Completed*:

1. **Structural check** — file ada dan tidak kosong
2. **FFprobe validation** — container media diverifikasi oleh FFprobe (durasi, ukuran)
3. **Hash verification** — SHA-256, SHA-1, atau MD5 dari metadata yt-dlp (untuk Video Only)
4. **File size check** — cocok dengan `filesize` yang diiklankan sumber

Jika terdeteksi korupsi:
- Re-download otomatis dibatasi (bounded retry)
- File korup dipindah ke `.corrupt-YYYYMMDD-HHMMSS` (quarantine)
- Error ditampilkan dengan jelas di UI

---

### 🍪 Autentikasi Cookie

#### Cookie Browser Otomatis
- Dukungan **Chrome, Firefox, dan Edge**
- Pemilihan profil browser opsional
- Pemilihan Firefox container opsional
- Hint instalasi jika browser tidak terdeteksi
- Pengaturan persisten tanpa menyimpan nilai cookie
- Nilai cookie **tidak pernah dicatat** di log

#### Cookie File Manual
- Import format Netscape `cookies.txt`
- Validasi struktural & batas ukuran yang ketat
- Nilai cookie tersembunyi di UI
- **Source-mode exclusivity** — tidak bisa aktif bersamaan dengan browser cookie
- Analisis, estimasi, dan unduhan yang terautentikasi

---

### 📊 Riwayat & Log

#### Tab History (SQLite)
- Riwayat semua unduhan yang berhasil
- Pencarian & filter (status, tanggal, kata kunci)
- Detail per-item
- Export ke **JSON** atau **CSV**
- Context actions yang aman (buka folder, copy URL, hapus entri)

#### Tab Log (Real-time)
- Log berputar yang diredaksi (tanpa kredensial)
- Filtering real-time berdasarkan level log
- **Severity-colored** — 🔴 ERROR, 🟡 WARNING, 🟢 INFO, ⬛ DEBUG
- Highlight kata pencarian
- Toggle warna, legenda, penghitung per-level
- Copy/export teks biasa yang aman

---

### ⚙️ Pengaturan Lengkap (12 Seksi)

Dialog Settings dengan **live search** dan **indikasi perubahan belum disimpan**:

| # | Seksi | Pengaturan Utama |
|---|---|---|
| 1 | **General** | Tab startup, konfirmasi keluar, simpan posisi jendela |
| 2 | **Downloads** | Folder default, template nama file, limit nama file, overwrite, file arsip |
| 3 | **Video** | Container default, preset resolusi/codec/fps/HDR default |
| 4 | **Audio** | Format audio default, kualitas, sample rate, channel |
| 5 | **Subtitles** | Bahasa, format subtitle, embed/sidecar, sumber (manual/auto), konversi |
| 6 | **Network** | Proxy, rate limit, timeout, retry, concurrent fragments, IP family, geo-bypass, User-Agent, HTTP chunk, sleep interval |
| 7 | **Cookies & Auth** | Browser cookie source, profil, Firefox container, cookie file path |
| 8 | **FFmpeg** | Path binary kustom, threads, preserve timestamps |
| 9 | **yt-dlp** | Format checking, extractor retries, playlist fault tolerance, prefer free formats, flat playlist, show warnings |
| 10 | **Appearance** | Dark/Light/System theme, font size, compact mode, status bar, alternating rows, panel preview |
| 11 | **Notifications** | Background-only notification, alert timing |
| 12 | **Advanced** | Log level, restrict filenames, cache, part files, description sidecar, xattrs, temp folder, multi-stream video/audio |

**Manajemen settings:**
- Export/import JSON (tanpa data autentikasi/proxy)
- Reset per-seksi atau reset penuh ke default
- **Live Apply** tanpa menutup dialog
- Diagnostik yang bisa dicopy (versi + jumlah konfigurasi per-kategori, tanpa data auth)

---

### 🖥️ Antarmuka & Pengalaman Pengguna

- **Dark & Light theme** yang bersih
- **Compact mode** opsional untuk UI lebih padat
- **Drag & drop URL** langsung ke jendela aplikasi
- **Preview thumbnail** sebelum unduhan (bisa disembunyikan)
- **Toolbar** dengan aksi: Supported Websites, Settings, About
- **Status bar** dengan info versi yt-dlp, FFmpeg, dan versi aplikasi
- **Keyboard shortcuts** yang komprehensif:

| Shortcut | Aksi |
|---|---|
| `Ctrl+L` | Fokus ke input URL |
| `Ctrl+Enter` | Analisis URL |
| `Ctrl+H` | Buka tab History |
| `Ctrl+Shift+L` | Buka tab Log |
| `Ctrl+,` | Buka Settings |
| `Ctrl+Q` | Keluar |

- **Dialog Supported Websites** — daftar langsung dari extractor yt-dlp yang terinstal (ribuan situs!)

---

## ⚡ Instalasi Cepat

### Prasyarat

| Komponen | Versi Minimum | Catatan |
|---|---|---|
| **Python** | 3.12+ | Wajib |
| **FFmpeg + FFprobe** | Bebas | Opsional*, diperlukan untuk konversi |

> \* Aplikasi tetap bisa digunakan tanpa FFmpeg, namun fitur merging, konversi audio, embed thumbnail, dan beberapa operasi subtitle membutuhkan `ffmpeg` dan `ffprobe` di `PATH`.

### Instalasi

```bash
# 1. Clone repositori
git clone https://github.com/username/video-downloader.git
cd video-downloader

# 2. Buat virtual environment
python -m venv .venv

# 3. Aktifkan virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 4. Install dependensi
pip install -r requirements.txt

# 5. Jalankan aplikasi
python main.py
```

### Dependensi Inti

```
PySide6>=6.7        # GUI framework (Qt for Python)
yt-dlp>=2025.1.15   # Download engine (1000+ situs)
requests>=2.32      # HTTP utilities
```

---

## 🚀 Cara Pakai

### Unduhan Dasar

1. **Paste URL** di kolom input (atau drag & drop dari browser)
2. Klik **Analyze** (atau `Ctrl+Enter`)
3. Pilih format, resolusi, codec, dll. sesuai kebutuhan
4. Klik **Add to Queue**
5. Klik **Start** atau aktifkan **Auto-start queue**

### Unduhan Playlist / Channel

1. Paste URL playlist atau channel
2. Klik **Analyze** → tunggu ekstraksi metadata
3. Klik **Choose Playlist Items**
4. Di dialog, **centang** video yang ingin diunduh (bisa cari, bulk-select, dll.)
5. Klik **Confirm Selection**
6. Klik **Add to Queue**

### Batch Download (Banyak URL Sekaligus)

1. Klik tombol **Batch Input**
2. Paste beberapa URL (satu per baris) atau klik **Import .txt File**
3. Klik **Analyze All** → tunggu analisis paralel
4. Pilih item yang berhasil dianalisis
5. Klik **Add Selected to Queue**

### Audio Only

1. Paste URL & Analyze
2. Ubah **Download Type** ke `Audio Only`
3. Pilih **Audio Format** (MP3, M4A, FLAC, OGG, WAV, Opus, dll.)
4. Pilih **Codec** & **Kualitas** yang diinginkan
5. Opsional: aktifkan **Embed Metadata**, **Embed Cover Art**
6. Add to Queue

---

## ⚙️ Pengaturan Lengkap

Buka Settings dengan `Ctrl+,` atau dari toolbar.

### Network

```
Proxy          : http://proxy:8080 atau socks5://...
Rate Limit     : 0 = tidak dibatasi (dalam KiB/s)
Timeout        : waktu tunggu koneksi (detik)
Retries        : jumlah retry per segment
Fragments      : concurrent fragment downloads
IP Family      : Auto / IPv4 / IPv6
Geo Bypass     : aktif/nonaktif
User-Agent     : custom UA string
HTTP Chunk     : ukuran chunk HTTP (KiB)
Sleep Interval : jeda antar request (detik)
```

### FFmpeg

```
Location    : path ke binary ffmpeg kustom (opsional)
Threads     : jumlah thread FFmpeg (0 = auto)
Timestamps  : preserve file modification timestamps
```

### Subtitles

```
Languages        : koma-separated (misal: en,id,ja) atau "all"
Format           : best, srt, vtt, ass, lrc, ...
Convert          : none, srt, vtt, ass, lrc
Embed            : embed subtitle ke container
Manual Subs      : unduh subtitle manual
Auto-generated   : unduh subtitle auto (YouTube, dll.)
```

---

## 🏗️ Build & Distribusi

### Build dengan PyInstaller

```bash
# Install PyInstaller
pip install pyinstaller

# Build (one-folder distribution)
pyinstaller --noconfirm video_downloader.spec
```

Output akan tersedia di `dist/Video Downloader/`.

> **Mengapa one-folder?** One-folder lebih mudah diinspeksi, lebih mudah dipasangkan dengan distribusi FFmpeg terpercaya, dan startup lebih cepat dibanding one-file. One-file mengalami startup lebih lambat karena perlu ekstraksi ke temp dan penanganan asset Qt/FFmpeg yang lebih kompleks.

### Distribusi dengan FFmpeg

Aplikasi ini **tidak pernah mengunduh binary secara otomatis**. Untuk mendistribusikan dengan FFmpeg:

1. Unduh FFmpeg dari sumber resmi: https://ffmpeg.org/download.html
2. Tempatkan `ffmpeg.exe` dan `ffprobe.exe` di folder distribusi (atau di `PATH`)
3. Opsional: set path di **Settings → FFmpeg → Location**

---

## 🧪 Testing

### Menjalankan Test Suite

```bash
# Install dependensi dev
pip install -r requirements-dev.txt

# Jalankan semua test
python -m pytest -q

# Dengan output verbose
python -m pytest -v

# Test spesifik
python -m pytest tests/test_formats.py -v
python -m pytest tests/test_integrity.py -v
```

### Coverage Test

```
tests/test_batch_dialog.py      — Batch URL input dialog
tests/test_browser_cookies.py   — Autentikasi cookie browser
tests/test_container_ui.py      — UI pemilihan container
tests/test_containers.py        — Logika container
tests/test_duplicates.py        — Deteksi duplikat URL
tests/test_formats.py           — Format selector & logika resolusi/codec/fps/HDR
tests/test_hdr_ui.py            — UI pemilihan HDR/dynamic range
tests/test_history.py           — SQLite history repository
tests/test_integrity.py         — Verifikasi integritas post-download
tests/test_log_highlighter.py   — Highlight log severity
tests/test_pause_resume.py      — Mekanisme pause/resume
tests/test_playlist_dialog.py   — Dialog pemilihan playlist
tests/test_queue_eta.py         — Estimasi ETA antrian
tests/test_settings_management.py — Export/import/reset settings
tests/test_settings_runtime.py  — Konfigurasi runtime yt-dlp
tests/test_size_estimation.py   — Estimasi ukuran pra-download
tests/test_utils.py             — Utilitas umum
tests/test_ytdlp_options.py     — Opsi & build_options yt-dlp
```

> Semua test berjalan **offline** — tidak memerlukan koneksi internet, kredensial, atau akun apapun.

---

## 🗂️ Struktur Proyek

```
video-downloader/
│
├── main.py                         # Entry point aplikasi
│
├── app/
│   ├── application.py              # Bootstrap & inisialisasi (QApplication, service, window)
│   └── constants.py                # APP_NAME, APP_VERSION, ORG_NAME
│
├── ui/
│   ├── main_window.py              # QMainWindow — toolbar, tab, shortcut, theme, drag-drop
│   ├── tabs.py                     # DownloaderTab, HistoryTab, LogTab
│   ├── dialogs.py                  # SettingsDialog, AboutDialog, PlaylistDialog, BatchDialog, dll.
│   ├── log_highlighter.py          # Pewarna severity log
│   └── styles.py                   # Dark/Light stylesheet Qt
│
├── services/
│   ├── ytdlp_service.py            # Wrapper yt-dlp: download, extract_info, estimate, verify
│   ├── integrity_service.py        # Post-download integrity: structural, FFprobe, hash, quarantine
│   ├── cookie_service.py           # Browser cookie & Netscape cookie file
│   └── ffmpeg_service.py           # Deteksi & lokasi FFmpeg/FFprobe
│
├── models/
│   └── download.py                 # DownloadRequest dataclass
│
├── repositories/
│   └── history_repository.py       # SQLite history CRUD
│
├── workers/
│   └── tasks.py                    # QThread workers untuk analisis & download async
│
├── utils/
│   ├── formats.py                  # Format selector, codec/resolution/fps/HDR utils
│   ├── containers.py               # Kompatibilitas container & codec
│   ├── duplicates.py               # Deteksi duplikat URL & media ID
│   ├── queue_eta.py                # Kalkulasi ETA antrian
│   ├── formatters.py               # Format ukuran, waktu, dll.
│   ├── validators.py               # Validasi URL & input
│   ├── security.py                 # Redaksi log (kredensial, token)
│   ├── paths.py                    # DATA_DIR, LOG_DIR, ensure_directories
│   └── logger.py                   # Setup logging dengan emitter Qt
│
├── data/                           # Database SQLite (history.db) — dibuat otomatis
├── logs/                           # Log aplikasi (app.log) — dibuat otomatis
├── tests/                          # Unit test suite (18 test files)
│
├── requirements.txt                # Dependensi runtime
├── requirements-dev.txt            # Dependensi development + test
├── video_downloader.spec           # PyInstaller build spec
└── .gitignore
```

---

## 🔧 Troubleshooting

### Extractor Tidak Berfungsi / Situs Tidak Didukung

```bash
# Update yt-dlp ke versi terbaru
pip install -U yt-dlp
```

Situs yang sebelumnya berfungsi bisa rusak karena perubahan di sisi situs atau update yt-dlp. Selalu pastikan yt-dlp up-to-date.

### Video Memerlukan Login

1. Buka **Settings → Cookies & Authentication**
2. Pilih **Browser** (Chrome/Firefox/Edge) yang sudah login ke situs tersebut
3. **Tutup browser** jika database cookie-nya terkunci
4. Alternatif: export `cookies.txt` dan gunakan **Cookie File** path
5. Nilai cookie **tidak pernah disimpan** di pengaturan atau log aplikasi

### Konversi / Merge Gagal

```bash
# Verifikasi FFmpeg terinstal dengan benar
ffmpeg -version
ffprobe -version

# Jika menggunakan binary kustom:
# Settings > FFmpeg > Location > arahkan ke folder berisi ffmpeg.exe
```

### File Korup Setelah Download

- File korup dipindahkan otomatis ke `<output-folder>/<nama>.corrupt-YYYYMMDD-HHMMSS`
- Cek tab **Log** untuk detail error integritas
- Coba unduh ulang — bisa jadi masalah koneksi sementara

### Log Teknis

```
logs/app.log
```

Log dirotasi dan **diredaksi** — tidak mengandung password, cookie, token, atau data sensitif lainnya.

### Error Umum

| Error | Solusi |
|---|---|
| `No such extractor` | Update yt-dlp |
| `Unable to download webpage` | Cek koneksi / proxy / VPN |
| `This video is private` | Aktifkan browser cookies |
| `Requested format is not available` | Pilih format lain atau gunakan "Auto" |
| `ffmpeg not found` | Install FFmpeg dan tambahkan ke PATH |
| `HTTP Error 429` | Aktifkan rate limit & sleep interval di Settings |
| `Cookie database is locked` | Tutup browser yang sedang terbuka |

---

## 🏛️ Arsitektur

```
┌─────────────────────────────────────────────────────┐
│                      main.py                         │
│              (Entry point, bootstrap)                │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────▼─────────────┐
         │      app/application.py   │
         │  (QApplication + wiring)  │
         └─────────────┬─────────────┘
                       │
    ┌──────────────────▼──────────────────┐
    │           ui/main_window.py          │
    │  (QMainWindow, toolbar, tabs, theme) │
    └──┬──────────────┬───────────────┬───┘
       │              │               │
  DownloaderTab   HistoryTab       LogTab
       │
  ┌────▼────────────────────────────────┐
  │           workers/tasks.py           │
  │   (QThread: analyse, download)       │
  └────┬────────────────────────────────┘
       │
  ┌────▼──────────────────────────────────┐
  │         services/ytdlp_service.py      │
  │  (download, extract_info, estimate,    │
  │   verify, build_options, formatters)   │
  └────┬──────────────────────────────────┘
       │
  ┌────▼──────────┐  ┌──────────────────┐
  │  integrity_   │  │  cookie_service  │
  │  service.py   │  │  ffmpeg_service  │
  └───────────────┘  └──────────────────┘
       │
  ┌────▼─────────────────────────────────┐
  │           utils/ & models/            │
  │  formats, containers, duplicates,     │
  │  queue_eta, validators, security, ... │
  └──────────────────────────────────────┘
       │
  ┌────▼─────────────────┐
  │  repositories/        │
  │  history_repository   │
  │  (SQLite, CRUD)       │
  └──────────────────────┘
```

---

## 🌐 Situs yang Didukung

Video Downloader mendukung **semua situs yang didukung oleh versi yt-dlp yang terinstal** — lebih dari 1.000 situs termasuk:

YouTube, YouTube Music, Twitter/X, Instagram, TikTok, Facebook, Vimeo, Dailymotion, Twitch, NicoNico, Bilibili, Reddit, SoundCloud, Bandcamp, BBC iPlayer, Arte, ZDF, dan ribuan lainnya.

Lihat daftar lengkap di aplikasi: **Toolbar → Supported Websites**

> Kompatibilitas bergantung pada versi yt-dlp yang terinstal dan perubahan di sisi situs. Update yt-dlp secara rutin.

---

## 🔒 Keamanan & Privasi

- **Tidak ada binary otomatis** — aplikasi tidak pernah mengunduh executable dari internet
- **Kredensial tidak dicatat** — nilai cookie, password, token diredaksi dari semua log
- **Path traversal protection** — verifikasi integritas menggunakan `is_relative_to()` untuk mencegah path escape
- **Validasi ketat cookie** — validasi struktural dan batas ukuran sebelum digunakan
- **Pengaturan tanpa data sensitif** — export settings tidak mengandung proxy, cookie, atau autentikasi
- **Quarantine aman** — file korup dipindahkan (bukan dihapus) dengan timestamp unik

---

## ⚖️ Legal & Kredit

> **Gunakan aplikasi ini hanya untuk media yang Anda miliki izin atau hak hukum untuk mengunduh.**
>
> Aplikasi ini **tidak** membypass DRM, paywall, atau kontrol akses. Ini **bukan** aplikasi resmi yt-dlp.

### Dibangun dengan

| Pustaka | Keterangan | Lisensi |
|---|---|---|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Download engine, format extraction | Unlicense |
| [FFmpeg](https://ffmpeg.org/) | Konversi, muxing, thumbnail | LGPL/GPL |
| [PySide6](https://doc.qt.io/qtforpython-6/) | GUI framework (Qt for Python) | LGPL |
| [requests](https://docs.python-requests.org/) | HTTP utilities | Apache 2.0 |

---

<div align="center">

**Video Downloader v1.0.0** — Dibuat dengan ❤️ menggunakan Python, PySide6, yt-dlp, dan FFmpeg.

*Unduh lebih cerdas. Unduh lebih lengkap.*

</div>
