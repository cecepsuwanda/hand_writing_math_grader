# hand_writing_math_grader

Aplikasi **web lokal** (FastAPI + HTMX) untuk memeriksa jawaban soal matematika tulisan tangan dari PDF (recognition → validasi SymPy/LLM → grading berbasis rubric).

**Prinsip arsitektur (wajib):** MVC, SOLID, clean code, OOP + functional programming — lihat [docs/architecture.md](docs/architecture.md) dan [docs/conventions.md](docs/conventions.md).

## Dokumentasi

| Dokumen | Keterangan |
|---------|------------|
| [docs/README.md](docs/README.md) | Indeks dokumentasi |
| [docs/architecture.md](docs/architecture.md) | Pipeline, lapisan MVC, peta folder, topic pack, kontrak web + API |
| [docs/conventions.md](docs/conventions.md) | Aturan coding dan domain (SOLID, OOP+FP, recognition fidelity, grading) |
| [docs/development-phases.md](docs/development-phases.md) | Status phase 1–9 + acceptance criteria |
| [docs/math-topics.md](docs/math-topics.md) | Silabus, status per bab, topic pack, capability |
| [docs/testing.md](docs/testing.md) | Konvensi pytest + peta kelas tes |

## Cara pakai singkat

1. Install dependensi (sekali):

```bat
install.bat
```

2. Jalankan server lalu buka `http://127.0.0.1:8000` di browser:

```bat
run.bat
```

Atau langsung Python:

```bash
python -m app.web                 # default web.host / web.port di config.yaml
python -m app.web --port 8765 --config path/to/config.yaml
```

Server hanya mendengarkan `127.0.0.1` (halaman menampilkan tulisan mahasiswa). Semua aset JS/CSS (htmx, Alpine.js, Konva.js, KaTeX) di-vendor, jadi tidak butuh internet.

### Alur halaman

| Langkah | Halaman / tombol | Hasil |
|---------|------------------|-------|
| 1 | Halaman awal → **Topik** → *Pilih* | Topic pack aktif (`1.5` default, `2`) + folder standar `standards/topik_<bab>` |
| 2 | **Kunci jawaban** → unggah `.tex` → *Ingest ke topik …* | `exam_schema.json`, `solutions/`, `rubrics/` |
| 3 | **PDF jawaban** → unggah PDF → *Propose crops* (atau *Mulai ulang*) | Job: folder run dikosongkan, halaman dirender, kotak ink diusulkan → editor crop |
| 4 | **Editor crop** (`/runs/<run>/crops`) | Gambar kotak baru dengan drag, geser/ubah ukuran, hapus (Del), atur urutan, set nomor soal & tipe → *Simpan & crop ulang* |
| 5 | **Label** (`/runs/<run>/labels`) — opsional | *Deteksi otomatis (vision)* lalu koreksi nomor soal per crop → *Simpan nomor soal* |
| 6 | Halaman run → *Transkripsi lalu review* | Job: recognize + extract dari crop, berhenti di **Review** |
| 7 | **Review** (`/runs/<run>/review`) | Edit langkah (`raw_text`, `symbolic`, role) dengan preview KaTeX, simpan per soal → *Nilai sekarang* |
| 8 | **Hasil** (`/runs/<run>/results`) | Skor per soal + langkah, unduh `report.pdf/html/tex/json`, `summary.csv`; *Nilai ulang* |

*Transkripsi + nilai langsung* di halaman run menjalankan langkah 6–8 tanpa berhenti di Review; *Nilai dari question.json* melanjutkan dari `question.json` yang sudah ada. Tahap panjang berjalan sebagai **job** dengan progress langsung (`/jobs/<id>`); satu run hanya boleh punya satu job aktif.

Kotak yang digambar tangan di editor crop memakai **padding 0** (crop persis sebesar kotak), sedangkan usulan ink otomatis tetap memakai margin dari `recognition.ink.*`. Kotak minimal 4 × 4 px dan harus berada di dalam halaman.

### Kunci jawaban per topik

