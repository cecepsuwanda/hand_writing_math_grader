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
- Acceptance: PDF di `data/input/jawaban/` → `data/output/pages/page_001.png`, …

## Phase 2 — Ollama Vision (ink crop + confirm)

- Client Ollama, ink-cluster bboxes → write `page_NNN_regions.json` → Pillow crop → **human confirm** (edit JSON + `recrop`) → `crop_math` symbolic JSON.
- Prompt: `crop_math.txt`.
- CLI: `propose-crops`, `recrop`; `recognize` / `process` confirm unless `--yes`.
- Recognition context dari `exam_schema`: **stem + expects_figure saja** (bukan steps/HP).
- Acceptance: page image → editable regions JSON + crop PNGs → recognition JSON valid.
- Config: `recognition.ink.*` (threshold, merge gaps, margins). Single regions artifact (no `*_regions_ink.json`).

## Phase 3 — Question Extraction

- Deteksi soal (termasuk multi-page), langkah, final answer.
- Acceptance: page images → objek `Question`.

## Phase 4 — LaTeX

- Builder LaTeX per soal; simpan `raw_text` dan `student.tex`.
- Acceptance: `Question` → `student.tex`.

## Phase 5 — SymPy

- Parser ekspresi/persamaan, equivalence, step validator.
- Acceptance: transformasi algebra yang dikenal menghasilkan status validasi yang diharapkan.
- Scope: konsistensi langkah mahasiswa. Compare ke kunci dilakukan di **Phase 7 grading** (bukan di validator).

## Phase 6 — LLM Validator

- Prompt validation, response terstruktur, status `uncertain`, confidence.
- Acceptance: ketidakpastian **tidak** dipaksa jadi valid/invalid diam-diam.

## Phase 7 — Grading

- Rubric, skor per langkah, partial credit, feedback.
- Acceptance: dataset uji menghasilkan rentang skor yang diharapkan.
- Compare final answer ke `standards/.../solutions/` (SymPy); skor `final_answer` = min(konsistensi, standard).
- Step-align **best-method** soft-align (shared+method bank; relational *form*) — **audit/feedback saja**; skor langkah algebra = konsistensi mahasiswa (jalur alternatif valid tidak dipotong).
- Skor parts: `critical_points` (set-equivalence milestone), `figure` (number_line set-equivalence; presence fallback), `final_answer` = min(konsistensi, standard).
- Ingest kunci: `python -m app.cli ingest-kunci` menulis `standards/.../solutions`, `exam_schema.json`, dan `rubrics/` dari `data/input/kunci_jawaban/` (Metode N → `methods[]`; shared `steps`; parts algebra/critical_points/sign_chart/figure/hp; `number_line` dari HP bila `expects_figure`). Recognition memuat schema bila ada (stem + `expects_figure` saja).
- Recognition (`crop-math-v9`): field `role` per langkah; figure `symbolic.repr` = `NUMBER_LINE(...)`; grading figure/milestone/HP memakai role (+ fallback legacy).
- Follow-up selesai untuk multi-metode MVP (Phase 1–3).

## Phase 8 — Report

- JSON, CSV, HTML + metadata reproducibility (PDF report bukan bagian MVP).

## Phase 9 — CLI polish

- Subcommand lengkap, progress/summary terminal, exit code jelas.
- `process` mendukung pilihan PDF interaktif dari `data/input/jawaban/`.
- `menu` (default `run.bat`): ingest kunci / crop ink / recrop / lanjut grading / keluar.
- Awal `process` mengosongkan `data/output/` kecuali `standards/`.
- Pastikan View/Controller/Service terpisah (MVC).
- Bukan web UI.
- Opsional pasca-MVP: `python -m app.api` (FastAPI tipis `/health`, `/api/process`, `/api/results/{id}`) — adapter di atas controller yang sama.

## Scope MVP matematika

Fokus awal: **topik 1.5 — pertidaksamaan** (bentuk umum + himpunan penyelesaian).

Perluas mengikuti urutan [`topik.md`](topik.md) (2 → 11) hanya setelah pipeline stabil. Detail status: [math-topics.md](math-topics.md).

## Definition of Done (ringkas)

- [x] CLI end-to-end untuk alur MVP
- [x] Struktur MVC + interfaces SOLID
- [x] Recognition tanpa mengoreksi jawaban mahasiswa
- [x] SymPy prioritas, LLM fallback
- [x] Partial credit + artefak audit
- [x] `REVIEW_REQUIRED` / low confidence
- [x] Test suite dasar hijau

Detail lengkap: [plan_ai_math_grader_ollama.md](plan_ai_math_grader_ollama.md) §21–§33.

## Smoke live (opsional, butuh Ollama)

Bukan bagian `pytest` default. Pastikan Ollama jalan dan model di `app/config/config.yaml` terisi, lalu:

```bash
python -m app.cli process smoke_inequality.pdf
```

atau `scripts/smoke_live.bat`. Sample: `data/input/jawaban/smoke_inequality.pdf`.
