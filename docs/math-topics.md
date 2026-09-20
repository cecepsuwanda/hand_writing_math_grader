# Domain Matematika (Silabus)

Katalog resmi: [`topik.md`](topik.md). Implementasi domain mengikuti urutan bab; jangan loncat bab sebelum yang sebelumnya cukup stabil.

## Urutan implementasi

```text
MVP:  1.5 Pertidaksamaan
Done: 2 Abs; 3 Fungsi; 4 Limit; 5 Kekontinuan; 6 Turunan; 7 Integral; 8 Transenden; 9 Matriks; 10 Det/Invers; 11 Vektor
Next: (silabus domain selesai)
```

## Status per bab

| Bab | Topik | Status | Validasi (hint) |
|-----|--------|--------|-----------------|
| 1 | Sistem Bilangan Real dan Pertidaksamaan | **MVP pada 1.5** | SymPy untuk himpunan penyelesaian; LLM untuk penjelasan sifat/interval jika perlu |
| 1.1–1.4 | Sistem bilangan, garis bilangan, selang, sifat | Supporting MVP | Lebih konseptual; LLM + cek notasi |
| 1.5 | Pertidaksamaan (bentuk umum + HP) | **MVP** | SymPy-first (solve/reduce inequality) |
| 2 | Pertidaksamaan nilai mutlak | **Supported** | SymPy-first Abs + compound/`Or`; case narratif non-set-equivalent → UNCERTAIN→LLM |
| 3 | Fungsi (definisi, domain/range, grafik, operasi) | **Supported** (slice) | Domain-as-inequality + `\in` selang; operasi ekspresi `(f±g)`/`∘`; grafik/range narratif → LLM |
| 4 | Limit | **Supported** (slice) | SymPy `limit` dua sisi finite + ∞→finite; one-sided finite; trig undecidable → UNCERTAIN→LLM |
| 5 | Kekontinuan | **Supported** (slice 5.1) | lim dua sisi = f(a) via LimitClaim + point_value; ε-δ / kiri-kanan / prose → UNCERTAIN→LLM |
| 6 | Turunan | **Supported** (slice 6.3) | SymPy `diff` polinomial via DIFF token; definisi/ε, sepihak, trig, rantai nested → UNCERTAIN→LLM |
| 7 | Integral | **Supported** (slice 7.1) | SymPy `integrate` polinomial via INT token; `+C` di-strip; substitusi/FTC narratif → UNCERTAIN→LLM |
| 8 | Fungsi transenden (ln, exp) | **Supported** (slice 8.3/8.5) | DIFF/INT ln·exp via local_dict; identitas tipis e^{ln x}; sifat narratif → UNCERTAIN→LLM |
| 9 | Matriks dan operasi | **Supported** (slice 9.4/9.7) | SymPy `Matrix` +/−/×/skalar/transpos via MATRIX token; jenis/trace narratif → UNCERTAIN→LLM |
| 10 | Determinan dan invers | **Supported** (slice 10.1–10.3) | SymPy `Matrix.det` / `.inv` via DET/INV tokens; singular & sifat narratif → UNCERTAIN→LLM |
| 11 | Vektor (norm, dot, sudut, …) | **Supported** (slice 11.1–11.6) | MATRIX kolom + NORM/DOT → skalar; unit via `/`; sudut/triple/prose → UNCERTAIN→LLM |

## Aturan scope

- Satu domain aktif pada satu waktu untuk fitur grading baru.
- Testdata dan rubric standar harus mencerminkan bab yang sedang di-support.
- Klaim “support bab X” hanya setelah acceptance criteria bab itu hijau.
