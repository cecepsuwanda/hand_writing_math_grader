# Konvensi Testing

Panduan menulis dan memperluas tes Math Grader. Discovery memakai **pytest** standar (`Test*` + `test_*`). Tidak ada registry kustom — tambah/hapus kasus cukup dengan menambah/menghapus class atau method.

## Prinsip

1. **Tanpa file test baru** — inventaris `tests/` tertutup. Perluasan hanya di file yang sudah ada.
2. **OOP Python** — kasus uji sebagai method di `class TestNamaDomain:`; fake/double sebagai class.
3. **Mudah ditambah/dikurangi** — unit ekstensi = class (area) + method (kasus). Hapus method/class = hapus coverage; tidak ada daftar registrasi yang harus di-update.
4. **Ringkas lewat `tests/support/`** — setup berulang (objek domain, config, fake, harness CLI/pipeline) dipanggil dari paket support bergaya MVC, bukan disalin per test.
5. **Tanpa live Ollama** di pytest default — mock HTTP / fake client. Smoke live: `scripts/smoke_live.bat` / CLI manual.

## Inventaris file (set tertutup)

| File | Peran |
|------|--------|
| `tests/test_suite.py` | Suite pipeline: config, PDF, vision, extract, LaTeX, SymPy, LLM hybrid, grading, kunci, report, CLI, topic pack |
| `tests/test_crop_symbolic.py` | Crop helpers, ink layout, two-pass recognizer, symbolic merge, stems/schema |
| `tests/test_crop_confirm.py` | Regions artifact, propose/recrop, `CropController` confirm loop, `question_crops`, labeler |
| `tests/test_number_line.py` | Parse/compare number line, kunci figure, `StandardFinalComparer.compare_figure` |
| `tests/support/` | Paket support bersama (builders, fakes, harness, asserts) — **bukan** tempat kasus uji |
| `tests/__init__.py` | Package marker |

```text
❌ Buat tests/test_foo.py / conftest.py berisi kasus uji baru
❌ Kasus uji (def test_ / class Test*) di tests/support/
✅ Tambah class TestFoo atau method test_* di salah satu file test di atas
✅ Setup/fake bersama → tests/support/<lapisan>.py
```

## Support MVC (`tests/support/`)

Setiap lapisan punya satu tanggung jawab; test cukup merangkai ketiganya lalu meng-assert.

| Modul | Lapisan | Isi utama |
|-------|---------|-----------|
| `builders.py` | Model | Factory objek domain & fixture file: `make_question`, `make_step`, `make_figure`, `symbolic`, `make_validation`, `make_step_validation`, `make_step_grade`, `sample_rubric`, `make_process_result`, `make_process_question_grade`, `make_report_question_grade`, `make_report_metadata`, `make_report_result`, `make_page`; `write_pdf`, `write_png`, `write_fake_png_bytes`, `write_config`, `write_crop_workspace`, `write_recognition`, `write_report_workspace`, `single_question_json`; konstanta `MINI_KUNCI`, `Q1_KUNCI` |
| `fakes.py` | Double port | `FakeClient` (Ollama vision/text), `FakeProposer` (ink), `RecordingJudge` (LLM judge), `RecordingMenuActions` (port `MenuActions` untuk `MenuController`), `RecordingProcessController` (pengganti `build_process_controller`), `FakeLatexRunner` (pengganti `subprocess.run` untuk `PdfLatexCompiler`) |
| `harness.py` | Controller | `CliHarness` (config temp + patch `app.cli.build_*` + `main()`), `ProcessHarness` (`ProcessController` dengan 7 stage `MagicMock`; `progress` = stage, `progress_events` = `ProcessProgress` lengkap), `GradingWorkspace` (standar + folder questions → `GradeController`), `q1_standard`, `make_recognizer`, `make_ollama_client`, `make_llm_judge`, `patch_tty` (patch `sys.stdin.isatty`), `patch_inputs` (patch `builtins.input`) |
| `asserts.py` | View | `assert_all_valid`, `assert_step_statuses`, `assert_contains` (teks CLI) |

