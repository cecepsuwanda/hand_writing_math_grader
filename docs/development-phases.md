# Tahapan Pengembangan

Phase 1–9 **selesai**. Dokumen ini mencatat scope + acceptance tiap phase sebagai acuan regresi. Pekerjaan baru = perluasan (topic pack, tahap, subcommand) — lihat skill `extend-math-grader` dan [`math-topics.md`](math-topics.md).

```text
1 PDF → 2 Vision → 3 Extract → 4 LaTeX → 5 SymPy
  → 6 LLM Validator → 7 Grading → 8 Report → 9 CLI polish
```

Setiap perubahan: implementasi → tulis/perluas tes → jalankan `pytest -q` → pertahankan perilaku phase sebelumnya.

| Phase | Status |
|-------|--------|
| 1 PDF | Selesai |
| 2 Vision (ink crop + confirm + question_crops) | Selesai |
| 3 Extract | Selesai |
| 4 LaTeX | Selesai |
| 5 SymPy | Selesai |
| 6 LLM Validator | Selesai |
| 7 Grading | Selesai |
| 8 Report (JSON/CSV/HTML/TeX) | Selesai |
| 9 CLI polish | Selesai |

## Phase 1 — PDF

- Load PDF, render PNG per halaman, metadata ukuran, nama file deterministik.
- Acceptance: PDF di `data/input/jawaban/` → `data/output/<nama_pdf>/pages/page_001.png`, …

## Phase 2 — Ollama Vision (ink crop + confirm)

- Client Ollama, ink-cluster bboxes → `page_NNN_regions.json` → crop Pillow → **konfirmasi user** (edit JSON + `recrop`) → `crop_math` symbolic JSON.
- Prompt: `crop_math.txt`; konteks dari `exam_schema` hanya **stem + `expects_figure`**.
- CLI: `propose-crops`, `recrop`; `recognize` / `process` meminta konfirmasi kecuali `--yes`.
- Config: `recognition.ink.*` (threshold, merge gaps, margins). Satu artefak regions (tanpa `*_regions_ink.json`).
- Nomor soal per crop: `label-questions` / `relabel-questions` (prompt `crop_label.txt`) → `crops/question_crops/question_NNN.json`. Alur dan aturan: [README root](../README.md#nomor-soal-question_crops), [`architecture.md`](architecture.md#pipeline).
- Acceptance: page image → regions JSON editable + crop PNG → recognition JSON valid.

## Phase 3 — Question Extraction

- Deteksi soal (termasuk multi-page), langkah, final answer.
- Nomor soal mengikuti `question_crops/` bila ada, sehingga soal yang tersebar di beberapa crop/halaman digabung ke `question_NNN` yang sama.
- Acceptance: recognition JSON → objek `Question` (`question.json`).

## Phase 4 — LaTeX

- Builder LaTeX per soal; simpan `raw_text` dan `student.tex`.
- Acceptance: `Question` → `student.tex`.

## Phase 5 — SymPy

- Parser ekspresi/persamaan, equivalence, step validator.
- Scope: konsistensi langkah mahasiswa. Compare ke kunci dilakukan di Phase 7 (bukan di validator).
- Acceptance: transformasi aljabar yang dikenal menghasilkan status validasi yang diharapkan.

## Phase 6 — LLM Validator

- Prompt `validation.txt`, response terstruktur, status `uncertain`, confidence. Hanya dipanggil untuk langkah yang SymPy tandai `uncertain`.
- Acceptance: ketidakpastian **tidak** dipaksa jadi valid/invalid diam-diam.

## Phase 7 — Grading

- Rubric, skor per langkah, partial credit, feedback (`grading.txt`, annotator LLM opsional).
- Ingest kunci (`ingest-kunci`) → `exam_schema.json`, `solutions/`, `rubrics/`.
- Aturan skor (konsistensi, soft-align audit, `final_answer` = min(konsistensi, standar) kecuali HP yang cocok kunci, bucket `critical_points` / `sign_chart` / `figure`): [`conventions.md`](conventions.md#validasi-dan-grading) dan [`conventions.md`](conventions.md#kunci-jawaban-ingest).
- Acceptance: dataset uji menghasilkan rentang skor yang diharapkan; jalur alternatif valid tidak dipotong.

## Phase 8 — Report

- `report.json` (+ metadata model & versi prompt), `summary.csv`, `report.html`, `report.tex` (satu file per mahasiswa: crop + OCR + komentar; dikompilasi otomatis ke `report.pdf` setelah grading; lihat README).
- Acceptance: artefak report lengkap dan konsisten dengan `grading.json` per soal.

## Phase 9 — CLI polish

- Subcommand lengkap, progress/summary terminal, exit code `0` / `1` / `2`.
- `menu` (default `run.bat`) dengan 8 pilihan; pilihan PDF / run interaktif.
- Output per PDF di `data/output/<nama_pdf>/`; aturan pengosongan dan pemilihan run: [README root](../README.md#artefak).
- Kontrak CLI + API opsional: [`architecture.md`](architecture.md#kontrak-cli).
- Bukan web UI.

## Topic packs (pasca Phase 9)

Pack `1.5` (default/MVP) dan `2` (terdaftar, delegasi ke `1.5`). Bab 3–11 belum punya pack. Status dan urutan: [`math-topics.md`](math-topics.md).

## Definition of Done

- [x] CLI end-to-end untuk alur MVP
- [x] Struktur MVC + interfaces SOLID
- [x] Recognition tanpa mengoreksi jawaban mahasiswa
- [x] SymPy prioritas, LLM fallback
- [x] Partial credit + artefak audit
- [x] `REVIEW_REQUIRED` bila ada langkah/part berstatus `uncertain`
- [x] Test suite hijau (`pytest -q`)

Smoke live (butuh Ollama): [README root](../README.md#smoke-live-butuh-ollama).
