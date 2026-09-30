---
name: extend-math-grader
description: >-
  Extends the Math Grader after phases 1–9: adds a topic pack (syllabus bab)
  with capabilities, adds or changes a pipeline stage (controller/service/view
  + pipeline_factory), or adds a CLI subcommand — following MVC, SOLID, clean
  code, OOP+FP and CLI-first conventions. Use when the user asks to add a new
  topic/bab/pack, support a new math notation, add or modify a pipeline step,
  add a CLI command or menu item, or continue development.
---

# Extend Math Grader

Phase 1–9 sudah selesai; pekerjaan baru selalu berupa **perluasan**. Pilih satu alur di bawah, kerjakan satu perubahan per PR.

## Sebelum coding

1. Inspect repo (`app/`, `tests/`) dan baca dokumen kanonik yang relevan:
   - `docs/architecture.md` — pipeline, lapisan, peta folder, kontrak CLI
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
      id, label, topik_refs, part_kinds, roles, figure_kinds, capability_ids,
      recognition_role_instructions, rubric_from_parts, coalesce_step_role
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
- [ ] Controller tipis di app/controllers/ (orkestrasi + panggil view); tidak import dari
      app/services (konstanta/implementasi di-inject), tidak glob/parse artefak sendiri
      (pakai app/functions/*_artifact.py); hasil = model *Result Pydantic di app/models/
- [ ] View di app/views/ (presentasi terminal saja; error/peringatan ke stderr via error_view)
- [ ] Wiring DI di app/services/pipeline_factory.py (dipakai CLI + API)
- [ ] Error domain = subclass MathGraderError (app/exceptions.py)
- [ ] Artefak intermediate ditulis ke folder run (RunLayout); tidak dihapus bila tahap berikut gagal
- [ ] Tes di file inventaris yang sesuai domain (lihat docs/testing.md)
- [ ] Update docs/architecture.md (pipeline / peta folder) bila berubah
```

Aturan: recognition tidak mengoreksi jawaban; SymPy sebelum LLM; output LLM divalidasi schema (rule `recognition-and-grading.mdc`).

## Alur C — Tambah subcommand CLI / item menu

```text
CLI progress:
- [ ] Parser: _add_<nama>_parser(subparsers) di app/cli.py memakai helper argumen
      (_add_pdf_arg, _add_dpi_arg, _add_pages_dir_arg, _add_yes_arg, _add_questions_dir_arg,
      _add_standard_arg, _add_run_arg, _add_topic_arg, …); daftarkan di loop build_parser()
- [ ] Handler _run_<nama>(args): load_config → pipeline_factory.build_* → controller → view → return 0;
      daftarkan di _HANDLERS. main() sudah memetakan error lewat _report_failure
      (MathGraderError → 1, lainnya → 2 + logger.exception)
- [ ] Folder run: _layout_for_pdf (ada PDF) atau _layout_for_run (--run)
- [ ] Pengosongan output hanya untuk folder run milik perintah itu
- [ ] Alur dipakai subcommand DAN menu? Helper _<alur>(config, layout, ...) di cli.py,
      dipanggil dari _run_<nama> dan _CliMenuActions (jangan duplikasi)
- [ ] Item menu (opsional):
      - entri MenuChoice + MAIN_MENU (app/functions/menu_choices.py)
      - method di Protocol MenuActions (app/interfaces/menu_actions.py), implementasi di _CliMenuActions
      - handler di MenuController._handlers (state sesi di MenuSession, bukan di cli.py)
- [ ] Input interaktif hanya lewat app/views/prompt_view.py (tidak ada input() di cli.py/controller)
- [ ] Tes: subcommand di TestCliProcess (CliHarness); menu di TestMenuController (RecordingMenuActions)
- [ ] Update README.md (menu/flag) + docs/architecture.md (kontrak CLI)
```

`cli.py` tetap tipis: parser, `_HANDLERS`, helper alur bersama, dan adapter `_CliMenuActions`. Logika bisnis ada di controller/service.

## Setelah selesai

- Jalankan `pytest -q` (tanpa Ollama live).
- Laporkan alur yang dipakai, file utama, tes yang ditambah, dan dokumen yang diperbarui.

## Referensi

- `docs/architecture.md`, `docs/conventions.md`, `docs/math-topics.md`, `docs/testing.md`
- Rules: `.cursor/rules/math-grader-core.mdc`, `mvc-architecture.mdc`, `recognition-and-grading.mdc`, `testing.mdc`
- Skill tes: `.cursor/skills/write-math-grader-tests`
- Skill review: `.cursor/skills/review-math-grader-compliance`
