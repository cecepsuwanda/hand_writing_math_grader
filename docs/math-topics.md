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
| — | 3–11 | `standards/topik_<bab>` | Belum ada pack. Tambah `app/topics/<id>/` + entri `_PACKS` saat acceptance grading bab itu siap |

Pemilihan pack: menu CLI **Pilih topik** (nomor, id, atau `topik_<bab>`), `grading.topic_id` di `config.yaml`, `--topic` pada `process` / `recognize` / `extract` / `validate` / `grade` / `report` / `label-questions` / `ingest-kunci` / `menu`, atau `topic_id` di `exam_schema.json` (hanya bersama `--standard`).

**Folder standar per bab.** Hasil ingest setiap pack disimpan di `<grading.standards_root>/topik_<bab>`, dengan bab = bagian id sebelum titik. Karena itu maksimal **satu pack per bab**: registry menolak dua pack yang memetakan ke folder yang sama (misalnya `1.3` dan `1.5` sama-sama `topik_1`).

## Capabilities

Capability = rewrite notasi (LaTeX / ASCII → token SymPy) yang dipakai recognizer + validator. Terdaftar di `app/capabilities/registry.py`; pack memilih lewat `capability_ids` (pack `1.5` dan `2` saat ini mengaktifkan semuanya).

| Capability id | Bab terkait |
|---------------|-------------|
| `abs` | 2 |
| `indexed_roots` (akar bernama, `x_1` / `x_{1}` / `x₁` → `x`) | 1.5, 2 |
| `interval` (selang, `\cup` / `∪` / ASCII `U`) | 1.3, 3.2 |
| `limit` | 4, 5 |
| `derivative` | 6 |
| `integral` | 7 |
| `transcendental` | 8 |
| `matrix` | 9 |
| `det_inverse` | 10 |
| `vector` | 11 |

## Status per bab

| Bab | Topik | Status | Validasi (hint) |
|-----|--------|--------|-----------------|
| 1.1–1.4 | Sistem bilangan, garis bilangan, selang, sifat | Pendukung MVP | Konseptual; cek notasi selang + LLM |
| 1.5 | Pertidaksamaan (bentuk umum + HP) | **MVP** | SymPy-first (solve/reduce inequality), garis bilangan = set-equivalence |
| 2 | Pertidaksamaan nilai mutlak | **Pack terdaftar** | SymPy-first Abs + compound/`Or`; kasus naratif → UNCERTAIN → LLM |
| 3 | Fungsi | Adapter normalisasi saja (tanpa pack & tanpa tes) | Domain sebagai pertidaksamaan + `\in` selang; grafik/range naratif → LLM |
| 4 | Limit | Adapter normalisasi saja (tanpa pack & tanpa tes) | SymPy `limit` dua sisi / sepihak; trig tak terputuskan → UNCERTAIN → LLM |
| 5 | Kekontinuan | Adapter normalisasi saja (tanpa pack & tanpa tes) | lim dua sisi = f(a); ε-δ / prosa → UNCERTAIN → LLM |
| 6 | Turunan | Adapter normalisasi saja (tanpa pack & tanpa tes) | SymPy `diff` via token DIFF; definisi / rantai bersarang → UNCERTAIN → LLM |
| 7 | Integral | Adapter normalisasi saja (tanpa pack & tanpa tes) | SymPy `integrate` via token INT; `+C` di-strip; substitusi naratif → LLM |
| 8 | Fungsi transenden | Adapter normalisasi saja (tanpa pack & tanpa tes) | DIFF/INT ln·exp; sifat naratif → UNCERTAIN → LLM |
| 9 | Matriks | Adapter normalisasi saja (tanpa pack & tanpa tes) | SymPy `Matrix` +/−/×/skalar/transpos via token MATRIX |
| 10 | Determinan dan invers | Adapter normalisasi saja (tanpa pack & tanpa tes) | `Matrix.det` / `.inv` via token DET/INV |
| 11 | Vektor | Adapter normalisasi saja (tanpa pack & tanpa tes) | MATRIX kolom + NORM/DOT; sudut/triple/prosa → UNCERTAIN → LLM |

## Aturan scope

- Satu domain aktif pada satu waktu untuk fitur grading baru.
- Testdata dan rubric standar harus mencerminkan bab yang sedang di-support.
- Klaim "support bab X" hanya setelah bab itu punya pack + acceptance test hijau.
- Pack berikutnya yang disarankan: **4 Limit** (capability `limit` sudah ada).
