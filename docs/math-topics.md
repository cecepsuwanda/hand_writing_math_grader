# Domain Matematika (Silabus)

Katalog resmi: [`topik.md`](topik.md). Implementasi domain mengikuti urutan bab; jangan loncat bab sebelum yang sebelumnya cukup stabil.

## Urutan implementasi

```text
MVP:  1.5 Pertidaksamaan
Next: 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11
```

## Status per bab

| Bab | Topik | Status | Validasi (hint) |
|-----|--------|--------|-----------------|
| 1 | Sistem Bilangan Real dan Pertidaksamaan | **MVP pada 1.5** | SymPy untuk himpunan penyelesaian; LLM untuk penjelasan sifat/interval jika perlu |
| 1.1–1.4 | Sistem bilangan, garis bilangan, selang, sifat | Supporting MVP | Lebih konseptual; LLM + cek notasi |
| 1.5 | Pertidaksamaan (bentuk umum + HP) | **MVP** | SymPy-first (solve/reduce inequality) |
| 2 | Pertidaksamaan nilai mutlak | Next | SymPy-first; pecah kasus absolut |
| 3 | Fungsi (definisi, domain/range, grafik, operasi) | Later | Domain/operasi: SymPy; grafik/justifikasi: LLM-heavy |
| 4 | Limit | Later | SymPy `limit` bila ekspresi jelas; trigonometri/∞: campur LLM |
| 5 | Kekontinuan | Later | Lebih banyak LLM (argumentasi); SymPy untuk evaluasi titik |
| 6 | Turunan | Later | SymPy `diff` untuk aturan; definisi/ε-gaya: LLM |
| 7 | Integral | Later | SymPy `integrate`; substitusi/justifikasi langkah: campur |
| 8 | Fungsi transenden (ln, exp) | Later | SymPy untuk turunan/integral; sifat: campur |
| 9 | Matriks dan operasi | Later | SymPy Matrix |
| 10 | Determinan dan invers | Later | SymPy Matrix (2×2, 3×3) |
| 11 | Vektor (norm, dot, sudut, …) | Later | SymPy vectors / ekspresi; LLM untuk interpretasi |

## Aturan scope

- Satu domain aktif pada satu waktu untuk fitur grading baru.
- Testdata dan rubric standar harus mencerminkan bab yang sedang di-support.
- Klaim “support bab X” hanya setelah acceptance criteria bab itu hijau.
