# Dokumentasi Math Grader

Panduan pengembangan aplikasi CLI untuk menilai lembar jawaban matematika tulisan tangan (PDF → recognition → validasi → grading).

## Sumber kebenaran

| Dokumen | Isi |
|---------|-----|
| [plan_ai_math_grader_ollama.md](plan_ai_math_grader_ollama.md) | Spesifikasi lengkap pipeline, data model, fase, DoD |
| [topik.md](topik.md) | Silabus domain matematika (bab 1–11) |
| [architecture.md](architecture.md) | MVC, dependency direction, struktur folder |
| [development-phases.md](development-phases.md) | Phase 1–9 dan acceptance criteria |
| [math-topics.md](math-topics.md) | Status domain per bab + urutan implementasi |
| [conventions.md](conventions.md) | SOLID, clean coding, OOP+FP, larangan |

## Target MVP

CLI Python (MVC) untuk soal **pertidaksamaan (topik 1.5)**, 1–5 halaman:

```text
PDF → PNG → Vision (Ollama) → JSON → LaTeX
  → SymPy (lalu LLM fallback) → rubric → skor + artefak audit
```

Roadmap domain mengikuti [`topik.md`](topik.md) / [math-topics.md](math-topics.md). Web UI / FastAPI **bukan** bagian MVP.

## Struktur aplikasi (target)

```text
app/
├── cli.py              # entry point
├── controllers/        # orkestrasi
├── views/              # presentasi CLI
├── models/             # schema domain
├── services/           # use-case + adapter
├── functions/          # pure transforms
├── interfaces/         # ports SOLID
└── prompts/
```

## Cara mulai (setelah kode ada)

Letakkan PDF jawaban di `data/input/jawaban/` dan kunci di `data/input/kunci_jawaban/`.

Pilih PDF secara interaktif (menu nomor/nama file):

```bash
python -m app.cli process
```

Atau sebutkan file langsung:

```bash
python -m app.cli process smoke_inequality.pdf
python -m app.cli process data/input/jawaban/smoke_inequality.pdf \
  --standard data/output/standards/exam_001 \
  --output data/output
```

Setiap `process` mengosongkan `data/output/` dulu (kecuali `standards/`), lalu menulis artefak baru.

## Panduan agent

- Rules: `.cursor/rules/`
- Skills: `.cursor/skills/implement-math-grader-phase`, `.cursor/skills/review-math-grader-compliance`
