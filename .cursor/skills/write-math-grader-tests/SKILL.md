---
name: write-math-grader-tests
description: >-
  Menulis atau memperluas tes Math Grader tanpa file test baru: class Test*
  OOP di inventaris tests/ yang sudah ada, setup dari paket tests/support/
  (builders, fakes, harness, asserts — gaya MVC), pytest subset.
  Use when adding tests, extending coverage, writing pytest for a phase,
  fixing failing tests, or when the user mentions testing / pytest / test_suite.
---

# Write Math Grader Tests

## Sebelum coding

1. Baca `docs/testing.md` (terutama § Support MVC).
2. Pilih **satu file inventaris** sesuai domain (jangan buat `tests/test_*.py` baru).
3. Cek `tests/support/` dulu — builder/harness yang dibutuhkan kemungkinan sudah ada.
4. Hormati rule `.cursor/rules/testing.mdc`.

## Inventaris (set tertutup)

| Domain | File |
|--------|------|
| Pipeline (config → web) | `tests/test_suite.py` |
| Crop / ink / symbolic recognition | `tests/test_crop_symbolic.py` |
| Confirm / recrop / editor crop manual / question_crops / labeler | `tests/test_crop_confirm.py` |
| Number line / figure | `tests/test_number_line.py` |
| Support bersama (bukan kasus uji) | `tests/support/` |

Domain baru → class `TestNama` di file terdekat (biasanya `test_suite.py`).

## Support MVC — pilih lapisan

| Butuh… | Ambil dari |
|--------|-----------|
| `Question` / `StudentStep` / `FigureRef` | `builders.make_question`, `make_step`, `make_figure` |
| `QuestionValidation` / rubric | `builders.make_validation`, `make_step_validation`, `sample_rubric` |
| `config.yaml`, PDF, PNG, pages+regions | `builders.write_config`, `write_pdf`, `write_png`, `write_crop_workspace` |
| Standar kunci di `tmp_path` | `harness.q1_standard`, `GradingWorkspace` |
| Halaman / endpoint web | `harness.WebHarness` (+ `.client`, `.pdf()`, `.run_dir()`, `.controller()`, `.jobs`) |
| Job background tanpa thread | `fakes.FakeJobManager` (dipasang otomatis oleh `WebHarness`) |
| `ProcessController` tanpa Ollama | `harness.ProcessHarness` |
| Vision recognizer / Ollama HTTP / LLM judge | `harness.make_recognizer`, `make_ollama_client`, `make_llm_judge`; `fakes.FakeClient`, `FakeProposer`, `RecordingJudge` |
| Assert status validasi / isi respons | `asserts.assert_all_valid`, `assert_step_statuses`, `assert_contains` |

Belum ada? Tambah ke modul lapisan yang sesuai **jika** dipakai ≥ 2 test atau lintas file; kalau sekali pakai, nested class/helper di test itu saja.

## Workflow

```text
Test progress:
- [ ] Domain → file inventaris
- [ ] Class Test* ada atau ditambah
- [ ] Setup dirakit dari tests/support (tanpa salin Question/config/MagicMock)
- [ ] Variasi input → parametrize (ids=...)
- [ ] Method test_* ditambah/dihapus
- [ ] pytest subset hijau (opsional: python -m pyflakes tests, bila terpasang)
- [ ] Tidak ada file test baru / free-function test / kasus uji di tests/support
```

### Tambah / kurangi

- **Tambah area:** `class TestNamaDomain:` di file yang tepat.
- **Tambah kasus:** `def test_perilaku(self, ...):` di class itu.
- **Kurangi:** hapus method/class (tidak ada registry).

### Pola

```python
from tests.support.asserts import assert_all_valid
from tests.support.builders import make_question
from tests.support.harness import WebHarness

class TestMathInequality:
    def test_validator_linear_chain(self) -> None:
        question = make_question('2x-3<5', '2x<8', 'x<4', final='x < 4')
        assert_all_valid(SymPyStepValidator().validate_question(question))

class TestWebDashboard:
    def test_dashboard_lists_pdfs(self, tmp_path, monkeypatch) -> None:
        web = WebHarness(tmp_path, monkeypatch)
        web.pdf('answer.pdf')
        response = web.client.get('/')
        assert response.status_code == 200
        assert 'answer.pdf' in response.text
```

- Fixture: `tmp_path`, `monkeypatch`.
- Isolasi lewat `tmp_path`; jangan andalkan `data/output/` asli.
- Job web berjalan sinkron lewat `FakeJobManager`; jangan menjalankan uvicorn di pytest.
- Jangan panggil Ollama live di pytest — `FakeClient` / `make_ollama_client`.

## Setelah selesai

Jalankan subset terkait, misalnya:

```bash
pytest tests/test_suite.py::TestScoreAggregate
pytest tests/test_number_line.py -q
python -m pyflakes tests   # opsional; pyflakes tidak ada di requirements.txt
```

Laporkan file yang diubah, class/method baru, helper support baru (jika ada), dan perintah pytest yang dijalankan.

## Anti-pola

```text
❌ tests/test_foo.py baru
❌ def test_... di level modul
❌ Kasus uji di conftest.py atau tests/support/
❌ Live Ollama di pytest
❌ Salin blok Question(...) / YAML config / 7 MagicMock stage
✅ class TestFoo + def test_... di file inventaris
✅ Builder/fake/harness di tests/support/<lapisan>.py
```

## Referensi

- `docs/testing.md`
- `.cursor/rules/testing.mdc`
- Skill perluasan: `extend-math-grader`
