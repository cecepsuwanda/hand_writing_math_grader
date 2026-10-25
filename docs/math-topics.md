# Domain Matematika (Silabus)

Katalog resmi domain + status implementasi. Kembangkan mengikuti urutan bab; **satu bab / pack per PR**, dan jangan loncat bab sebelum acceptance test bab sebelumnya hijau.

## Silabus

```text
1. Sistem Bilangan Real dan Pertidaksamaan
   1.1 Sistem Bilangan
   1.2 Garis Bilangan
   1.3 Selang/Interval
   1.4 Sifat Bilangan Real
   1.5 Pertidaksamaan (Bentuk Umum dan Cara menentukan himpunan penyelesaian)

2. Pertidaksamaan Nilai Mutlak
   2.1 Nilai Mutlak
   2.2 Pertidaksamaan Nilai Mutlak

3. Fungsi
   3.1 Definisi Fungsi dan Notasi
   3.2 Domain dan Range
   3.3 Grafik Fungsi
   3.4 Jenis-Jenis Fungsi
   3.5 Operasi Fungsi

4. Limit
   4.1 Limit Fungsi di Satu Titik
   4.2 Limit Kiri dan Limit Kanan
   4.3 Sifat Limit Fungsi
   4.4 Limit Fungsi Trigonometri
   4.5 Limit Tak Hingga

5. Kekontinuan
   5.1 Kekontinuan Fungsi
   5.2 Kontinu Kiri dan Kontinu Kanan

6. Turunan Fungsi
   6.1 Definisi Turunan
   6.2 Turunan Sepihak
   6.3 Aturan Pencarian Turunan
   6.4 Turunan Fungsi Trigonometri
   6.5 Aturan Rantai
   6.6 Turunan Tingkat Tinggi
   6.7 Persamaan Garis Singgung

7. Integral
   7.1 Anti Turunan (Integral)
   7.2 Sifat-sifat integral tak tentu
   7.3 Teorema Dasar Kalkulus
   7.4 Sifat-sifat integral tentu
   7.5 Integral Substitusi

8. Fungsi Transenden
   8.1 Fungsi Logaritma Asli
   8.2 Sifat-sifat fungsi Logaritma Asli
   8.3 Turunan dan Integral Fungsi Logaritma Asli
   8.4 Fungsi Eksponensial Asli
   8.5 Turunan dan Integral Fungsi Eksponensial

9. Matriks dan Operasinya
   9.1 Definisi Matriks
   9.2 Ukuran Matriks
   9.3 Jenis-jenis Matriks
   9.4 Transpos Matriks
   9.5 Sifat Transpos Matriks
   9.6 Trace Matriks
   9.7 Operasi Pada Matriks

10. Invers dan Determinan
    10.1 Determinan Matriks 2x2
    10.2 Determinan Matriks 3x3
    10.3 Invers Matriks

11. Vektor di Bidang dan Ruang
    11.1 Pengertian dan Notasi
    11.2 Operasi pada vektor
    11.3 Norm
    11.4 Jarak Antara 2 Buah Titik
    11.5 Vektor Satuan
    11.6 Hasil Kali Titik (Dot Product)
    11.7 Sudut antara dua buah vektor
    11.8 Triple Skalar
```

## Topic packs

Pack = implementasi `TopicPack` di `app/topics/<id>/` + entri di `_PACKS` (`app/topics/registry.py`).