Setiap topik punya folder standar sendiri di `data/output/standards/`, dinamai menurut nomor bab: pack `1.5` ke `topik_1`, pack `2` ke `topik_2`, dan seterusnya. Ingest menulis ke folder topik aktif; transkripsi dan grading membaca dari folder yang sama. Jadi kunci topik 1 dan topik 2 tidak saling menimpa. Topbar menampilkan topik yang sedang aktif. Selama user belum memilih topik, grading mengikuti `topic_id` di `exam_schema.json`, lalu `grading.topic_id` di `config.yaml`.

- Satu ingest = satu file kunci (dipilih dari daftar di halaman awal).
- Ingest ulang mengganti `solutions/` dan `rubrics/` di folder topik itu, jadi soal dari kunci lama tidak tersisa.
- Lokasi induk diatur `grading.standards_root` di `config.yaml` (default `data/output/standards`). Key lama `grading.standard_dir` diabaikan dengan peringatan.
- **Migrasi:** folder lama `standards/exam_001` tidak dipakai lagi. Ingest kunci sekali dengan topik `1.5` untuk mengisi `topik_1`, lalu `exam_001` boleh dihapus.

Model dan endpoint Ollama diambil dari `app/config/config.yaml`; override lewat env `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL`, `OLLAMA_REASONING_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`.

> **Privasi:** model bersufiks `-cloud` di `config.yaml` mengirim gambar jawaban ke luar mesin (halaman awal menampilkan peringatan "Model cloud aktif"). Untuk data mahasiswa, pakai model Ollama lokal.

### Aturan penilaian

- **Confidence LLM:** bila SymPy tidak bisa memutuskan, `reasoning_model` menilai langkah atau jawaban akhir. Putusan VALID/INVALID dengan confidence di bawah `grading.llm_min_confidence` (default `0.7`, rentang 0–1), atau tanpa confidence sama sekali, menjadi UNCERTAIN: setengah poin dan soal ditandai REVIEW_REQUIRED.
- **Rubric hilang atau tidak valid:** soal itu dilewati dengan peringatan dan soal lain tetap dinilai. `grading.json` lama di folder soal itu dihapus. Di report soal tersebut tampil skor 0, REVIEW_REQUIRED, dan label **TIDAK DINILAI**; nilai maksimumnya diambil dari rubric bawaan topik. Soal di kunci yang tidak punya folder jawaban diberi label **TIDAK DIJAWAB**. Kalau semua soal tidak punya rubric, grade berhenti dengan error.
- **Total rubric:** jumlah `points` di `criteria` harus sama dengan `maximum_score`. Kalau tidak, rubric dianggap tidak valid (diperlakukan seperti rubric hilang).
- **`validation.json` usang:** tahap validasi menyimpan sidik jari langkah dan jawaban akhir dari `question.json`. Kalau `question.json` diedit setelah itu, grading menolak `validation.json` lama; *Nilai sekarang* menjalankan validasi ulang sebelum grading. File lama tanpa sidik jari tetap diterima.
- **Bagian rubric:** langkah ber-role `critical_points`/`sign_chart`/`figure`/`hp` dinilai di bagian rubric masing-masing, bukan dari pool algebra. Titik kritis dibandingkan sebagai himpunan (`x=0 atau x=1` sama dengan dua langkah terpisah); titik ekstra yang salah mengurangi nilai bila ditulis di langkah ber-role `critical_points` (persamaan di langkah aljabar biasa tidak dihitung sebagai titik ekstra). Kalau tidak ada langkah aljabar sama sekali, poin algebra menjadi setengah dan soal perlu review. Gambar tanpa garis bilangan di kunci mendapat UNCERTAIN, bukan VALID otomatis.
- **Uji tanda:** langkah `sign_chart` harus berupa substitusi ke ekspresi pertidaksamaan terakhir (mis. `(-3*(-5))/((-5+4)*(-5-2)) = 15/7`, `... = 15/7 > 0`, atau `x = -5 => ... > 0`). Pernyataan numerik yang benar tapi tidak terkait (`2 > 1`), atau yang hanya menyebut `f(0) = ...`, mendapat UNCERTAIN dan diperiksa LLM.
- **Notasi yang dikenali:** desimal sama dengan pecahan (`0.5` = `0,5` = `1/2`). Akar berindeks `x_1`, `x_{1}`, dan `x₁` dibaca sebagai `x` (topik 1.5 dan 2; `x1` tanpa garis bawah tidak diubah). Simbol Unicode `≤ ≥ ≠ ∞ − ×`, kata `atau`/`dan`, HP kosong (`\emptyset`, `\{\}`), semua bilangan real (`\mathbb{R}`, `HP = R`), dan notasi pembentuk himpunan (`\{x \mid x < 3\}`) juga dikenali. `y = 2 atau y = 3` dibaca sebagai akar, sedangkan `y = 2x + 1` tetap dibaca sebagai fungsi.
- **Role langkah:** role di `question.json` diubah ke huruf kecil tanpa spasi (`"HP"` → `hp`). `question.json` lama yang role-nya ditulis tidak kanonik bisa memiliki sidik jari berbeda; jalankan ulang *Nilai sekarang* bila grading menolak `validation.json`.
- **Nomor soal sementara:** crop tanpa nomor yang langkah pertamanya menyalin stem soal N diberi nomor N, asalkan soal N belum terbaca dari crop bernomor (status tetap `provisional` agar dicek). Crop tanpa nomor lainnya diberi nomor setelah nomor terbesar di kunci (kunci 1–7 → 8, 9, …), tidak dinilai, muncul sebagai peringatan di report, dan tidak menambah nilai maksimum.

