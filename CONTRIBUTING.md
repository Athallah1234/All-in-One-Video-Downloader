# Panduan Kontribusi

Terima kasih telah tertarik untuk berkontribusi pada **Simple Video Downloader**! 🎉

---

## 📋 Daftar Isi

- [Kode Etik](#kode-etik)
- [Cara Berkontribusi](#cara-berkontribusi)
- [Melaporkan Bug](#melaporkan-bug)
- [Mengusulkan Fitur](#mengusulkan-fitur)
- [Setup Development](#setup-development)
- [Standar Kode](#standar-kode)
- [Panduan Commit](#panduan-commit)
- [Proses Pull Request](#proses-pull-request)

---

## Kode Etik

Proyek ini mengadopsi prinsip-prinsip Contributor Covenant. Dengan berpartisipasi, Anda diharapkan untuk:
- Bersikap hormat dan inklusif
- Menerima kritik konstruktif dengan terbuka
- Fokus pada apa yang terbaik untuk komunitas

---

## Cara Berkontribusi

Ada banyak cara untuk berkontribusi:

- 🐛 **Melaporkan bug** — buka Issue dengan detail lengkap
- 💡 **Mengusulkan fitur** — diskusikan di Discussions sebelum membuat PR
- 🔧 **Memperbaiki bug** — fork, fix, dan buat Pull Request
- 📖 **Memperbaiki dokumentasi** — README, CHANGELOG, komentar kode
- 🌐 **Terjemahan** — bantu terjemahkan UI ke bahasa lain
- 🧪 **Menulis test** — tingkatkan cakupan pengujian

---

## Melaporkan Bug

Sebelum melaporkan, pastikan:
1. Cek [Issues](https://github.com/username/simple-video-downloader/issues) — mungkin sudah dilaporkan
2. Pastikan menggunakan versi terbaru

Saat membuat issue baru, sertakan:

```
**Deskripsi Bug**
Penjelasan singkat masalahnya.

**Langkah Reproduksi**
1. Buka aplikasi
2. Masukkan URL '...'
3. Pilih mode '...'
4. Klik Download
5. Error terjadi: '...'

**Perilaku yang Diharapkan**
Apa yang seharusnya terjadi.

**Screenshot / Log**
Tempel log dari tab Log di aplikasi.

**Environment**
- OS: [misal: Windows 11 64-bit]
- Python: [misal: 3.12.2]
- yt-dlp: [misal: 2026.8.19]
- PySide6: [misal: 6.8.1]
- FFmpeg: [misal: 7.1 (jika relevan)]
```

---

## Mengusulkan Fitur

1. Buka [Discussions → Ideas](https://github.com/username/simple-video-downloader/discussions)
2. Jelaskan use case dan manfaatnya
3. Diskusikan pendekatan implementasi
4. Setelah ada kesepakatan, baru buat PR

---

## Setup Development

```bash
# 1. Fork repository di GitHub
# 2. Clone fork Anda
git clone https://github.com/YOUR_USERNAME/simple-video-downloader.git
cd simple-video-downloader

# 3. Tambahkan upstream remote
git remote add upstream https://github.com/username/simple-video-downloader.git

# 4. Buat virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 5. Install dependensi + dev dependencies
pip install -r requirements.txt
pip install pytest pytest-cov

# 6. Verifikasi semua test lulus
python -m pytest tests/ -v
```

---

## Standar Kode

### Python Style
- Ikuti **PEP 8** — gunakan snake_case untuk variabel/fungsi, PascalCase untuk kelas
- Panjang baris maksimum **100 karakter**
- Gunakan **type hints** untuk parameter dan return value
- Tulis **docstring** untuk setiap fungsi/kelas publik

### Prinsip Arsitektur
- **Single Responsibility**: setiap modul punya satu tanggung jawab
- **GUI Thread Safety**: semua mutasi Task harus di GUI thread — jangan ubah dari worker thread
- **No Polling**: gunakan Qt Signals/Slots, bukan loop polling
- **Allowlist, bukan Blocklist**: untuk validasi input pengguna, preferensikan allowlist

### Apa yang Tidak Boleh Dilakukan
- ❌ Jangan tambahkan dependensi baru tanpa diskusi
- ❌ Jangan simpan credentials/password ke file atau log
- ❌ Jangan buat subprocess tanpa `CREATE_NO_WINDOW` di Windows
- ❌ Jangan bypass validasi template nama file
- ❌ Jangan commit file `data/`, `logs/`, `downloads/`, atau `.venv/`

---

## Panduan Commit

Gunakan format **Conventional Commits**:

```
<type>(<scope>): <deskripsi singkat>

[body opsional]

[footer opsional]
```

**Tipe yang didukung:**

| Tipe | Kapan digunakan |
|------|----------------|
| `feat` | Fitur baru |
| `fix` | Perbaikan bug |
| `docs` | Perubahan dokumentasi |
| `refactor` | Refaktor kode tanpa mengubah fungsionalitas |
| `test` | Tambah atau perbaiki test |
| `chore` | Pembaruan dependensi, config, dll. |
| `perf` | Peningkatan performa |
| `style` | Format kode (tidak mengubah logika) |

**Contoh:**
```
feat(core): tambah dukungan proxy SOCKS5h dengan remote DNS
fix(queue): cegah race condition saat retry bersamaan dengan cancel
docs: perbarui panduan instalasi FFmpeg untuk Windows
test(proxy): tambah test case untuk IPv6 address di SOCKS5 host
```

---

## Proses Pull Request

1. **Sync** dengan upstream sebelum mulai:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Buat branch** dari `main`:
   ```bash
   git checkout -b fix/nama-bug
   # atau
   git checkout -b feat/nama-fitur
   ```

3. **Buat perubahan** dan pastikan:
   - [ ] Semua test lulus: `python -m pytest tests/ -v`
   - [ ] Tidak ada regresi di fitur lain
   - [ ] Docstring ditambahkan untuk kode baru
   - [ ] Test baru ditambahkan untuk bug fix / fitur

4. **Push dan buat PR**:
   ```bash
   git push origin feat/nama-fitur
   ```
   Lalu buka Pull Request di GitHub.

5. **Isi PR template** dengan lengkap (jenis perubahan, cara testing, screenshot jika UI)

6. **Tunggu review** — maintainer akan memberikan feedback dalam beberapa hari

---

Terima kasih sudah berkontribusi! 🙏