| Pack id | Bab | Folder standar | Status |
|---------|-----|----------------|--------|
| `1.5` | 1.5 Pertidaksamaan | `standards/topik_1` | **MVP, default** — ingest, roles, `step_checks`, rubric, grading, tes |
| `2` | 2 Pertidaksamaan nilai mutlak | `standards/topik_2` | **Registered** — delegasi roles/`step_checks`/rubric/role instructions ke `1.5`; tes masih minimal |
| `4` | 4 Limit | `standards/topik_4` | **Registered** — roles `algebra` / `indeterminate` / `one_sided` / `figure` / `hp`; final dari `% final:` (cadangan: nilai kalimat `Jadi`); acceptance ingest `tugas_topik_4.tex` (19 sub-soal) |
| `3` | 3 Fungsi | `standards/topik_3` | **Registered** (`Function3Pack`, isolasi) — lembar rubrik: 7 butir × 100, nilai tugas = rata-rata; Langkah 60/50, Jawaban 40/30 (0 atau penuh), Penyajian 20 hanya butir 2–3; lantai langkah 25; butir 4–6 = gabungan (a)+(b); ingest kaya (`VALUE_TABLE`, final `ada`/`tidak ada`); sub-soal **1a/1b, 4a/4b, 5a/5b, 6a/6b** + grafik 2–3; acceptance `tugas_topik_3.tex` (10 (sub-)soal) |
| `5` | 5 Kekontinuan | `standards/topik_5` | **Registered** (`ChapterPack`) — `one_sided` / `function_value` / `continuity` + `figure`; acceptance `tugas_topik_5.tex` (7) |
| `6` | 6 Turunan | `standards/topik_6` | **Registered** (`ChapterPack`) — `definition` / `one_sided_derivative` / `tangent_line` + `figure`; acceptance `tugas_topik_6.tex` (12) |
| `7` | 7 Integral | `standards/topik_7` | **Registered** (`ChapterPack`) — `antiderivative` / `integral_property` / `ftc` / `substitution` / `evaluate_bounds`; acceptance `tugas_topik_7.tex` (15) |
| `8` | 8 Fungsi Transenden | `standards/topik_8` | **Registered** (`ChapterPack`) — `domain` / `log_rule` / `chain_rule` / `substitution`; acceptance `tugas_topik_8.tex` (12) |
| `9` | 9 Matriks | `standards/topik_9` | **Registered** (`ChapterPack`) — `size_check` / `transpose` / `trace` / `matrix_equation`; acceptance `tugas_topik_9.tex` (10) |
| `10` | 10 Determinan dan Invers | `standards/topik_10` | **Registered** (`ChapterPack`) — `determinant` / `cofactor` / `inverse` / `singular_condition`; acceptance `tugas_topik_10.tex` (6) |
| `11` | 11 Vektor | `standards/topik_11` | **Registered** (`ChapterPack`) — `components` / `norm` / `dot` / `cross`; capability tambahan `vector_tuple`; acceptance `tugas_topik_11.tex` (9) |

`ChapterPack` (`app/topics/chapter_pack.py`) menurunkan roles, `step_checks`, rubric dan role instructions dari deklarasi `MilestonePart` (judul seksi kunci, cue teks langkah, poin). Rubric: milestone memakai poinnya, `figure` 2, `final_answer` 3, `algebra` sisanya dari 10 (tes konsistensi memastikan `algebra` > 0 untuk setiap pack). Urutan dropdown = urutan silabus (`1.5, 2, 3, …, 11`).

Pemilihan pack: dropdown **Topik** di halaman awal web UI (berlaku untuk ingest kunci dan semua job), `grading.topic_id` di `config.yaml`, atau `topic_id` di `exam_schema.json` selama user belum memilih topik.

**Folder per bab.** Naming `topik_<bab>` (bab = bagian id sebelum titik) dipakai untuk: standards (`<grading.standards_root>/topik_<bab>`), PDF jawaban (`<input.jawaban_dir>/topik_<bab>`), dan run output (`<output.root_dir>/topik_<bab>/<nama_pdf>`). Maksimal **satu pack per bab**: registry menolak dua pack yang memetakan ke folder yang sama (misalnya `1.3` dan `1.5` sama-sama `topik_1`).

## Capabilities

Capability = rewrite notasi (LaTeX / ASCII → token SymPy) yang dipakai recognizer + validator. Terdaftar di `app/capabilities/registry.py`; pack memilih lewat `capability_ids` (pack `1.5` dan `2` mengaktifkan semuanya; pack bab ≥ 3 memakai `ALL_CAPABILITY_IDS`, tanpa `indexed_roots`; pack `3` menambah `piecewise`; pack `11` menambah `vector_tuple`). Ingest kunci menormalisasi di bawah pack aktif (`using_pack`), jadi capability opt-in ikut berlaku untuk `final_symbolic` / `steps_symbolic`. Pack dengan `show_milestone_pattern` (`1.5`, `2`, `3`): halaman Review/Hasil menampilkan **Pola kunci** (judul `Langkah N` → role); skor tetap coverage per role, bukan matching urutan langkah siswa. Re-ingest `tugas_topik_1.tex` / `tugas_topik_2.tex` / `tugas_topik_3.tex` agar `ExamMilestone.title` terisi di schema.