### Nomor soal (`question_crops`)

Ingest kunci wajib dijalankan dulu — halaman Label butuh `exam_schema.json`. *Deteksi otomatis (vision)* membaca label nomor soal di tiap crop, lalu menulis **satu file per soal di kunci** (7 soal → 7 file):

`data/output/<nama_pdf>/crops/question_crops/question_003.json`:

```json
{ "question_number": 3, "stem": "...", "crops": ["page_001_region_02_solution.png", "page_002_region_00_solution.png"] }
```

Satu soal boleh punya beberapa crop (lintas halaman), dan satu crop boleh muncul di dua soal (isi `3, 4` di kolom nomornya). Crop tanpa label ikut soal sebelumnya (urutan baca); crop yang balasan vision-nya tidak terbaca juga ikut soal sebelumnya, tetapi didaftar sebagai peringatan "label tidak terbaca" agar dicek. Jika vision tidak menemukan label, sistem membagi satu crop per soal bila jumlahnya sama; kalau tidak, daftar dikosongkan agar diisi user. Form *Simpan nomor soal* memvalidasi lagi: soal di luar kunci atau nama crop tak dikenal = error; soal tanpa crop atau crop tanpa nomor = peringatan.

Saat transkripsi: kalau `question_crops/` ada, nomor soal diambil dari file tersebut, dan file yang tidak valid menghentikan job. Kalau folder itu belum ada, job tetap jalan dengan **peringatan** di progress dan nomor soal ditebak model per crop.

### Tinjau transkripsi (`question.json`)

*Transkripsi lalu review* berhenti setelah tulisan tangan dikenali dan digabung per soal. Halaman Review menampilkan tiap langkah: `role`, `raw_text`, dan `symbolic` (jenis + `repr`) dengan preview KaTeX. Langkah yang perlu dicek diberi tanda: `low_confidence` (di bawah `recognition.review_min_confidence`, default 0.8), `uncertain_mark` (`[uncertain]` di `raw_text`), atau `missing_symbolic` (`repr` kosong). Tambah/hapus langkah, simpan per soal, lalu *Nilai sekarang* untuk LaTeX → validasi → grading → report.

SymPy membaca **`symbolic.repr`**; `raw_text` hanya untuk tampilan dan laporan, jadi koreksi isi matematika di `repr` (preview yang gagal menandakan `repr` tidak terbaca SymPy). Untuk soal yang disimpan, `latex_source.tex` dihapus agar `student.tex` dibangun ulang dari langkah yang sudah diperbaiki. `question.json` ditolak bila tidak terbaca, `question_number` tidak cocok dengan nama folder, atau ada `step_number` ganda.

Kalau Anda mengedit `question.json` di luar aplikasi, pakai *Nilai dari question.json* (atau *Nilai sekarang*), **bukan** transkripsi ulang: transkripsi mengenali ulang tulisan tangan lalu mengosongkan `questions/` (setelah pengenalan berhasil). Penilaian dari `question.json` tidak menjalankan recognize/extract dan tidak menulis `question.json`; `latex_source.tex` yang lebih lama dari `question.json` dihapus otomatis. Model vision tidak dibutuhkan untuk langkah ini.

