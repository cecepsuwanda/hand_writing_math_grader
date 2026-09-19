---
name: review-math-grader-compliance
description: >-
  Reviews Math Grader code or diffs for MVC boundaries, SOLID/DI, recognition
  fidelity, SymPy-before-LLM validation, audit artifacts, CLI-only MVP, and
  clean coding. Use when reviewing PRs, checking architecture compliance,
  auditing a phase implementation, or when the user asks for a compliance or
  architecture review.
---

# Review Math Grader Compliance

## Cara kerja

1. Tentukan scope: uncommitted changes, branch diff, atau file yang disebut user.
2. Baca diff/file terkait.
3. Nilai terhadap checklist di bawah.
4. Laporkan temuan: **Wajib diperbaiki** / **Saran** / **OK**.
5. Jangan rewrite besar kecuali user minta — fokus temuan kepatuhan.

## Checklist

### MVC & SOLID

- [ ] View tidak memanggil Ollama/SymPy/filesystem business persist
- [ ] Controller tipis (tidak berisi prompt/math grading)
- [ ] Service bergantung interface, bukan konkret library tersebar
- [ ] Pure transforms di `functions/`, bukan static util class kosong
- [ ] Tidak ada god-interface / god-class

### Recognition & grading

- [ ] Recognition tidak mengoreksi atau mengarang langkah mahasiswa
- [ ] `raw_text` / gambar asli dipertahankan
- [ ] SymPy dicoba sebelum LLM untuk klaim simbolik
- [ ] Output LLM divalidasi schema; `uncertain` diizinkan
- [ ] Grading berbasis rubric + partial credit; audit fields ada

### Produk & proses

- [ ] Entry tetap CLI; tidak ada FastAPI/Streamlit sebagai pengganti MVP
- [ ] Domain sesuai roadmap `docs/topik.md` / `docs/math-topics.md`; tidak mengklaim support bab di luar scope saat ini
- [ ] Nama model dari config, bukan hard-coded
- [ ] Artefak intermediate tidak dihapus
- [ ] Ada/ diperbarui tests untuk perubahan phase
- [ ] Type hints + penanganan error eksplisit

## Format laporan

```markdown
## Compliance review

**Scope:** …
**Phase terkait:** …

### Wajib diperbaiki
- …

### Saran
- …

### OK
- …
```

## Referensi

- `docs/architecture.md`, `docs/conventions.md`, `docs/math-topics.md`
- `docs/topik.md`
- `.cursor/rules/mvc-architecture.mdc`, `recognition-and-grading.mdc`
- `docs/plan_ai_math_grader_ollama.md` §2, §23, §31, §32, §33
