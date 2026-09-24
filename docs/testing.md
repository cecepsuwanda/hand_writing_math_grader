# Konvensi Testing

Panduan menulis dan memperluas tes Math Grader. Discovery memakai **pytest** standar (`Test*` + `test_*`). Tidak ada registry kustom — tambah/hapus kasus cukup dengan menambah/menghapus class atau method.

## Prinsip

1. **Tanpa file test baru** — inventaris `tests/` tertutup. Perluasan hanya di file yang sudah ada.
2. **OOP Python** — kasus uji sebagai method di `class TestNamaDomain:`; fake/double sebagai class.
3. **Mudah ditambah/dikurangi** — unit ekstensi = class (area) + method (kasus). Hapus method/class = hapus coverage; tidak ada daftar registrasi yang harus di-update.
4. **Tanpa live Ollama** di pytest default — mock HTTP / fake client. Smoke live: `scripts/smoke_live.bat` / CLI manual.

## Inventaris file (set tertutup)

| File | Peran |
|------|--------|
| `tests/test_suite.py` | Suite pipeline: config, PDF, vision, extract, LaTeX, SymPy, LLM hybrid, grading, kunci, report, CLI |
| `tests/test_crop_symbolic.py` | Crop helpers, ink layout, two-pass recognizer, symbolic merge, stems/schema |
| `tests/test_crop_confirm.py` | Regions artifact, propose/recrop, `CropController` confirm loop |
| `tests/test_number_line.py` | Parse/compare number line, kunci figure, `StandardFinalComparer.compare_figure` |
| `tests/helpers.py` | Helper bersama dan fake/double lintas file (**bukan** tempat kasus uji) |
| `tests/__init__.py` | Package marker |

```text
❌ Buat tests/test_foo.py / conftest.py berisi kasus uji baru
✅ Tambah class TestFoo atau method test_* di salah satu file di atas
✅ Fake bersama → class di helpers.py
```

## Peta domain → file

| Domain / phase | File | Contoh class (target OOP) |
|----------------|------|---------------------------|
| Config, paths, workspace, exit view | `test_suite.py` | `TestConfig`, `TestPaths`, `TestOutputReset`, `TestExitView` |
| PDF render | `test_suite.py` | `TestPdfRenderer` |
| JSON extract, recognition schema, Ollama client, vision | `test_suite.py` | `TestJsonExtract`, `TestRecognitionSchema`, `TestOllamaClient`, `TestVisionRecognizer` |
| Question merge/split, LaTeX | `test_suite.py` | `TestQuestionMergeExtract`, `TestQuestionSchemaSplit`, `TestLatex` |
| SymPy / inequality, LLM hybrid | `test_suite.py` | `TestMathInequality`, `TestLlmHybrid` |
| Grading, kunci ingest, report, CLI process | `test_suite.py` | `TestGrading`, `TestKunciIngest`, `TestReport`, `TestCliProcess` |
| Crop symbolic / ink / recognizer crops | `test_crop_symbolic.py` | `TestCropHelpers`, `TestInkLayout`, `TestTwoPassRecognizer`, … |
| Crop confirm / recrop | `test_crop_confirm.py` | `TestRegionsArtifact`, `TestCropConfirm`, … |
| Number line / figure compare | `test_number_line.py` | `TestNumberLineParse`, `TestNumberLineCompare`, … |
| PDF fixture, FakeClient bersama | `helpers.py` | `write_pdf`, class `FakeClient`, … |

Jika domain baru tidak cocok tabel di atas: **tetap** pilih file terdekat (biasanya `test_suite.py`) dan buat `class TestNamaDomain:` di sana. Jangan buat file baru.

## Unit ekstensi (tambah / kurangi)

```text
Perubahan fitur
  → pilih file tests yang sudah ada
  → tambah atau edit class TestDomain
  → tambah atau hapus method test_*
  → jalankan pytest subset
```

| Aksi | Cara |
|------|------|
| Tambah area domain | `class TestNamaBaru:` di file yang tepat |
| Tambah kasus | `def test_perilaku(self, ...):` di class itu |
| Kurangi kasus / area | Hapus method atau class terkait |
| Shared double | Class di `helpers.py` (atau nested class jika hanya satu file) |

## Pola OOP

Pytest mengumpulkan class plain bernama `Test*` (tidak wajib subclass `unittest.TestCase`).

```python
# ✅ GOOD — method di class Test*
class TestGrading:
    def test_aggregate_full_credit(self) -> None:
        grade = aggregate_question_grade(...)
        assert grade.score == grade.maximum_score

# ✅ GOOD — fake sebagai class (helpers atau nested)
class FakeClient:
    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        return self.content

# ❌ BAD — file baru
# tests/test_grading_extra.py

# ❌ BAD — free-function test di level modul
def test_aggregate_full_credit() -> None:
    ...
```

- Type hints pada signature test (`self` + fixture/arg).
- Fixture bawaan pytest: `tmp_path`, `monkeypatch`, `capsys`.
- Isolasi: prefer `tmp_path`; jangan andalkan artefak `data/output/` dari run CLI.
- Model vision/reasoning di SUT: string uji lokal (`'vision-test'`) atau dari config — jangan hard-code nama model produksi.

## Cara menjalankan

```bash
# Semua tes
pytest

# Satu file
pytest tests/test_number_line.py

# Satu class / method
pytest tests/test_suite.py::TestGrading
pytest tests/test_suite.py::TestGrading::test_aggregate_full_credit

# Filter nama
pytest -k "crop or number_line"
```

Smoke live Ollama **bukan** bagian `pytest` default — lihat [README.md](README.md) § Smoke live.

## Anti-pola

| Jangan | Lakukan |
|--------|---------|
| `tests/test_*.py` baru | Edit file inventaris di atas |
| Free-function `test_*` di level modul | Method di `class Test*` |
| Kasus uji di `conftest.py` | Hanya fixture bersama jika benar-benar perlu; prefer `helpers.py` |
| Panggil Ollama live di pytest | `FakeClient` / `httpx.MockTransport` |
| Duplikasi fake besar lintas file | Class di `helpers.py` |
| God-class test tanpa batas | Satu class per domain sempit; pecah class baru di **file yang sama** |

## Referensi agent

- Rule: `.cursor/rules/testing.mdc`
- Skill: `.cursor/skills/write-math-grader-tests`
