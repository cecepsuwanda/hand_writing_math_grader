# Konvensi Pengembangan

## Domain matematika

Katalog resmi: [`topik.md`](topik.md). Status dan urutan implementasi: [math-topics.md](math-topics.md).

- MVP aktif: **topik 1.5 Pertidaksamaan**.
- Jangan perluas grading ke bab lain sebelum domain/pipeline saat ini hijau.
- Jangan mengklaim support bab di luar scope yang sudah diuji.

## SOLID

- **S**: satu alasan berubah per kelas/modul.
- **O**: perluasan lewat interface baru, bukan edit besar inti.
- **L**: implementasi `VisionRecognizer` / `StepValidator` dapat diganti tanpa merusak pemanggil.
- **I**: interface sempit (`PdfRenderer`, `VisionRecognizer`, `StepValidator`, `GradeReporter`).
- **D**: Controller/service bergantung abstraksi; Ollama/PyMuPDF/SymPy diinjeksi.

## Clean coding

- Nama bermakna; fungsi kecil; tidak ada side effect tersembunyi.
- Konfigurasi terpusat (`app/config/config.yaml` + env); hindari magic string tersebar.
- Type hints; kontrak data antar layer dengan Pydantic.
- Error handling eksplisit; jangan menelan exception.
- Komentar hanya untuk “mengapa”.

## OOP dan Functional Programming

| Gunakan OOP | Gunakan pure function |
|-------------|------------------------|
| Client/service ber-state (`OllamaClient`, `PdfRenderer`) | Equivalence check, agregasi skor, mapping step→LaTeX |
| Polymorphism lewat ABC/Protocol | Filter/map tahap pipeline tanpa mutasi input |
| Domain model (Pydantic) | Helper di `app/functions/` |

- Prefer data recognition/validation/grading immutable-ish.
- Composition over inheritance.
- Jangan buat class utilitas berisi static method saja — pakai fungsi modul.

## Recognition fidelity

Saat recognition, LLM **tidak boleh**:

- memperbaiki persamaan / typo;
- menyimpulkan langkah yang tidak tertulis;
- mengganti jawaban dengan yang “benar”.

Jika ragu: flag confidence / `uncertain`, pertahankan gambar asli.

## Validasi dan grading

1. Syntax / parse LaTeX.
2. SymPy jika memungkinkan.
3. LLM hanya jika deterministic checker tidak cukup.
4. Bandingkan makna matematis, bukan string LaTeX mentah.
5. Partial credit; bedakan conceptual / calculation / carry-forward error.
6. Jangan nolkan semua skor hanya karena final answer salah.

Output LLM wajib divalidasi terhadap schema. Status `uncertain` dan `REVIEW_REQUIRED` diizinkan.

## CLI dan antarmuka

- Entry point wajib: `python -m app.cli ...`
- PDF jawaban: `data/input/jawaban/`; kunci: `data/input/kunci_jawaban/`.
- `process` tanpa argumen PDF → menu pilihan interaktif.
- Awal `process` mengosongkan `data/output/` kecuali `standards/`.
- Model vision/reasoning dari config — **jangan hard-code** nama model.
- FastAPI/Streamlit hanya setelah engine CLI stabil; service layer harus reusable.

## Reproducibility & keamanan

Simpan metadata submission: versi app, model, versi prompt, timestamp.

Jangan commit password/API key. Gunakan environment variables bila perlu. Prefer Ollama lokal untuk data mahasiswa.

## Logging

Log: timestamp, submission_id, page, model, prompt_version, processing_time, status tahap, errors.
