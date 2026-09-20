# Student answer PDFs

Place handwritten answer PDFs here for the CLI to pick up.

Tracked sample for smoke / live checks:

- `smoke_inequality.pdf` — minimal inequality worksheet (topik 1.5)

Other student submissions stay local (gitignored). Do not commit personal homework PDFs.

```bash
python -m app.cli process
python -m app.cli process smoke_inequality.pdf
```
