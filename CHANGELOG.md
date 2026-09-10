# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Initial public release

---

## [1.0.0] - 2026-09-10

### Added
- Multi-mode download: Video, Audio, Subtitle, Playlist, Channel, Live Stream, 360°/VR, Metadata
- Concurrent download queue (up to 3 simultaneous downloads)
- Pause, resume, cancel, and retry per download
- Auto-retry with exponential backoff (configurable attempts, base delay, max delay)
- Manual retry-now — skip the backoff countdown immediately
- Real-time progress: speed, ETA, file size, fragment info, extractor name
- Download history stored in local SQLite database
- Download archive — skip already-downloaded URLs across sessions
- Format & quality selector: Best Video+Audio, MP4, WebM, Audio Only, Custom yt-dlp format
- Resolution options: 144p to 2160p (4K) or Best Available
- Audio format conversion: MP3, M4A, AAC, FLAC, WAV, Opus, Vorbis (requires FFmpeg)
- Audio quality: 96–320 kbps
- Output container selection: Auto, MP4, MKV, WebM
- Custom filename template with live preview and validation
- Subtitle download with language, format, and SRT conversion options
- Subtitle embedding into video file (requires FFmpeg)
- Thumbnail download and embedding (requires FFmpeg)
- Metadata embedding (title, artist, etc.) via FFmpeg
- Description and info JSON download
- SponsorBlock integration — remove sponsor segments automatically
- Playlist mode: start/end/items/reverse/random/ignore-unavailable controls
- Channel mode: All Videos, Latest N, Oldest N, Date Range, Custom Items
- Live stream recording with configurable max duration (1 second – 7 days)
- Live-from-start option for platforms that support it
- 360°/VR mode — equirectangular format detection from extractor metadata only
- aria2c integration as external downloader with configurable connections, splits, and min-split-size
- Proxy support: System, No Proxy, HTTP/HTTPS URL, SOCKS5, SOCKS5h (remote DNS)
- SOCKS5 credential fields (username/password, session-only, never stored)
- Rate limit, source address, and IP protocol (IPv4/IPv6) settings
- Authentication: site username/password (session-only), netrc file, browser cookies, Netscape cookie file
- Offline authentication likelihood detection from URL and domain signals
- FFmpeg auto-detection from PATH or configurable folder, with version and compatibility check
- aria2c auto-detection with version validation
- Light / Dark / System theme support with live switch
- System tray notifications on download complete or failed
- Clipboard URL monitoring with inline banner
- Bulk URL import from text file
- Keyboard shortcuts: Ctrl+L (focus URL), Ctrl+O (import), Ctrl+, (settings), Ctrl+Q (quit), F5 (refresh)
- Supported Websites browser with real-time search
- FFmpeg status dialog
- Log tab for real-time application log streaming
- Atomic settings write (write to .tmp then rename — no corruption)
- Session-key isolation: passwords and proxy credentials excluded from settings.json
- URL privacy: sensitive query parameters redacted before database storage
- Error credential redaction in log output
- Extra Options allowlist (safe subset of yt-dlp flags only)
- Filename template directory-traversal prevention
- Python version check (>=3.11) and dependency check at startup with Windows MessageBox fallback
- LRU-cached FFmpeg and aria2c binary inspection (cache key: path + mtime_ns + size)
- Graceful shutdown: prompts user when downloads are active, waits for workers before exiting
- Window position/size persistence across sessions
