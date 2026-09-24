---
name: write-math-grader-tests
description: >-
  Menulis atau memperluas tes Math Grader tanpa file test baru: class Test*
  OOP di inventaris tests/ yang sudah ada, fake di helpers.py, pytest subset.
  Use when adding tests, extending coverage, writing pytest for a phase,
  fixing failing tests, or when the user mentions testing / pytest / test_suite.
---

# Write Math Grader Tests

## Sebelum coding

1. Baca `docs/testing.md`.
2. Pilih **satu file inventaris** sesuai domain (jangan buat `tests/test_*.py` baru).
3. Hormati rule `.cursor/rules/testing.mdc`.

## Inventaris (set tertutup)

| Domain | File |
|--------|------|
| Pipeline (config → CLI) | `tests/test_suite.py` |
| Crop / ink / symbolic recognition | `tests/test_crop_symbolic.py` |
| Confirm / recrop | `tests/test_crop_confirm.py` |
| Number line / figure | `tests/test_number_line.py` |
| Helper + fake bersama | `tests/helpers.py` |

Domain baru → class `TestNama` di file terdekat (biasanya `test_suite.py`).

## Workflow

```text
Test progress:
- [ ] Domain → file inventaris
- [ ] Class Test* ada atau ditambah
- [ ] Method test_* ditambah/dihapus
- [ ] Fake/double = class (helpers atau nested)
- [ ] pytest subset hijau
- [ ] Tidak ada file test baru / free-function test baru
```

### Tambah / kurangi

- **Tambah area:** `class TestNamaDomain:` di file yang tepat.
- **Tambah kasus:** `def test_perilaku(self, ...):` di class itu.
- **Kurangi:** hapus method/class (tidak ada registry).

### Pola

```python
class TestGrading:
    def test_aggregate_full_credit(self) -> None:
        ...

class FakeClient:  # di helpers.py jika lintas file
    def generate_with_image(self, prompt, image_path, model) -> str:
        return self.content
```

- Fixture: `tmp_path`, `monkeypatch`, `capsys`.
- Isolasi lewat `tmp_path`; jangan andalkan `data/output/` dari CLI.
- Jangan panggil Ollama live di pytest — fake / `httpx.MockTransport`.

## Setelah selesai

Jalankan subset terkait, misalnya:

```bash
pytest tests/test_suite.py::TestGrading
pytest tests/test_number_line.py -q
```

Laporkan file yang diubah, class/method baru, dan perintah pytest yang dijalankan.

## Anti-pola

```text
❌ tests/test_foo.py baru
❌ def test_... di level modul
❌ Kasus uji di conftest.py
❌ Live Ollama di pytest
✅ class TestFoo + def test_... di file inventaris
✅ Fake class di helpers.py
```

## Referensi

- `docs/testing.md`
- `.cursor/rules/testing.mdc`
- Skill phase: `implement-math-grader-phase`