| Capability id | Bab terkait |
|---------------|-------------|
| `abs` | 2 |
| `indexed_roots` (akar bernama, `x_1` / `x_{1}` / `x₁` → `x`) | 1.5, 2 |
| `interval` (selang, `\cup` / `∪` / ASCII `U`) | 1.3, 3.2 |
| `piecewise` (`\begin{cases}` / `{a if c,…}` → `Piecewise(...)`) | 3 |
| `limit` | 4, 5 |
| `derivative` | 6 |
| `integral` | 7 |
| `transcendental` | 8 |
| `matrix` | 9 |
| `det_inverse` | 10 |
| `vector` | 11 |
| `vector_tuple` (opt-in: `(a, b, c)` → `MATRIX` kolom; di pack lain `(a, b)` = selang) | 11 |

## Status per bab

| Bab | Topik | Status | Validasi (hint) |
|-----|--------|--------|-----------------|
| 1.1–1.4 | Sistem bilangan, garis bilangan, selang, sifat | Pendukung MVP | Konseptual; cek notasi selang + LLM |
| 1.5 | Pertidaksamaan (bentuk umum + HP) | **MVP** | SymPy-first (solve/reduce inequality), garis bilangan = set-equivalence |
| 2 | Pertidaksamaan nilai mutlak | **Pack terdaftar** | SymPy-first Abs + compound/`Or`; kasus naratif → UNCERTAIN → LLM |
| 3 | Fungsi | **Pack terdaftar** (lembar rubrik 100, rata-rata 7 butir) | Domain/range/tabel/komposisi/`% final:` masuk pool Langkah. Jawaban dan penyajian 0 atau penuh. Narasi role `concept` ikut langkah, bukan kolom poin sendiri. Recognition `cases`→`Piecewise` + `GRAPH_POINTS` |
| 4 | Limit | **Pack terdaftar** (ingest + rubric + roles; acceptance ingest hijau) | SymPy `limit` dua sisi / sepihak per token `LIMIT(...)`; rantai `lim … = a = b` dan trig tak terputuskan → UNCERTAIN → LLM |
| 5 | Kekontinuan | **Pack terdaftar** (acceptance ingest hijau) | lim dua sisi = f(a); ε-δ / prosa → UNCERTAIN → LLM |
| 6 | Turunan | **Pack terdaftar** (acceptance ingest hijau) | `f'(x) = …` / `f''(x)` / `f'_-(a)` dibaca sebagai nilai; rantai berisi `LIMIT`/`DIFF`/`INT` → UNCERTAIN → LLM |
| 7 | Integral | **Pack terdaftar** (acceptance ingest hijau) | `\int … dx` → token INT; `[F]_a^b` / `\Bigl[F\Bigr]_a^b` dievaluasi; `\sqrt`/`\sqrt[n]` dipertahankan; `\int … = …` dalam rantai → UNCERTAIN → LLM |
| 8 | Fungsi transenden | **Pack terdaftar** (acceptance ingest hijau) | `\ln\|u\|` → `ln Abs(u)`; `\sec`/`\csc`/`\cot`, `\cos^2 x`; ekor `\approx …` dibuang; sifat naratif → UNCERTAIN → LLM |
| 9 | Matriks | **Pack terdaftar** (acceptance ingest hijau) | SymPy `Matrix` via token MATRIX/TRANSPOSE/TRACE; ruas kiri bernama (`A + B =`, `A^{-1} =`) dibuang; relasi matriks `… = …` → UNCERTAIN → LLM |
| 10 | Determinan dan invers | **Pack terdaftar** (acceptance ingest hijau) | `Matrix.det` / `.inv` / `.adjugate` via DET/INV/ADJ; `\det(A) = <kerja skalar>` dicek sebagai rantai skalar |
| 11 | Vektor | **Pack terdaftar** (acceptance ingest hijau) | Tuple → MATRIX kolom (`vector_tuple`), NORM/DOT/CROSS (bernama + literal); sudut/prosa → UNCERTAIN → LLM |

## Aturan scope

- Satu domain aktif pada satu waktu untuk fitur grading baru.
- Testdata dan rubric standar harus mencerminkan bab yang sedang di-support.
- Klaim "support bab X" hanya setelah bab itu punya pack + acceptance test hijau.
- Semua bab silabus (1.5, 2, 3–11) sudah punya pack + acceptance ingest. Langkah berikutnya: acceptance grading end-to-end per bab dengan jawaban mahasiswa sungguhan, dan evaluasi relasi matriks (`DET(M) = -2`) di parser agar bab 9–11 tidak bergantung pada LLM.
