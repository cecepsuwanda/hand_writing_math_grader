---
name: implement-math-grader-phase
description: >-
  Implements one Math Grader development phase (PDF, Vision, Extract, LaTeX,
  SymPy, LLM validator, grading, report, CLI polish) using MVC, SOLID, and
  CLI-first conventions. Use when the user asks to implement a phase, scaffold
  the app, continue development, add render/recognize/validate/grade CLI, or
  build the next pipeline stage.
---

# Implement Math Grader Phase

## Sebelum coding

1. Baca `docs/development-phases.md` dan inspect repo (`app/`, `tests/`).
2. Tentukan **satu** phase berikutnya yang belum selesai (jangan loncat).
3. Baca detail phase di [phases.md](phases.md) bila perlu.
4. Hormati rules proyek: CLI-first, MVC, recognition ≠ grading.
5. Cek domain aktif di `docs/math-topics.md` (MVP: topik 1.5 pertidaksamaan). Jangan loncat bab silabus.

## Workflow

Salin dan centang:

```text
Phase progress:
- [ ] Identifikasi phase + acceptance criteria
- [ ] Scaffold folder MVC jika belum ada
- [ ] Interfaces + DI untuk dependency baru
- [ ] Implement service / pure function
- [ ] Controller tipis + View CLI (jika entry point dibutuhkan)
- [ ] Tests + jalankan tests
- [ ] Artefak intermediate tersimpan
- [ ] Tidak merusak phase sebelumnya
```

### Scaffold (jika `app/` belum ada)

Buat struktur dari `docs/architecture.md`:

`controllers/`, `views/`, `models/`, `services/`, `functions/`, `interfaces/`, `prompts/`, plus `cli.py` and `config/` (package + `config.yaml`).

### Aturan implementasi

- Controller: orkestrasi saja — tidak memanggil Ollama/SymPy langsung.
- View: presentasi terminal saja.
- Service OOP + injection lewat `interfaces/`.
- Transformasi deterministik → `app/functions/` (pure).
- Model vision/reasoning dari config — jangan hard-code.
- Recognition: jangan koreksi/mengarang jawaban mahasiswa.
- Validasi: SymPy dulu, LLM fallback; schema-validate JSON LLM.
- `process`: dukung pilih PDF dari `data/input/jawaban/`; kosongkan `data/output/` di awal (kecuali `standards/`).
- Jangan tambah FastAPI/Streamlit di phase ini kecuali user eksplisit minta **setelah** MVP CLI.

### Setelah selesai

- Laporkan phase yang dikerjakan, file utama, cara menjalankan test/CLI.
- Sebut acceptance criteria yang terpenuhi / yang masih terbuka.

## Referensi

- [phases.md](phases.md) — ringkasan Phase 1–9
- `docs/architecture.md`, `docs/conventions.md`, `docs/math-topics.md`
- `docs/topik.md` — silabus domain
- `docs/plan_ai_math_grader_ollama.md` §21, §23, §31, §33, §35