### Artefak

Setiap PDF yang diproses mendapat folder sendiri di `data/output/` sesuai nama file (tanpa `.pdf`):

```text
data/output/
  standards/
    topik_1/  topik_2/  ...    # kunci/rubric/schema per topik, dipakai bersama
  <nama_pdf>/
    pages/  crops/  recognition/  questions/
    report.json  summary.csv  report.html  report.tex  report.pdf  report.log
```

`report.tex` adalah laporan satu file per mahasiswa: untuk tiap soal berisi gambar crop jawaban (dari `crops/question_crops/`, atau `image_regions` bila peta belum ada), hasil bacaan OCR per langkah, dan komentar penilaian (skor, status validasi, feedback, komponen, jawaban akhir).

**`report.pdf` otomatis.** Begitu `report.tex` ditulis (tepat setelah grading, di setiap job yang menilai), sistem menjalankan `pdflatex` dua kali di folder run. Hasilnya `report.pdf` dan `report.log`; file sisa (`.aux`, dll.) dihapus. Kalau gagal (pdflatex tidak ditemukan, error LaTeX, atau `report.pdf` sedang dibuka viewer), hanya muncul **peringatan**: run tetap sukses dan `report.tex` tetap ada. Setelah masalahnya diatasi, kompilasi ulang dengan *Nilai ulang* di halaman hasil.

Pengaturan ada di `config.yaml` bagian `report.pdf`: `enabled`, `pdflatex_path` (kosong = cari di PATH, lalu lokasi standar MiKTeX / TeX Live; bisa juga lewat env `PDFLATEX_PATH`), `passes`, dan `timeout_seconds`.

**Pengosongan output:** hanya folder `data/output/<nama_pdf>/` milik PDF tersebut yang dikosongkan, di awal *Propose crops* / *Mulai ulang* (dan `POST /api/process`). Transkripsi dan penilaian tidak mengosongkan folder run; artefak lama baru diganti **setelah** pengenalan tulisan berhasil: JSON `recognition/` milik halaman yang sudah tidak ada dihapus, lalu `questions/` dikosongkan sebelum extract. Kalau pengenalan gagal (misalnya Ollama mati), `recognition/` dan `questions/` lama tetap utuh. `standards/` dan hasil PDF lain tidak pernah disentuh oleh run; hanya ingest yang menulis ke `standards/topik_<bab>`.

**Nama run** = nama PDF tanpa `.pdf` (karakter ilegal Windows diganti `_`). Path di URL divalidasi: nama run, crop, dan berkas unduhan tidak bisa keluar dari folder run.

**API JSON** (untuk skrip): `POST /api/process` (`{"pdf", "student_id"}` → 202 + `status_url`), `GET /api/jobs/<id>`, `GET /api/results/<question_id>?run=<nama_pdf>`, `GET /health`. Detail: [docs/architecture.md](docs/architecture.md#kontrak-web).

### Tes

```bash
pytest -q
```

Konvensi: [docs/testing.md](docs/testing.md). Tes tidak memanggil Ollama, tidak menyalakan uvicorn, dan tidak membuka browser (`TestClient` in-process).

### Smoke live (butuh Ollama)

```bash
python scripts/smoke_live.py smoke_inequality.pdf smoke_001
```

atau `scripts\smoke_live.bat`. Skrip ini menjalankan `POST /api/process` in-process lalu mencetak progress job. Sample PDF: `data\input\jawaban\smoke_inequality.pdf`. Tidak termasuk suite `pytest` default. Hasil yang diharapkan: progress per tahap, "Selesai: /runs/smoke_inequality/results", dan artefak lengkap di `data/output/smoke_inequality/`.

## Status

Phase 1–9 selesai ([docs/development-phases.md](docs/development-phases.md)). MVP domain: **pertidaksamaan (topik 1.5)**; pack `2` (nilai mutlak) terdaftar. Antarmuka: web UI lokal (`python -m app.web`); CLI interaktif lama sudah dihapus.

## Agent guidance

- Cursor rules: `.cursor/rules/`
- Skills: `.cursor/skills/` (`extend-math-grader`, `review-math-grader-compliance`, `write-math-grader-tests`)
