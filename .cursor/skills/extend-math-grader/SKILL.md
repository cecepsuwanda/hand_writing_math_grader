---
name: extend-math-grader
description: >-
  Extends the Math Grader after phases 1–9: adds a topic pack (syllabus bab)
  with capabilities, adds or changes a pipeline stage (controller/service
  + pipeline_factory), or adds a web page / endpoint / background job —
  following MVC, SOLID, clean code, OOP+FP and web-UI conventions. Use when
  the user asks to add a new topic/bab/pack, support a new math notation, add
  or modify a pipeline step, add a page or button to the web UI, or continue
  development.
---

# Extend Math Grader

Phase 1–9 sudah selesai; pekerjaan baru selalu berupa **perluasan**. Pilih satu alur di bawah, kerjakan satu perubahan per PR.

## Sebelum coding

1. Inspect repo (`app/`, `tests/`) dan baca dokumen kanonik yang relevan:
   - `docs/architecture.md` — pipeline, lapisan, peta folder, kontrak web (halaman + endpoint)
   - `docs/conventions.md` — aturan coding + domain
   - `docs/math-topics.md` — silabus, status bab, pack, capability
   - `docs/testing.md` — konvensi tes
2. Pertahankan perilaku yang sudah ada; jangan ubah kontrak modul stabil tanpa alasan.
3. Jangan mengarang API library — verifikasi dokumentasi (SymPy, PyMuPDF, Pillow, httpx).
4. Nama model dari config; jangan hard-code.

## Alur A — Tambah topic pack (bab silabus)

Hanya setelah bab sebelumnya punya acceptance test hijau (urutan: `docs/math-topics.md`).

```text
Pack progress:
- [ ] app/topics/<nama_bab>/__init__.py: class pack + PACK = ...
- [ ] Implement semua anggota TopicPack (app/interfaces/topic_pack.py):
      id, label, topik_refs, part_kinds, roles, step_checks, figure_kinds,
      capability_ids, recognition_role_instructions, rubric_from_parts,
      coalesce_step_role
- [ ] step_checks: petakan tiap role ke StepCheck (app/models/validation.py);
      role tanpa entri = TRANSITION. Jenis cek baru = anggota StepCheck + checker
      di SymPyStepValidator._checkers (bukan nama role di service inti)
- [ ] Tambah entri di _PACKS (app/topics/registry.py)
- [ ] Notasi baru? rewrite_* di app/functions/<x>_normalize.py (pure)
      + entri _CAPABILITIES (app/capabilities/registry.py); pilih lewat capability_ids
- [ ] Controller/service inti TIDAK disentuh (tetap pack-agnostic)
- [ ] Tes di tests/test_suite.py: TestTopicRegistry, TestTopicPackBehavior, TestCapabilityDispatch
      (+ class domain baru bila perlu, di file yang sama)
- [ ] Update docs/math-topics.md (tabel pack, status bab)
```

Pack boleh mendelegasikan ke pack lain (contoh: `app/topics/abs_inequality_2/` memakai roles/rubric `1.5`).

## Alur B — Tambah / ubah tahap pipeline

```text
Stage progress:
- [ ] Kontrak data: model Pydantic di app/models/
- [ ] Port: ABC/Protocol sempit di app/interfaces/ (bila ada adapter eksternal)
- [ ] Service (OOP, ber-state) di app/services/<area>/ ATAU fungsi pure di app/functions/
- [ ] Controller tipis di app/controllers/ (orkestrasi; tanpa print/prompt); tidak import dari
      app/services (konstanta/implementasi di-inject), tidak glob/parse artefak sendiri
      (pakai app/functions/*_artifact.py); hasil = model *Result Pydantic di app/models/;
      notifikasi (progres, peringatan) lewat callback opsional
- [ ] Tampilkan hasil di web: method WebPipeline + template (lihat Alur C)
- [ ] Wiring DI di app/services/pipeline_factory.py
- [ ] Error domain = subclass MathGraderError (app/exceptions.py)
- [ ] Artefak intermediate ditulis ke folder run (RunLayout); tidak dihapus bila tahap berikut gagal
- [ ] Tes di file inventaris yang sesuai domain (lihat docs/testing.md)
- [ ] Update docs/architecture.md (pipeline / peta folder) bila berubah
```

Aturan: recognition tidak mengoreksi jawaban; SymPy sebelum LLM; output LLM divalidasi schema (rule `recognition-and-grading.mdc`).

## Alur C — Tambah halaman / endpoint / job web

```text
Web progress:
- [ ] Use-case di WebPipeline (app/web/pipeline.py): ambil config dari WebSession, folder run
      lewat files.require_run, builder lewat modul `pipeline_factory.build_x` (bukan import nama);
      kembalikan model Pydantic (tanpa print/prompt)
- [ ] Lama (Ollama / render / grading)? kirim ke JobManager.submit(run=..., kind=JobKind.X,
      task=lambda reporter: ...) — task mengembalikan URL halaman lanjutan; progres via
      reporter.progress / reporter.message (SSE di /jobs/{id}/events)
- [ ] Schema request/response di app/web/schemas.py (validasi input di sini, bukan di router)
- [ ] Router tipis di app/web/routers/<area>.py; daftarkan di ROUTERS (app/web/routers/__init__.py)
- [ ] Template di app/web/templates/ (extends base.html; partial HTMX di templates/partials/);
      aset JS/CSS pihak ketiga hanya dari app/web/static/vendor/ (tanpa CDN)
- [ ] Path artefak dari URL → app/web/files.py (anti path traversal); jangan bangun Path dari input mentah
- [ ] Error domain = subclass MathGraderError; status HTTP di app/web/errors.py (_STATUS)
- [ ] Pengosongan output hanya untuk folder run milik aksi itu (hanya Propose crops)
- [ ] Tes: WebHarness (TestClient + FakeJobManager) di class Test* file inventaris yang sesuai
- [ ] Update README.md + docs/architecture.md (kontrak web)
```

`app/web/main.py` hanya merakit `FastAPI` (`create_app`), static, template, dan `ROUTERS`. Logika bisnis ada di controller/service; router hanya adapter HTTP.

## Setelah selesai

- Jalankan `pytest -q` (tanpa Ollama live). Perubahan UI: cek manual dengan `python -m app.web`.
- Laporkan alur yang dipakai, file utama, tes yang ditambah, dan dokumen yang diperbarui.

## Referensi

- `docs/architecture.md`, `docs/conventions.md`, `docs/math-topics.md`, `docs/testing.md`
- Rules: `.cursor/rules/math-grader-core.mdc`, `mvc-architecture.mdc`, `recognition-and-grading.mdc`, `testing.mdc`
- Skill tes: `.cursor/skills/write-math-grader-tests`
- Skill review: `.cursor/skills/review-math-grader-compliance`
