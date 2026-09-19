# Tahapan Pengembangan

Kerjakan **satu phase per sesi/PR**. Jangan loncat ke FastAPI/Streamlit sebelum pipeline CLI stabil.

Urutan wajib:

```text
1 PDF → 2 Vision → 3 Extract → 4 LaTeX → 5 SymPy
  → 6 LLM Validator → 7 Grading → 8 Report → 9 CLI polish
```

Setiap phase: implementasi → tulis test → jalankan test → pertahankan perilaku phase sebelumnya.

## Phase 1 — PDF

- Load PDF, render PNG per halaman, metadata ukuran, nama file deterministik.
- Acceptance: `answer.pdf` → `page_001.png`, `page_002.png`, …

## Phase 2 — Ollama Vision

- Client Ollama, input gambar, JSON terstruktur, retry, timeout, logging.
- Acceptance: page image → recognition JSON valid (schema).

## Phase 3 — Question Extraction

- Deteksi soal (termasuk multi-page), langkah, final answer.
- Acceptance: page images → objek `Question`.

## Phase 4 — LaTeX

- Builder LaTeX per soal; simpan `raw_text` dan `student.tex`.
- Acceptance: `Question` → `student.tex`.

## Phase 5 — SymPy

- Parser ekspresi/persamaan, equivalence, step validator.
- Acceptance: transformasi algebra yang dikenal menghasilkan status validasi yang diharapkan.

## Phase 6 — LLM Validator

- Prompt validation, response terstruktur, status `uncertain`, confidence.
- Acceptance: ketidakpastian **tidak** dipaksa jadi valid/invalid diam-diam.

## Phase 7 — Grading

- Rubric, skor per langkah, partial credit, feedback.
- Acceptance: dataset uji menghasilkan rentang skor yang diharapkan.

## Phase 8 — Report

- JSON, CSV, HTML (opsional PDF) + metadata reproducibility.

## Phase 9 — CLI polish

- Subcommand lengkap, progress/summary terminal, exit code jelas.
- Pastikan View/Controller/Service terpisah (MVC).
- Bukan web UI.

## Scope MVP matematika

Fokus awal: **topik 1.5 — pertidaksamaan** (bentuk umum + himpunan penyelesaian).

Perluas mengikuti urutan [`topik.md`](topik.md) (2 → 11) hanya setelah pipeline stabil. Detail status: [math-topics.md](math-topics.md).

## Definition of Done (ringkas)

- [ ] CLI end-to-end untuk alur MVP
- [ ] Struktur MVC + interfaces SOLID
- [ ] Recognition tanpa mengoreksi jawaban mahasiswa
- [ ] SymPy prioritas, LLM fallback
- [ ] Partial credit + artefak audit
- [ ] `REVIEW_REQUIRED` / low confidence
- [ ] Test suite dasar hijau

Detail lengkap: [plan_ai_math_grader_ollama.md](plan_ai_math_grader_ollama.md) §21–§33.
