# hand_writing_math_grader

Aplikasi **CLI Python** untuk memeriksa jawaban soal matematika tulisan tangan dari PDF (recognition → validasi SymPy/LLM → grading berbasis rubric).

**Prinsip arsitektur (wajib):** MVC, SOLID, clean code, OOP + functional programming — lihat [docs/architecture.md](docs/architecture.md) dan [docs/conventions.md](docs/conventions.md).

## Dokumentasi

| Dokumen | Keterangan |
|---------|------------|
| [plan_ai_math_grader_ollama.md](docs/plan_ai_math_grader_ollama.md) | Spesifikasi lengkap |
| [topik.md](docs/topik.md) | Silabus domain matematika |
| [docs/README.md](docs/README.md) | Indeks panduan pengembangan |
| [docs/architecture.md](docs/architecture.md) | Arsitektur MVC + SOLID/clean/OOP+FP |
| [docs/development-phases.md](docs/development-phases.md) | Phase 1–9 |
| [docs/math-topics.md](docs/math-topics.md) | Status domain per bab |
| [docs/conventions.md](docs/conventions.md) | Prinsip arsitektur wajib, SOLID, clean coding, OOP+FP |

## Cara pakai singkat

1. Install dependensi (sekali):

```bat
install.bat
```

2. Taruh PDF jawaban di `data/input/jawaban/`, kunci di `data/input/kunci_jawaban/`.
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

`run.bat` / `menu` membuka menu: ingest kunci, proses PDF, atau keluar.

Di awal `process`, isi `data/output/` dikosongkan (kecuali `standards/`).

### Smoke live (butuh Ollama)

```bash
python -m app.cli process smoke_inequality.pdf
```

atau `scripts\smoke_live.bat`. Sample PDF: `data\input\jawaban\smoke_inequality.pdf`. Tidak termasuk suite `pytest` default.

## Status

MVP domain: **pertidaksamaan (topik 1.5)**. Implementasi mengikuti `docs/development-phases.md`.

## Agent guidance

- Cursor rules: `.cursor/rules/`
- Skills: `.cursor/skills/`
