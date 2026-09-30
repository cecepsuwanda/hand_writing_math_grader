# hand_writing_math_grader

Aplikasi **CLI Python** untuk memeriksa jawaban soal matematika tulisan tangan dari PDF (recognition → validasi SymPy/LLM → grading berbasis rubric).

**Prinsip arsitektur (wajib):** MVC, SOLID, clean code, OOP + functional programming — lihat [docs/architecture.md](docs/architecture.md) dan [docs/conventions.md](docs/conventions.md).

## Dokumentasi

| Dokumen | Keterangan |
|---------|------------|
| [docs/README.md](docs/README.md) | Indeks dokumentasi |
| [docs/architecture.md](docs/architecture.md) | Pipeline, lapisan MVC, peta folder, topic pack, kontrak CLI |
| [docs/conventions.md](docs/conventions.md) | Aturan coding dan domain (SOLID, OOP+FP, recognition fidelity, grading) |
| [docs/development-phases.md](docs/development-phases.md) | Status phase 1–9 + acceptance criteria |
| [docs/math-topics.md](docs/math-topics.md) | Silabus, status per bab, topic pack, capability |
| [docs/testing.md](docs/testing.md) | Konvensi pytest + peta kelas tes |

## Cara pakai singkat

1. Install dependensi (sekali):

```bat
install.bat
```

2. Taruh PDF jawaban di `data/input/jawaban/`, kunci `.tex` di `data/input/kunci_jawaban/`.
3. Jalankan pipeline:

```bat
run.bat
run.bat process smoke_inequality.pdf
```

Atau langsung Python:

```bash
python -m app.cli menu
python -m app.cli process smoke_inequality.pdf
```

Nama file tanpa path dicari di `data/input/jawaban/` (kunci: `data/input/kunci_jawaban/`). Tanpa argumen PDF, CLI menampilkan daftar pilihan.

### Menu

`run.bat` / `menu` membuka menu:

| No | Menu | Subcommand setara |
|----|------|-------------------|
| 1 | Pilih topik grader | `--topic <id>` |
| 2 | Ingest kunci jawaban (.tex) | `ingest-kunci` |
| 3 | Pilih PDF → render → crop ink (konfirmasi) | `propose-crops` |
| 4 | Crop ulang dari `page_*_regions.json` | `recrop` |
| 5 | Kenali nomor soal → `question_crops/question_*.json` | `label-questions` |
| 6 | Muat ulang nomor soal dari JSON yang sudah diedit | `relabel-questions` |
| 7 | Lanjutkan grading (recognize → report) dari crops | `process --use-existing-crops` |
| 8 | Keluar | — |

### Flag penting

| Flag | Keterangan |
|------|------------|
| `--config <path>` | Config lain (default `app/config/config.yaml`); letakkan **sebelum** subcommand |
| `--topic <id>` | Topic pack (`1.5` default, `2`); lihat [docs/math-topics.md](docs/math-topics.md) |
| `--run <nama_pdf>` | Pilih folder hasil untuk subcommand tanpa argumen PDF |
| `--yes` | Lewati konfirmasi crop / label (non-interaktif) |
| `--use-existing-crops` | `process` / `recognize`: pakai `page_*_regions.json` + crops yang ada, tanpa propose ulang |

Model dan endpoint Ollama diambil dari `app/config/config.yaml`; override lewat env `OLLAMA_BASE_URL`, `OLLAMA_VISION_MODEL`, `OLLAMA_REASONING_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_MAX_RETRIES`.

> **Privasi:** model bersufiks `-cloud` di `config.yaml` mengirim gambar jawaban ke luar mesin. Untuk data mahasiswa, pakai model Ollama lokal.

### Nomor soal (`question_crops`)

`ingest-kunci` (menu 2) wajib dijalankan dulu — `label-questions` butuh `exam_schema.json`. Menu 5 dijalankan manual setelah crop OK. Sistem membaca label nomor soal di tiap crop (vision), lalu menulis **satu file per soal di kunci** (7 soal → 7 file):

