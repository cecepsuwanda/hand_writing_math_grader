# Ringkasan Phase 1–9

Urutan wajib. Satu phase per sesi. Setiap implementasi harus patuh **MVC**, **SOLID**, **clean code**, serta **OOP + FP** (`docs/architecture.md`, `docs/conventions.md`). Scope **matematika** (bab silabus) merujuk `docs/math-topics.md` / `docs/topik.md` — terpisah dari phase teknis di bawah.

## Phase 1 — PDF

- Modul: `services/pdf/renderer.py`, interface `PdfRenderer`
- CLI: `python -m app.cli render data/input/jawaban/...pdf`
- Acceptance: PDF → `page_001.png`, …
- Test: 1 halaman, multi halaman, PDF kosong, file invalid

## Phase 2 — Ollama Vision

- Modul: `services/vision/ollama_client.py`, `recognizer.py`, `ink_region_proposer.py`, `factory.py`; `controllers/crop_controller.py`
- Interface: `VisionRecognizer`
- Prompt: `prompts/crop_math.txt` (ink bbox → crop)
- Artefak: `page_NNN_regions.json` (editable) + `region_XX_solution.png`
- CLI: `propose-crops`, `recrop`; confirm loop before recognize (`--yes` skips)
- Acceptance: image → regions JSON + crops → recognition JSON (Pydantic)
- Fitur: retry, timeout, logging; `recognition.ink.*` dari config

## Phase 3 — Question Extraction

- Modul: `services/questions/extractor.py` (+ `functions/question_merge.py`)
- Acceptance: pages → `Question` (multi-page, steps, final answer)

## Phase 4 — LaTeX

- Modul: `services/latex/builder.py`, `functions/latex_transforms.py`
- Acceptance: Question → `student.tex`; tetap simpan `raw_text`

## Phase 5 — SymPy

- Modul: `services/math/parser.py`, `sympy_validator.py`, `equivalence.py`
- Acceptance: transformasi dikenal → status validasi benar
- Scope validator: konsistensi langkah mahasiswa; compare ke kunci di Phase 7 grading

## Phase 6 — LLM Validator

- Prompt: `prompts/validation.txt`
- Acceptance: boleh `uncertain`; jangan paksa valid/invalid tanpa evidence

## Phase 7 — Grading

- Modul: `services/grading/step_grader.py`, `rubric.py`
- Prompt: `prompts/grading.txt`
- Acceptance: partial credit; rentang skor sesuai testdata
- Follow-up: bandingkan ke standard solution / kunci (`data/input/kunci_jawaban`, `standards/.../solutions`)
  → **Done (slice):** final = min(konsistensi, standard SymPy); soft-align steps = audit; skor langkah = konsistensi; `ingest-kunci` CLI for enumerate+align+HP TeX

## Phase 8 — Report

- JSON / CSV / HTML + metadata reproducibility (model, prompt version, timestamp)

## Phase 9 — CLI polish

- Semua subcommand, progress/summary View, exit codes
- `process` tanpa argumen: menu pilih PDF dari `data/input/jawaban/`
- Awal `process`: kosongkan `data/output/` kecuali `standards/`
- Bukan web UI

## Anti-patterns

- Menggabungkan recognition + grading dalam satu prompt gambar
- Controller berisi HTTP Ollama
- Menghapus recognition.json setelah grading **di tengah run yang sama**
- Menghapus `data/output/standards/` saat reset workspace
- Hard-code `llama3.2-vision` di source