Aturan:

- Import eksplisit dari submodul: `from tests.support.builders import make_question`.
- Tambah builder/harness/fake **hanya** jika dipakai ≥ 2 test atau lintas file; double sekali pakai tetap nested class di test-nya.
- Builder murni menulis model/file; harness boleh memanggil service/controller (mis. `KunciIngester`, `GradeController`).
- Default builder = kasus paling umum (question 1, status VALID, model `'vision-test'`/`'test-model'`); override lewat keyword.

Contoh test baru yang ringkas:

```python
class TestStepGrader:
    def test_step_grader_with_standard(self, tmp_path: Path) -> None:
        workspace = GradingWorkspace(tmp_path)          # controller
        workspace.add_solution()
        workspace.add_question(
            make_question('2x-3<5', 'x<4', final='x<4'),  # model
            make_validation(ValidationStatus.VALID, ValidationStatus.VALID),
        )
        grade = workspace.grade(with_comparer=True).grades[0]
        assert grade.score == pytest.approx(10.0)

class TestCliProcess:
    def test_cli_process_resolves_bare_filename(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        pdf = cli.pdf('smoke_inequality.pdf')
        fake = cli.controller()
        assert cli.run('process', 'smoke_inequality.pdf') == 0
        assert fake.pdf_paths == [pdf]
```

Variasi input/ekspektasi pada perilaku yang sama → `@pytest.mark.parametrize` (dengan `ids=`), bukan method salinan.

## Peta domain → file

| Domain / phase | File | Contoh class (target OOP) |
|----------------|------|---------------------------|
| Config, paths, menu choices, run layout, workspace, style/exit/prompt view | `test_suite.py` | `TestConfig`, `TestPaths`, `TestMenuChoices`, `TestRunLayout`, `TestOutputReset`, `TestStyleView`, `TestExitView`, `TestPromptView` |
| PDF render | `test_suite.py` | `TestPdfRenderer` |
| JSON extract, recognition schema, Ollama client, vision | `test_suite.py` | `TestJsonExtract`, `TestRecognitionSchema`, `TestOllamaClient`, `TestVisionRecognizer` |
| Question merge/split, review question.json, LaTeX | `test_suite.py` | `TestQuestionMergeExtract`, `TestQuestionReview`, `TestQuestionSchemaSplit`, `TestLatex` |
| SymPy / inequality, LLM hybrid (+ `validation_artifact`) | `test_suite.py` | `TestMathInequality`, `TestLlmHybrid` |
| Grading (skor, grader, standar, soft-align) | `test_suite.py` | `TestScoreAggregate`, `TestStepGrader`, `TestStandardExtract`, `TestStandardComparer`, `TestStepAlign` |
| Kunci ingest, report (+ `grading_artifact`, `artifact_guard`), CLI process / finish-questions + `ProcessController` | `test_suite.py` | `TestKunciIngest`, `TestReport`, `TestCliProcess` |
| Menu interaktif (`MenuController`, dispatch, `_ensure_layout`, exit code, EOF) | `test_suite.py` | `TestMenuController` |
| Topic pack / capability registry | `test_suite.py` | `TestTopicRegistry`, `TestTopicPackBehavior`, `TestCapabilityDispatch` |
| Crop symbolic / ink / recognizer crops | `test_crop_symbolic.py` | `TestCropHelpers`, `TestSymbolicMerge`, `TestTwoPassRecognizer`, `TestInkLayout`, `TestRecognitionStems` |
| Confirm / recrop / question_crops / labeler | `test_crop_confirm.py` | `TestRegionsArtifact`, `TestCropConfirm`, `TestQuestionCrops`, `TestQuestionLabelController`, `TestRecognizerQuestionCrops` |
| Number line / figure compare | `test_number_line.py` | `TestNumberLineParse`, `TestNumberLineCompare`, `TestNumberLineIngest`, `TestCompareFigure` |