`data/output/<nama_pdf>/crops/question_crops/question_003.json`:

```json
{ "question_number": 3, "stem": "...", "crops": ["page_001_region_02_solution.png", "page_002_region_00_solution.png"] }
```

Satu soal boleh punya beberapa crop (lintas halaman), dan satu crop boleh muncul di dua file soal. Crop tanpa label ikut soal sebelumnya (urutan baca). Jika vision tidak menemukan label, sistem membagi satu crop per soal bila jumlahnya sama; kalau tidak, daftar dikosongkan agar diisi user. Edit daftar `"crops"`, lalu jalankan menu 6 untuk memvalidasi dan memuat ulang (sama seperti pola crop → recrop).

Saat grading (menu 7 / `process`): kalau `question_crops/` ada, nomor soal diambil dari file tersebut, dan file yang tidak valid (soal di luar kunci atau nama crop tidak dikenal) menghentikan run. Kalau folder itu belum ada, run tetap jalan dengan **peringatan** dan nomor soal ditebak model per crop.

### Artefak

Setiap PDF yang diproses mendapat folder sendiri di `data/output/` sesuai nama file (tanpa `.pdf`):

```text
data/output/
  standards/exam_001/          # kunci/rubric, dipakai bersama
  <nama_pdf>/
    pages/  crops/  recognition/  questions/
    report.json  summary.csv  report.html  report.tex
```

`report.tex` adalah laporan satu file per mahasiswa: untuk tiap soal berisi gambar crop jawaban (dari `crops/question_crops/`, atau `image_regions` bila peta belum ada), hasil bacaan OCR per langkah, dan komentar penilaian (skor, status validasi, feedback, komponen, jawaban akhir). Path gambar relatif terhadap folder run, jadi kompilasi dilakukan manual dari folder tersebut:

```bash
cd "data/output/<nama_pdf>"
pdflatex report.tex
```

**Pengosongan output:** hanya folder `data/output/<nama_pdf>/` milik PDF tersebut yang dikosongkan, di awal `process`, `propose-crops`, dan menu 3. Dengan `process --use-existing-crops`, folder `crops/` dipertahankan. Menu 7 tidak mengosongkan folder run; ia hanya mengosongkan `recognition/` dan `questions/` sebelum menulis ulang. `recognize` / `extract` hanya mengosongkan folder output-nya sendiri. `standards/` dan hasil PDF lain tidak pernah disentuh.

**Pemilihan run:** subcommand tanpa argumen PDF (`recrop`, `label-questions`, `relabel-questions`, `latex`, `validate`, `grade`, `report`) memakai `--run <nama_pdf>`. Tanpa `--run`: jika hanya ada satu folder hasil, folder itu dipakai; jika lebih dari satu, terminal interaktif menampilkan pilihan, sedangkan non-interaktif gagal dan meminta `--run`.

**Exit code:** `0` sukses, `1` error domain (`MathGraderError`), `2` error tak terduga.

### Tes

```bash
pytest -q
```

Konvensi: [docs/testing.md](docs/testing.md). Tes tidak memanggil Ollama.

### Smoke live (butuh Ollama)

```bash
python -m app.cli process smoke_inequality.pdf
```

atau `scripts\smoke_live.bat`. Sample PDF: `data\input\jawaban\smoke_inequality.pdf`. Tidak termasuk suite `pytest` default. Hasil yang diharapkan: progress per tahap, ringkasan skor, dan artefak lengkap di `data/output/smoke_inequality/`.

## Status

Phase 1–9 selesai ([docs/development-phases.md](docs/development-phases.md)). MVP domain: **pertidaksamaan (topik 1.5)**; pack `2` (nilai mutlak) terdaftar. API opsional: `python -m app.api` (FastAPI, bukan pengganti CLI).

## Agent guidance

- Cursor rules: `.cursor/rules/`
- Skills: `.cursor/skills/` (`extend-math-grader`, `review-math-grader-compliance`, `write-math-grader-tests`)
