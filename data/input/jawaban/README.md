# Student answer PDFs

PDFs live under **topic buckets**: `topik_<bab>/` (same naming as standards).

- `topik_1/smoke_inequality.pdf` — sample for topik 1.5 smoke / live checks
- `topik_3/…` — Tugas Minggu 3 (fungsi), dll.

The web UI lists and uploads into the **active topic** folder only. Other student submissions stay local (gitignored).

```bash
python -m app.web
# or smoke (PDF under topik_1 when topic 1.5 is active):
python scripts/smoke_live.py smoke_inequality.pdf smoke_001
```

Results go to `data/output/topik_<bab>/<pdf_name>/`.
