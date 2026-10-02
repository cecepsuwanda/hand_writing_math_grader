---
name: review-math-grader-compliance
description: >-
  Reviews Math Grader code or diffs for MVC, SOLID/DI, clean code, OOP+FP,
  topic-pack boundaries, recognition fidelity, SymPy-before-LLM validation,
  per-run artifacts, and CLI-first product rules. Use when reviewing PRs,
  checking architecture compliance, auditing an extension, or when the user
  asks for a compliance or architecture review.
---

# Review Math Grader Compliance

## Cara kerja

1. Tentukan scope: uncommitted changes, branch diff, atau file yang disebut user.
2. Baca diff/file terkait.
3. Nilai terhadap checklist di bawah.
4. Laporkan temuan: **Wajib diperbaiki** / **Saran** / **OK**.
5. Jangan rewrite besar kecuali user minta — fokus temuan kepatuhan.

## Checklist

### MVC, SOLID, clean code, OOP+FP

- [ ] View tidak memanggil Ollama/SymPy/persist artefak
- [ ] View tidak import `app.controllers` / `app.services`; error/peringatan ke stderr (`print_error` / `print_warning` di `error_view`)
- [ ] Tidak ada `input()` di controller, `cli.py`, atau `app/commands/`; input interaktif hanya lewat `views/prompt_view.py`
- [ ] Controller tipis (orkestrasi + view; tidak berisi prompt/rumus grading)
- [ ] Controller tidak import konstanta/implementasi dari `app/services` (di-inject `pipeline_factory`); tidak glob/parse artefak sendiri (pakai `functions/*_artifact.py`)
- [ ] Semua `*Result` = model Pydantic di `app/models/` (tanpa dataclass hasil di controller); default bersama dari `models/defaults.py`
- [ ] `cli.py` tipis (`build_parser` + `main` atas `COMMANDS`); subcommand = class `Command` di `app/commands/`, alur bersama di `flows.py`, adapter `CliMenuActions`; state menu di `MenuController` / `MenuSession`
- [ ] Service bergantung interface / DI lewat `pipeline_factory`, bukan konkret library tersebar
- [ ] `functions/` deterministik; I/O hanya di modul artefak yang diizinkan (`*_artifact.py`, `question_crops.py`, `image_crop.py`, `report_details.py`, `workspace_reset.py`, `load_exam_schema`); tanpa network/model
- [ ] Service/client ber-state memakai OOP di `services/`; tidak ada static util class
- [ ] Error domain = subclass `MathGraderError`; tidak menelan exception
- [ ] Clean code: nama bermakna, fungsi fokus, type hints
- [ ] Tidak ada god-interface / god-class

### Topic pack

- [ ] Logika khusus bab ada di `app/topics/<id>/` / capability, bukan di controller atau service inti
- [ ] Pack baru terdaftar di `_PACKS`; capability baru di `app/capabilities/registry.py` + `rewrite_*` pure
- [ ] Tidak mengklaim support bab yang belum punya pack + tes (`docs/math-topics.md`)

### Recognition & grading

- [ ] Recognition tidak mengoreksi atau mengarang langkah mahasiswa
- [ ] Konteks vision hanya stem + `expects_figure` (tanpa steps/HP)
- [ ] `question_crops/` divalidasi: file tidak valid → `QuestionCropsInvalidError`; folder hilang → peringatan
- [ ] `raw_text` / gambar asli dipertahankan
- [ ] SymPy dicoba sebelum LLM; output LLM divalidasi schema; `uncertain` diizinkan
- [ ] Skor langkah = konsistensi; `final_answer` = min(konsistensi, standar); partial credit; audit fields ada

### Produk & artefak

- [ ] Entry tetap CLI; API hanya adapter opsional
- [ ] Nama model dari config/env, bukan hard-coded
- [ ] Pengosongan output hanya `data/output/<nama_pdf>/` (per-run); `standards/` dan run lain aman
- [ ] Artefak intermediate tidak dihapus bila tahap berikut gagal
- [ ] Dokumen kanonik diperbarui bila kontrak/CLI/pack berubah

### Testing

- [ ] Sesuai rule `.cursor/rules/testing.mdc` (tanpa file `test_*.py` baru, OOP `class Test*`, setup dari `tests/support/`, tanpa Ollama live)
- [ ] Perubahan perilaku disertai tes baru/diperbarui

## Format laporan

```markdown
## Compliance review

**Scope:** …
**Area terkait:** …

### Wajib diperbaiki
- …

### Saran
- …

### OK
- …
```

## Referensi

- `docs/architecture.md`, `docs/conventions.md`, `docs/math-topics.md`, `docs/testing.md`
- `.cursor/rules/mvc-architecture.mdc`, `math-grader-core.mdc`, `recognition-and-grading.mdc`, `testing.mdc`
- Skills: `.cursor/skills/extend-math-grader`, `.cursor/skills/write-math-grader-tests`