Jika domain baru tidak cocok tabel di atas: **tetap** pilih file terdekat (biasanya `test_suite.py`) dan buat `class TestNamaDomain:` di sana. Jangan buat file baru.

## Unit ekstensi (tambah / kurangi)

```text
Perubahan fitur
  → pilih file tests yang sudah ada
  → tambah atau edit class TestDomain
  → tambah atau hapus method test_* (setup dari tests/support/)
  → jalankan pytest subset
```

| Aksi | Cara |
|------|------|
| Tambah area domain | `class TestNamaBaru:` di file yang tepat |
| Tambah kasus | `def test_perilaku(self, ...):` di class itu, rakit dari builders/harness |
| Variasi kasus sama | Tambah baris `parametrize` |
| Kurangi kasus / area | Hapus method atau class terkait |
| Shared double / setup | Class/fungsi di `tests/support/` (nested class jika hanya satu test) |

## Pola OOP

Pytest mengumpulkan class plain bernama `Test*` (tidak wajib subclass `unittest.TestCase`).

```python
# ✅ GOOD — method di class Test*, setup dari tests/support
class TestScoreAggregate:
    def test_aggregate_full_credit(self) -> None:
        validation = make_validation(*[ValidationStatus.VALID] * 4)
        grade = aggregate_question_grade(question_id='question_001', question_number=1,
                                         validation=validation, rubric=sample_rubric())
        assert grade.score == grade.maximum_score

# ✅ GOOD — fake sebagai class (tests/support/fakes.py atau nested)
class FakeClient:
    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        return self.content

# ❌ BAD — file baru
# tests/test_grading_extra.py

# ❌ BAD — free-function test di level modul
def test_aggregate_full_credit() -> None:
    ...

# ❌ BAD — salin 10 baris Question(...)/config YAML/MagicMock per test
```

- Type hints pada signature test (`self` + fixture/arg).
- Fixture bawaan pytest: `tmp_path`, `monkeypatch`, `capsys`.
- Isolasi: prefer `tmp_path`; jangan andalkan artefak `data/output/` dari run CLI. `CliHarness` selalu mengarahkan `output.root_dir` ke `tmp_path/output`.
- Butuh standar kunci (solutions/schema/rubrics)? Pakai `q1_standard(tmp_path)` (ingest `Q1_KUNCI` lewat `KunciIngester`) atau `GradingWorkspace`; jangan baca `data/output/standards/`.
- Model vision/reasoning di SUT: string uji lokal (`'vision-test'`) atau dari config — jangan hard-code nama model produksi.

## Cara menjalankan

```bash
# Semua tes
pytest

# Satu file
pytest tests/test_number_line.py

# Satu class / method
pytest tests/test_suite.py::TestScoreAggregate
pytest tests/test_suite.py::TestScoreAggregate::test_aggregate_full_credit

# Filter nama
pytest -k "crop or number_line"
```

Smoke live Ollama **bukan** bagian `pytest` default — lihat [README root](../README.md#smoke-live-butuh-ollama).

## Anti-pola

| Jangan | Lakukan |
|--------|---------|
| `tests/test_*.py` baru | Edit file inventaris di atas |
| Free-function `test_*` di level modul | Method di `class Test*` |
| Kasus uji di `conftest.py` atau `tests/support/` | Kasus uji hanya di file test; support berisi builder/fake/harness |
| Panggil Ollama live di pytest | `FakeClient` / `make_ollama_client` (`httpx.MockTransport`) |
| Duplikasi setup (Question, config YAML, stage `MagicMock`) lintas test | Builder / harness di `tests/support/` |
| Method salinan yang hanya beda input | `@pytest.mark.parametrize` |
| God-class test tanpa batas | Satu class per domain sempit; pecah class baru di **file yang sama** |

## Referensi agent

- Rule: `.cursor/rules/testing.mdc`
- Skill: `.cursor/skills/write-math-grader-tests`
