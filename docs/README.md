# Dokumentasi Math Grader

Indeks dokumentasi aplikasi web lokal untuk menilai lembar jawaban matematika tulisan tangan. Pemakaian (alur halaman, artefak, smoke): [README root](../README.md).

```text
PDF → PNG → ink bbox → editor crop (regions.json) → crop → question_crops → Vision JSON
  → questions → LaTeX artefak → SymPy (± LLM) → grade vs exam_schema → report
```

## Sumber kebenaran

Satu topik, satu dokumen. Dokumen lain cukup menautkan.

| Dokumen | Isi |
|---------|-----|
| [../README.md](../README.md) | Pemakaian: alur halaman web, artefak, pengosongan output, smoke |
| [architecture.md](architecture.md) | Pipeline, lapisan MVC, peta folder, topic pack, kontrak web + API |
| [conventions.md](conventions.md) | Aturan coding dan domain: SOLID, OOP+FP, error, recognition fidelity, grading, audit |
| [development-phases.md](development-phases.md) | Status phase 1–9 + acceptance criteria |
| [math-topics.md](math-topics.md) | Silabus bab 1–11, status per bab, topic pack, capability |
| [testing.md](testing.md) | Konvensi pytest: tanpa file baru, OOP `Test*`, `tests/support/`, peta kelas |
| [evaluasi-kode.md](evaluasi-kode.md) | Laporan audit menyeluruh, evaluasi arsitektur, dan perbaikan tipe/linter |

## Panduan agent

- Rules: `.cursor/rules/`
- Skills: `.cursor/skills/extend-math-grader`, `.cursor/skills/review-math-grader-compliance`, `.cursor/skills/write-math-grader-tests`
