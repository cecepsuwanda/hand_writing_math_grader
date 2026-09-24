from __future__ import annotations
from app.cli import main
from app.config import DEFAULT_CONFIG_PATH, load_config
from app.controllers.grade_controller import GradeController
from app.controllers.ingest_kunci_controller import IngestKunciController
from app.controllers.process_controller import ProcessController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.report_controller import ReportController
from app.exceptions import EmptyExtractionError, RecognitionNotFoundError
from app.exceptions import EmptyPdfError, InvalidPdfError, PdfNotFoundError
from app.exceptions import GradingNotFoundError
from app.exceptions import InvalidRecognitionJsonError, OllamaModelNotConfiguredError
from app.exceptions import MathParseError
from app.exceptions import OllamaTimeoutError, OllamaUnavailableError
from app.exceptions import PdfNotFoundError
from app.exceptions import QuestionsNotFoundError
from app.exceptions import RecognitionPathMismatchError
from app.exceptions import ValidationNotFoundError
from app.functions.json_extract import (
    extract_json_object,
    repair_json_escapes,
    repair_llm_json_syntax,
    salvage_judgement_object,
)
from app.functions.kunci_ingest import build_exam_schema, extract_align_steps, extract_hp_final, extract_question_stems, extract_soal_number, format_recognition_question_block, ingest_kunci_tex, item_expects_figure, load_exam_schema, load_question_stems_from_kunci, split_enumerate_items
from app.functions.latex_transforms import build_student_latex, escape_latex_text, format_aligned_line, normalize_step_latex, strip_final_answer_prefix
from app.functions.page_names import page_image_filename
from app.functions.paths import list_jawaban_pdfs, list_kunci_tex, parse_kunci_choice, parse_main_menu_choice, parse_path_choice, parse_pdf_choice, resolve_jawaban_pdf
from app.functions.question_merge import collect_latex_documents, merge_page_recognitions
from app.functions.question_names import question_dir_name
from app.functions.question_split import split_questions_by_exam_schema
from app.models.exam_schema import ExamQuestion, ExamSchema
from app.functions.report_aggregate import aggregate_exam_report, summary_csv_rows
from app.functions.score_aggregate import aggregate_question_grade, allocate_step_max_scores
from app.functions.standard_extract import exam_schema_path, extract_final_answer_from_tex, extract_solution_steps_from_tex, standard_solution_path
from app.functions.step_align import align_student_steps_to_standard
from app.models.grading import ErrorType, QuestionGrade, ReviewStatus, StepGrade, StepGradeStatus
from app.models.grading import GradeResult, QuestionGrade, ReviewStatus
from app.models.grading import ReviewStatus, Rubric, RubricCriterion
from app.models.grading import Rubric, RubricCriterion
from app.models.latex import LatexResult
from app.models.page import Page
from app.models.page import Page, RenderResult
from app.models.process import ProcessStage
from app.models.question import ExtractResult
from app.models.question import Question, StudentStep
from app.models.question import SegmentationStatus
from app.models.recognition import PageRecognition, RecognizedQuestion, RecognizedStep, Region, SymbolicPayload
from app.models.recognition import RecognizeResult
from app.models.report import ExamReport, PromptVersions, QuestionReportRow, ReportMetadata, ReportResult
from app.models.report import PromptVersions, ReportMetadata
from app.models.validation import QuestionValidation, StepValidation, ValidationMethod, ValidationStatus
from app.models.validation import ValidateResult
from app.models.validation import ValidationMethod, ValidationStatus
from app.models.validation import ValidationStatus
from app.services.grading.report import JsonCsvHtmlReporter
from app.services.grading.rubric import RubricLoader
from app.services.grading.standard_comparer import StandardFinalComparer
from app.services.grading.step_grader import StepGrader
from app.services.latex.builder import LatexBuilder
from app.services.math.equivalence import relations_equivalent, relations_form_equivalent
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.llm_judge import LlmStepJudge
from app.services.math.parser import normalize_math_text, parse_relation
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.questions.extractor import QuestionExtractor
from app.services.standards.kunci_ingester import KunciIngester
from app.services.vision.ollama_client import OllamaClient
from app.services.vision.recognizer import OllamaVisionRecognizer, PROMPT_VERSION
from app.services.workspace.cleaner import clear_output_workspace, prepare_pipeline_workspace
from app.views.exit_view import (
    mark_interactive_session_done,
    prompt_continue_or_exit,
    reset_interactive_session_flag,
    wait_for_exit,
)
from pathlib import Path
from pydantic import ValidationError
from sympy import Eq, Lt, Symbol
from tests.helpers import write_pdf
from unittest.mock import MagicMock
import httpx
import json
import pytest

def _image(tmp_path: Path) -> Path:
    path = tmp_path / 'page.png'
    path.write_bytes(b'\x89PNG\r\n\x1a\nfake')
    return path

class FakeClient:

    def __init__(self, content: str | list[str]) -> None:
        if isinstance(content, list):
            self._queue = list(content)
            self.content = content[0] if content else ''
        else:
            self._queue = None
            self.content = content
        self.calls: list[tuple[str, Path, str]] = []

    def generate_with_image(self, prompt: str, image_path: Path, model: str) -> str:
        self.calls.append((prompt, image_path, model))
        if self._queue is not None:
            if not self._queue:
                raise AssertionError('FakeClient exhausted response queue')
            return self._queue.pop(0)
        return self.content

def _write_recognition(path: Path, page: PageRecognition) -> None:
    path.write_text(page.model_dump_json(indent=2), encoding='utf-8')

class RecordingJudge:

    def __init__(self, response: dict | None=None, *, fail_json: bool=False) -> None:
        self.calls: list[tuple] = []
        self.response = response or {'status': 'uncertain', 'reason': 'not enough evidence', 'confidence': 0.4}
        self.fail_json = fail_json

    def judge_transition(self, **kwargs):
        self.calls.append(('transition', kwargs))
        from app.models.validation import StepValidation
        if self.fail_json:
            return StepValidation(step_number=kwargs['step_number'], status=ValidationStatus.UNCERTAIN, method=ValidationMethod.LLM, reason='invalid LLM response: bad json')
        return StepValidation(step_number=kwargs['step_number'], status=ValidationStatus(self.response['status']), method=ValidationMethod.LLM, reason=self.response.get('reason', ''), confidence=self.response.get('confidence'))

    def judge_final_answer(self, **kwargs):
        self.calls.append(('final', kwargs))
        return self.judge_transition(step_number=kwargs['step_number'], previous=kwargs.get('last_step'), current=None)

def _sample_rubric() -> Rubric:
    return Rubric(question=1, maximum_score=10, criteria=[RubricCriterion(id='setup', points=2), RubricCriterion(id='transformation', points=4), RubricCriterion(id='calculation', points=2), RubricCriterion(id='final_answer', points=2)])

def _step(n: int, status: ValidationStatus, reason: str='') -> StepValidation:
    return StepValidation(step_number=n, status=status, method=ValidationMethod.SYMPY, reason=reason or status.value)
_MINI_KUNCI = '\n\\begin{document}\n\\begin{enumerate}\n    \\item $2-3x \\le 12$\n    \\begin{itemize}\n    \\item Langkah-langkah\n    \\begin{align}\n    2 - 3x &\\leq 12 \\quad \\text{(awal)} \\\\\n    x &\\geq -\\frac{10}{3}\n    \\end{align}\n    \\item HP: $\\left[-\\frac{10}{3}, \\infty\\right)$\n    \\end{itemize}\n\n    \\item $3x-5 < 4x-6$\n    \\begin{itemize}\n    \\item Langkah-langkah\n    \\begin{align}\n    3x - 5 &< 4x - 6 \\\\\n    x &> 1\n    \\end{align}\n    \\item HP: $(1, \\infty)$\n    \\end{itemize}\n\\end{enumerate}\n\\end{document}\n'

def _step_grade(n: int, score: float, max_score: float, *, status: StepGradeStatus=StepGradeStatus.CORRECT, validation: ValidationStatus=ValidationStatus.VALID) -> StepGrade:
    return StepGrade(step_number=n, score=score, max_score=max_score, status=status, error_type=ErrorType.NONE, feedback='', validation_status=validation)

def _report_question_grade(number: int, score: float, maximum: float, *, review: ReviewStatus=ReviewStatus.AUTO_ACCEPT, steps: int=2) -> QuestionGrade:
    per = maximum / max(steps, 1)
    return QuestionGrade(question_id=f'question_{number:03d}', question_number=number, score=score, maximum_score=maximum, steps=[_step_grade(i + 1, per if i < steps - 1 else score - per * (steps - 1), per) for i in range(steps)], review_status=review)

def _metadata(tmp_path: Path) -> ReportMetadata:
    return ReportMetadata(generated_at='2026-01-01T00:00:00+00:00', standard_dir=tmp_path / 'standards' / 'exam_001', questions_dir=tmp_path / 'questions', student_id='student_001', vision_model='vision-test', reasoning_model='reason-test', prompt_versions=PromptVersions(recognition='recognition-v1', validation='validation-v1', grading='grading-v1'))

def _page() -> Page:
    return Page(page_number=1, image='page_001.png', width=100, height=100)

def _process_question_grade() -> QuestionGrade:
    return QuestionGrade(question_id='question_001', question_number=1, score=8.0, maximum_score=10.0, review_status=ReviewStatus.AUTO_ACCEPT)

def _report_result(tmp_path: Path) -> ReportResult:
    out = tmp_path / 'output'
    meta = ReportMetadata(generated_at='2026-01-01T00:00:00+00:00', standard_dir=tmp_path / 'standards', questions_dir=tmp_path / 'questions', student_id='student_001', prompt_versions=PromptVersions())
    exam = ExamReport(metadata=meta, questions=[QuestionReportRow(question_id='question_001', question_number=1, score=8.0, maximum_score=10.0, review_status=ReviewStatus.AUTO_ACCEPT, step_count=2)], total_score=8.0, maximum_total=10.0, overall_status=ReviewStatus.AUTO_ACCEPT)
    return ReportResult(exam_report=exam, output_dir=out, report_json_path=out / 'report.json', summary_csv_path=out / 'summary.csv', report_html_path=out / 'report.html')

class TestConfig:

    def test_default_config_path_points_at_package_yaml(self) -> None:
        assert DEFAULT_CONFIG_PATH.name == 'config.yaml'
        assert DEFAULT_CONFIG_PATH.parent.name == 'config'
        assert DEFAULT_CONFIG_PATH.is_file()

    def test_load_config_default_reads_package_yaml(self) -> None:
        config = load_config()
        assert config.pdf.dpi == 200
        assert config.pdf.output_dir == Path('data/output/pages')
        assert config.input.jawaban_dir == Path('data/input/jawaban')
        assert config.input.kunci_jawaban_dir == Path('data/input/kunci_jawaban')
        assert config.recognition.output_dir == Path('data/output/recognition')
        assert config.questions.output_dir == Path('data/output/questions')
        assert config.grading.standard_dir == Path('data/output/standards/exam_001')
        assert config.report.output_dir == Path('data/output')
        assert config.ollama.base_url == 'http://localhost:11434'
        assert isinstance(config.recognition.output_dir, Path)

class TestPaths:

    def test_resolve_jawaban_pdf_prefers_existing_path(self, tmp_path: Path) -> None:
        pdf = tmp_path / 'direct.pdf'
        pdf.write_bytes(b'%PDF')
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        assert resolve_jawaban_pdf(pdf, jawaban) == pdf

    def test_resolve_jawaban_pdf_finds_bare_name_under_jawaban(self, tmp_path: Path) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        pdf = jawaban / 'smoke_inequality.pdf'
        pdf.write_bytes(b'%PDF')
        assert resolve_jawaban_pdf(Path('smoke_inequality.pdf'), jawaban) == pdf

    def test_resolve_jawaban_pdf_returns_original_when_missing(self, tmp_path: Path) -> None:
        missing = Path('missing.pdf')
        assert resolve_jawaban_pdf(missing, tmp_path / 'jawaban') == missing

    def test_list_jawaban_pdfs_sorted(self, tmp_path: Path) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        (jawaban / 'b.pdf').write_bytes(b'%PDF')
        (jawaban / 'a.PDF').write_bytes(b'%PDF')
        (jawaban / 'notes.txt').write_text('x', encoding='utf-8')
        (jawaban / 'subdir').mkdir()
        names = [p.name for p in list_jawaban_pdfs(jawaban)]
        assert names == ['a.PDF', 'b.pdf']

    def test_parse_pdf_choice_by_index_and_name(self, tmp_path: Path) -> None:
        pdfs = [tmp_path / 'one.pdf', tmp_path / 'two.pdf']
        for pdf in pdfs:
            pdf.write_bytes(b'%PDF')
        assert parse_pdf_choice(pdfs, '2') == pdfs[1]
        assert parse_pdf_choice(pdfs, 'one.pdf') == pdfs[0]
        assert parse_pdf_choice(pdfs, 'TWO') == pdfs[1]
        with pytest.raises(ValueError):
            parse_pdf_choice(pdfs, '9')

    def test_parse_pdf_choice_prefers_filename_over_index(self, tmp_path: Path) -> None:
        pdfs = [tmp_path / 'alpha.pdf', tmp_path / '2.pdf']
        for pdf in pdfs:
            pdf.write_bytes(b'%PDF')
        assert parse_pdf_choice(pdfs, '2') == pdfs[1]
        assert parse_pdf_choice(pdfs, '1') == pdfs[0]

    def test_list_kunci_tex_sorted(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci'
        kunci.mkdir()
        (kunci / 'b.tex').write_text('%', encoding='utf-8')
        (kunci / 'a.TEX').write_text('%', encoding='utf-8')
        (kunci / 'notes.txt').write_text('x', encoding='utf-8')
        names = [p.name for p in list_kunci_tex(kunci)]
        assert names == ['a.TEX', 'b.tex']

    def test_parse_kunci_and_path_choice(self, tmp_path: Path) -> None:
        files = [tmp_path / 'one.tex', tmp_path / 'two.tex']
        for path in files:
            path.write_text('%', encoding='utf-8')
        assert parse_kunci_choice(files, '2') == files[1]
        assert parse_kunci_choice(files, 'one') == files[0]
        assert parse_path_choice(files, 'TWO.tex', kind='kunci', default_suffix='.tex') == files[1]

    def test_parse_main_menu_choice(self) -> None:
        assert parse_main_menu_choice('1') == 'ingest'
        assert parse_main_menu_choice('ingest') == 'ingest'
        assert parse_main_menu_choice('2') == 'propose_crops'
        assert parse_main_menu_choice('propose') == 'propose_crops'
        assert parse_main_menu_choice('3') == 'recrop'
        assert parse_main_menu_choice('recrop') == 'recrop'
        assert parse_main_menu_choice('4') == 'finish'
        assert parse_main_menu_choice('proses') == 'finish'
        assert parse_main_menu_choice('5') == 'exit'
        assert parse_main_menu_choice('keluar') == 'exit'
        with pytest.raises(ValueError):
            parse_main_menu_choice('9')
        with pytest.raises(ValueError):
            parse_main_menu_choice('  ')

class TestOutputReset:

    def test_clear_output_workspace_preserves_standards(self, tmp_path: Path) -> None:
        root = tmp_path / 'output'
        pages = root / 'pages'
        pages.mkdir(parents=True)
        (pages / 'page_001.png').write_bytes(b'x')
        (root / 'report.json').write_text('{}', encoding='utf-8')
        standards = root / 'standards' / 'exam_001'
        standards.mkdir(parents=True)
        rubric = standards / 'rubric.json'
        rubric.write_text('{}', encoding='utf-8')
        removed = clear_output_workspace(root)
        assert sorted(removed) == ['pages', 'report.json']
        assert not pages.exists()
        assert not (root / 'report.json').exists()
        assert rubric.is_file()

    def test_clear_output_workspace_creates_missing_root(self, tmp_path: Path) -> None:
        root = tmp_path / 'missing-output'
        assert clear_output_workspace(root) == []
        assert root.is_dir()

    def test_prepare_pipeline_workspace_clears_dirs_outside_root(self, tmp_path: Path) -> None:
        root = tmp_path / 'output'
        root.mkdir()
        (root / 'stale.txt').write_text('x', encoding='utf-8')
        standards = root / 'standards'
        standards.mkdir()
        (standards / 'keep.txt').write_text('keep', encoding='utf-8')
        pages_dir = tmp_path / 'external_pages'
        recognition_dir = tmp_path / 'external_recognition'
        questions_dir = tmp_path / 'external_questions'
        crops_dir = tmp_path / 'external_crops'
        for directory in (pages_dir, recognition_dir, questions_dir, crops_dir):
            directory.mkdir()
            (directory / 'old.bin').write_bytes(b'old')
        removed = prepare_pipeline_workspace(
            root,
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            crops_dir=crops_dir,
        )
        assert 'stale.txt' in removed
        assert not (pages_dir / 'old.bin').exists()
        assert not (recognition_dir / 'old.bin').exists()
        assert not (questions_dir / 'old.bin').exists()
        assert not (crops_dir / 'old.bin').exists()
        assert (standards / 'keep.txt').is_file()
        assert pages_dir.is_dir()

class TestExitView:

    def test_wait_for_exit_skips_when_stdin_not_tty(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        stdin = MagicMock()
        stdin.isatty.return_value = False
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        called = []

        def fake_input(prompt: str='') -> str:
            called.append(prompt)
            return ''
        monkeypatch.setattr('builtins.input', fake_input)
        wait_for_exit()
        assert called == []

    def test_wait_for_exit_prompts_when_stdin_is_tty(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        called: list[str] = []

        def fake_input(prompt: str='') -> str:
            called.append(prompt)
            return ''
        monkeypatch.setattr('builtins.input', fake_input)
        wait_for_exit()
        assert len(called) == 1
        assert 'Enter' in called[0]

    def test_wait_for_exit_ignores_eof(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        monkeypatch.setattr('builtins.input', MagicMock(side_effect=EOFError))
        wait_for_exit()

    def test_wait_for_exit_skips_after_interactive_session(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        mark_interactive_session_done()
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        called: list[str] = []
        monkeypatch.setattr('builtins.input', lambda p='': called.append(p) or '')
        wait_for_exit()
        assert called == []
        reset_interactive_session_flag()

    def test_prompt_continue_or_exit_non_tty(self, monkeypatch) -> None:
        stdin = MagicMock()
        stdin.isatty.return_value = False
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        assert prompt_continue_or_exit() == 'exit'

    def test_prompt_continue_or_exit_choice_continue(self, monkeypatch) -> None:
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        monkeypatch.setattr('builtins.input', lambda _p='': '1')
        assert prompt_continue_or_exit() == 'continue'

    def test_prompt_continue_or_exit_choice_exit(self, monkeypatch) -> None:
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        monkeypatch.setattr('builtins.input', lambda _p='': '2')
        assert prompt_continue_or_exit() == 'exit'

    def test_prompt_continue_or_exit_retries_then_exit(self, monkeypatch) -> None:
        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        answers = iter(['x', '2'])
        monkeypatch.setattr('builtins.input', lambda _p='': next(answers))
        assert prompt_continue_or_exit() == 'exit'

class TestPdfRenderer:

    def test_page_image_filename_is_zero_padded(self) -> None:
        assert page_image_filename(1) == 'page_001.png'
        assert page_image_filename(12) == 'page_012.png'
        assert page_image_filename(100) == 'page_100.png'

    def test_page_image_filename_rejects_non_positive(self) -> None:
        with pytest.raises(ValueError):
            page_image_filename(0)

    def test_render_single_page_pdf(self, tmp_path: Path) -> None:
        pdf_path = write_pdf(tmp_path / 'single.pdf', 1)
        output_dir = tmp_path / 'pages'
        pages = PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)
        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].image == 'page_001.png'
        assert pages[0].width > 0
        assert pages[0].height > 0
        assert (output_dir / 'page_001.png').is_file()
        assert (output_dir / 'pages.json').is_file()

    def test_render_multi_page_pdf(self, tmp_path: Path) -> None:
        pdf_path = write_pdf(tmp_path / 'multi.pdf', 3)
        output_dir = tmp_path / 'pages'
        pages = PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)
        assert [page.page_number for page in pages] == [1, 2, 3]
        assert [page.image for page in pages] == ['page_001.png', 'page_002.png', 'page_003.png']
        for page in pages:
            assert (output_dir / page.image).is_file()
            assert page.width > 0
            assert page.height > 0
        metadata = json.loads((output_dir / 'pages.json').read_text(encoding='utf-8'))
        assert len(metadata) == 3
        assert metadata[1]['image'] == 'page_002.png'

    def test_render_empty_pdf_raises(self, tmp_path: Path) -> None:
        pdf_path = write_pdf(tmp_path / 'empty.pdf', 0)
        output_dir = tmp_path / 'pages'
        with pytest.raises(EmptyPdfError):
            PyMuPdfRenderer().render(pdf_path, output_dir, dpi=72)
        assert not (output_dir / 'page_001.png').exists()
        assert not (output_dir / 'pages.json').exists()

    def test_render_invalid_file_raises(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / 'not.pdf'
        pdf_path.write_bytes(b'this is not a pdf')
        with pytest.raises(InvalidPdfError):
            PyMuPdfRenderer().render(pdf_path, tmp_path / 'pages', dpi=72)

    def test_render_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PdfNotFoundError):
            PyMuPdfRenderer().render(tmp_path / 'missing.pdf', tmp_path / 'pages', dpi=72)

    def test_cli_render_writes_png_and_exits_zero(self, tmp_path: Path, capsys) -> None:
        pdf_path = write_pdf(tmp_path / 'answer.pdf', 2)
        output_dir = tmp_path / 'pages'
        exit_code = main(['render', str(pdf_path), '--output', str(output_dir), '--dpi', '72'])
        assert exit_code == 0
        assert (output_dir / 'page_001.png').is_file()
        assert (output_dir / 'page_002.png').is_file()
        assert (output_dir / 'pages.json').is_file()
        captured = capsys.readouterr()
        assert 'Rendered 2 page(s)' in captured.out

class TestJsonExtract:

    def test_extract_raw_json_object(self) -> None:
        data = extract_json_object('{"page_number": 1, "questions": []}')
        assert data['page_number'] == 1
        assert data['questions'] == []

    def test_extract_json_from_markdown_fence(self) -> None:
        text = 'Here is the result:\n```json\n{"page_number": 2, "questions": [{"question_number": 1, "steps": []}]}\n```\n'
        data = extract_json_object(text)
        assert data['page_number'] == 2
        assert data['questions'][0]['question_number'] == 1

    def test_extract_json_with_surrounding_text(self) -> None:
        text = 'prefix {"page_number": 3, "questions": []} suffix'
        data = extract_json_object(text)
        assert data['page_number'] == 3

    def test_extract_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match='empty model response'):
            extract_json_object('   ')

    def test_extract_rejects_array(self) -> None:
        with pytest.raises(ValueError, match='expected JSON object'):
            extract_json_object('[1, 2, 3]')

    def test_extract_strips_think_wrapper(self) -> None:
        text = '<think>plan the json</think>\n{"page_number": 4, "questions": []}'
        data = extract_json_object(text)
        assert data['page_number'] == 4

    def test_extract_non_json_includes_preview(self) -> None:
        with pytest.raises(ValueError, match='response_preview'):
            extract_json_object('Here is prose with no braces at all')

    def test_extract_repairs_latex_invalid_escapes(self) -> None:
        text = '{\n  "error_type": "none",\n  "feedback": "Rewrite as x \\in [-10/3, \\infty)"\n}'
        data = extract_json_object(text)
        assert data['error_type'] == 'none'
        assert data['feedback'] == 'Rewrite as x \\in [-10/3, \\infty)'

    def test_extract_repairs_latex_frac_and_neq(self) -> None:
        text = '{"feedback": "use \\frac{1}{2}, not x\\neq 0"}'
        data = extract_json_object(text)
        assert data['feedback'] == 'use \\frac{1}{2}, not x\\neq 0'

    def test_repair_preserves_real_json_escapes(self) -> None:
        raw = '{"feedback": "line1\\nline2\\tstop"}'
        repaired = repair_json_escapes(raw)
        assert repaired == raw
        data = extract_json_object(raw)
        assert data['feedback'] == 'line1\nline2\tstop'

    def test_extract_trailing_comma_and_latex(self) -> None:
        text = '{\n  "status": "valid",\n  "reason": "HP is [-10/3, \\infty)",\n  "confidence": 0.9,\n}'
        data = extract_json_object(text)
        assert data['status'] == 'valid'
        assert '\\infty' in data['reason'] or 'infty' in data['reason']
        assert data['confidence'] == 0.9

    def test_salvage_reason_with_internal_quotes(self) -> None:
        text = (
            '{\n'
            '  "status": "invalid",\n'
            '  "reason": "Previous HP = [-10/3, oo) vs current "x>1"",\n'
            '  "confidence": 0.96\n'
            '}'
        )
        with pytest.raises(ValueError):
            extract_json_object(text)
        salvaged = salvage_judgement_object(text)
        assert salvaged is not None
        assert salvaged['status'] == 'invalid'
        assert 'x>1' in salvaged['reason']
        assert salvaged['confidence'] == 0.96

    def test_salvage_keeps_latex_neq(self) -> None:
        text = '{"status": "invalid", "reason": "saw x \\\\neq 0 and \\\\theta", "confidence": 0.4}'
        salvaged = salvage_judgement_object(text)
        assert salvaged is not None
        assert salvaged['reason'] == 'saw x \\neq 0 and \\theta'
        assert '\n' not in salvaged['reason']
        assert '\t' not in salvaged['reason']

    def test_repair_keeps_latex_not(self) -> None:
        text = '{"feedback": "x \\not= 0 and \\nmid"}'
        data = extract_json_object(text)
        assert data['feedback'] == 'x \\not= 0 and \\nmid'

    def test_repair_llm_json_syntax_smart_quotes(self) -> None:
        text = '{\n  "status": "valid",\n  "reason": “ok”,\n  "confidence": 0.5,\n}'
        fixed = repair_llm_json_syntax(text)
        data = extract_json_object(fixed)
        assert data['status'] == 'valid'
        assert data['reason'] == 'ok'

class TestRecognitionSchema:

    def test_page_recognition_valid_minimal(self) -> None:
        page = PageRecognition.model_validate({'page_number': 1, 'questions': [{'question_number': 1, 'steps': [{'step_number': 1, 'raw_text': 'x > 0', 'latex': 'x > 0'}], 'final_answer': 'x > 0'}]})
        assert page.page_number == 1
        assert page.questions[0].steps[0].raw_text == 'x > 0'

    def test_page_recognition_with_confidence_and_region(self) -> None:
        page = PageRecognition.model_validate({'page_number': 1, 'questions': [{'question_number': 1, 'region': {'x': 10, 'y': 20, 'width': 100, 'height': 200}, 'steps': [], 'final_answer': '', 'confidence': 0.8}], 'prompt_version': 'recognition-v1', 'model': 'test-model'})
        assert page.questions[0].region is not None
        assert page.questions[0].region.x == 10
        assert page.questions[0].confidence == 0.8
        assert page.model == 'test-model'

    def test_page_recognition_rejects_bad_confidence(self) -> None:
        with pytest.raises(ValidationError):
            PageRecognition.model_validate({'page_number': 1, 'questions': [{'question_number': 1, 'steps': [], 'confidence': 1.5}]})

class TestOllamaClient:

    def test_generate_with_image_success(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == '/api/chat'
            body = json.loads(request.content.decode())
            assert body['model'] == 'vision-test'
            assert body['format'] == 'json'
            assert body['think'] is False
            assert body['stream'] is False
            assert body['messages'][0]['images']
            return httpx.Response(200, json={'message': {'content': '{"page_number": 1, "questions": []}'}})
        transport = httpx.MockTransport(handler)
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=5, max_retries=0, transport=transport)
        content = client.generate_with_image('prompt', _image(tmp_path), 'vision-test')
        assert 'page_number' in content

    def test_generate_falls_back_to_thinking_when_content_empty(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={'message': {'content': '', 'thinking': '{"ok": true}'}, 'done_reason': 'length'})
        transport = httpx.MockTransport(handler)
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=5, max_retries=0, transport=transport)
        content = client.generate_with_image('prompt', _image(tmp_path), 'vision-test')
        assert content == '{"ok": true}'

    def test_generate_retries_on_timeout_then_succeeds(self, tmp_path: Path) -> None:
        calls = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls['n'] += 1
            if calls['n'] == 1:
                raise httpx.ReadTimeout('slow')
            return httpx.Response(200, json={'message': {'content': '{"ok": true}'}})
        transport = httpx.MockTransport(handler)
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=1, max_retries=1, transport=transport)
        content = client.generate_with_image('prompt', _image(tmp_path), 'vision-test')
        assert content == '{"ok": true}'
        assert calls['n'] == 2

    def test_generate_timeout_exhausted(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout('slow')
        transport = httpx.MockTransport(handler)
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=1, max_retries=1, transport=transport)
        with pytest.raises(OllamaTimeoutError):
            client.generate_with_image('prompt', _image(tmp_path), 'vision-test')

    def test_generate_connection_error(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError('offline')
        transport = httpx.MockTransport(handler)
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=1, max_retries=0, transport=transport)
        with pytest.raises(OllamaUnavailableError):
            client.generate_with_image('prompt', _image(tmp_path), 'vision-test')

class TestVisionRecognizer:

    def test_recognizer_writes_artifact(self, tmp_path: Path) -> None:
        from PIL import Image
        from app.models.recognition import DetectedRegion, Region
        from app.services.vision.recognizer import PROMPT_VERSION as PV

        image = tmp_path / 'page_001.png'
        Image.new('RGB', (120, 120), color=(255, 255, 255)).save(image)
        out = tmp_path / 'recognition'
        math = '{"question_number":1,"steps":[{"step_number":1,"raw_text":"x>0","symbolic":{"kind":"relation","repr":"x>0"},"confidence":0.9}],"final_answer":"x>0","final_answer_symbolic":{"kind":"relation","repr":"x>0"},"latex_document":"x>0","confidence":0.9}'
        client = FakeClient([math])

        class FakeProposer:
            def propose(self, image_path, page_number=1):
                return [DetectedRegion(type='solution', region=Region(x=0, y=0, width=50, height=50), question_number=1, order=0)]

        recognizer = OllamaVisionRecognizer(client=client, model='vision-test', output_dir=out, crops_dir=tmp_path / 'crops', proposer=FakeProposer())
        page = recognizer.recognize_page(image, 1)
        assert page.page_number == 1
        assert page.model == 'vision-test'
        assert page.prompt_version == PV
        assert page.questions[0].final_answer == 'x>0'
        assert page.questions[0].region_type == 'solution'
        assert page.questions[0].steps[0].latex == ''
        assert page.questions[0].steps[0].symbolic is not None
        artifact = out / 'page_001_recognition.json'
        assert artifact.is_file()
        assert image.is_file()
        assert (tmp_path / 'crops' / 'page_001' / 'page_001_regions.json').is_file()

    def test_recognizer_invalid_json_keeps_image(self, tmp_path: Path) -> None:
        from PIL import Image
        from app.models.recognition import DetectedRegion, Region

        image = tmp_path / 'page_001.png'
        Image.new('RGB', (40, 40), color=(255, 255, 255)).save(image)
        out = tmp_path / 'recognition'
        client = FakeClient('not json at all')

        class FakeProposer:
            def propose(self, image_path, page_number=1):
                return [DetectedRegion(type='solution', region=Region(x=0, y=0, width=20, height=20), question_number=1, order=0)]

        recognizer = OllamaVisionRecognizer(client=client, model='vision-test', output_dir=out, crops_dir=tmp_path / 'crops', proposer=FakeProposer())
        with pytest.raises(InvalidRecognitionJsonError) as exc_info:
            recognizer.recognize_page(image, 1)
        assert image.is_file()
        assert not (out / 'page_001_recognition.json').exists()
        assert 'response_preview' in str(exc_info.value)
        assert len(client.calls) == 3
        failed = list((tmp_path / 'crops' / 'page_001').glob('*_crop_math_failed.txt'))
        assert len(failed) == 1

    def test_recognizer_retries_then_accepts_valid_json(self, tmp_path: Path) -> None:
        from PIL import Image
        from app.models.recognition import DetectedRegion, Region

        image = tmp_path / 'page_001.png'
        Image.new('RGB', (40, 40), color=(255, 255, 255)).save(image)
        out = tmp_path / 'recognition'
        good = '{"question_number":1,"steps":[],"final_answer":"x>0","confidence":0.9}'
        client = FakeClient(['not json', 'still bad', good])

        class FakeProposer:
            def propose(self, image_path, page_number=1):
                return [DetectedRegion(type='solution', region=Region(x=0, y=0, width=20, height=20), question_number=1, order=0)]

        recognizer = OllamaVisionRecognizer(client=client, model='vision-test', output_dir=out, crops_dir=tmp_path / 'crops', proposer=FakeProposer())
        page = recognizer.recognize_page(image, 1)
        assert page.questions[0].final_answer == 'x>0'
        assert len(client.calls) == 3

    def test_recognizer_requires_model(self, tmp_path: Path) -> None:
        image = tmp_path / 'page_001.png'
        image.write_bytes(b'png')
        recognizer = OllamaVisionRecognizer(client=FakeClient('{}'), model='', output_dir=tmp_path / 'recognition')
        with pytest.raises(OllamaModelNotConfiguredError):
            recognizer.recognize_page(image, 1)

    def test_recognize_pages_rejects_output_dir_mismatch(self, tmp_path: Path) -> None:
        recognizer = MagicMock()
        recognizer.output_dir = tmp_path / 'wrong'
        recognizer.recognize_page.return_value = PageRecognition(page_number=1, questions=[])
        controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
        pages = [Page(page_number=1, image='page_001.png', width=10, height=10)]
        with pytest.raises(RecognitionPathMismatchError):
            controller.recognize_pages(pages, tmp_path / 'pages', tmp_path / 'recognition')

    def test_recognize_pages_allows_matching_output_dir(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        recognizer = MagicMock()
        recognizer.output_dir = recognition_dir
        recognizer.recognize_page.return_value = PageRecognition(page_number=1, questions=[])
        controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
        pages_dir = tmp_path / 'pages'
        pages_dir.mkdir()
        (pages_dir / 'page_001.png').write_bytes(b'x')
        pages = [Page(page_number=1, image='page_001.png', width=10, height=10)]
        result = controller.recognize_pages(pages, pages_dir, recognition_dir)
        assert result.output_dir == recognition_dir
        assert len(result.artifact_paths) == 1

class TestQuestionMergeExtract:

    def test_question_dir_name(self) -> None:
        assert question_dir_name(1) == 'question_001'
        assert question_dir_name(12) == 'question_012'

    def test_merge_single_page(self) -> None:
        pages = [PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=1, region=Region(x=1, y=2, width=3, height=4), steps=[RecognizedStep(step_number=1, raw_text='2x-3<5', latex='2x-3<5', confidence=0.9), RecognizedStep(step_number=2, raw_text='x<4', latex='x<4', confidence=0.8)], final_answer='x<4', confidence=0.85)])]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        q = questions[0]
        assert q.question_id == 'question_001'
        assert q.question_number == 1
        assert q.page_references == [1]
        assert len(q.student_steps) == 2
        assert q.student_steps[0].step_number == 1
        assert q.student_steps[1].raw_text == 'x<4'
        assert q.student_final_answer == 'x<4'
        assert q.segmentation_status == SegmentationStatus.MERGED
        assert q.confidence == 0.8

    def test_merge_multi_page_same_question_number(self) -> None:
        pages = [PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=1, steps=[RecognizedStep(step_number=1, raw_text='start', latex='')], final_answer='')]), PageRecognition(page_number=2, questions=[RecognizedQuestion(question_number=1, steps=[RecognizedStep(step_number=1, raw_text='end', latex='')], final_answer='x < 4')])]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        q = questions[0]
        assert q.page_references == [1, 2]
        assert [s.raw_text for s in q.student_steps] == ['start', 'end']
        assert [s.step_number for s in q.student_steps] == [1, 2]
        assert [s.page_number for s in q.student_steps] == [1, 2]
        assert q.student_final_answer == 'x < 4'
        assert len(q.image_regions) == 2

    def test_merge_two_distinct_questions(self) -> None:
        pages = [PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=2, steps=[RecognizedStep(step_number=1, raw_text='q2', latex='')], final_answer='a2'), RecognizedQuestion(question_number=1, steps=[RecognizedStep(step_number=1, raw_text='q1', latex='')], final_answer='a1')])]
        questions = merge_page_recognitions(pages)
        assert [q.question_id for q in questions] == ['question_001', 'question_002']
        assert questions[0].student_final_answer == 'a1'
        assert questions[1].student_final_answer == 'a2'

    def test_merge_provisional_invalid_number(self) -> None:
        pages = [PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='frag', latex='')], final_answer='?')])]
        questions = merge_page_recognitions(pages)
        assert len(questions) == 1
        assert questions[0].question_number == 1
        assert questions[0].question_id == 'question_001'
        assert questions[0].segmentation_status == SegmentationStatus.PROVISIONAL

    def test_collect_latex_follows_provisional_numbering(self) -> None:
        pages = [PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='a', latex='')], final_answer='a', latex_document='DOC0'), RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='b', latex='')], final_answer='b', latex_document='DOC1')])]
        questions = merge_page_recognitions(pages)
        latex = collect_latex_documents(pages)
        assert [q.question_number for q in questions] == [1, 2]
        assert latex == {1: 'DOC0', 2: 'DOC1'}

    def test_extractor_writes_latex_for_provisional_questions(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        _write_recognition(recognition_dir / 'page_001_recognition.json', PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='x>0', latex='')], final_answer='x>0', latex_document='DOC_A'), RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='x<1', latex='')], final_answer='x<1', latex_document='DOC_B')]))
        output_dir = tmp_path / 'questions'
        QuestionExtractor().extract_from_dir(recognition_dir, output_dir)
        assert (output_dir / 'question_001' / 'latex_source.tex').read_text(encoding='utf-8').strip() == 'DOC_A'
        assert (output_dir / 'question_002' / 'latex_source.tex').read_text(encoding='utf-8').strip() == 'DOC_B'

    def test_extractor_writes_question_json(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        _write_recognition(recognition_dir / 'page_001_recognition.json', PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=1, steps=[RecognizedStep(step_number=1, raw_text='2x<8', latex='2x<8')], final_answer='x<4')], prompt_version='recognition-v1', model='test'))
        output_dir = tmp_path / 'questions'
        result = QuestionExtractor().extract_from_dir(recognition_dir, output_dir)
        assert len(result.questions) == 1
        artifact = output_dir / 'question_001' / 'question.json'
        assert artifact.is_file()
        assert (output_dir / 'question_001' / 'recognition_pages.json').is_file()
        payload = json.loads(artifact.read_text(encoding='utf-8'))
        assert payload['student_final_answer'] == 'x<4'
        assert payload['question_id'] == 'question_001'
        assert result.artifact_paths[0] == artifact

    def test_extractor_missing_recognition_dir(self, tmp_path: Path) -> None:
        with pytest.raises(RecognitionNotFoundError):
            QuestionExtractor().extract_from_dir(tmp_path / 'missing', tmp_path / 'out')

    def test_extractor_empty_questions(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        _write_recognition(recognition_dir / 'page_001_recognition.json', PageRecognition(page_number=1, questions=[]))
        with pytest.raises(EmptyExtractionError):
            QuestionExtractor().extract_from_dir(recognition_dir, tmp_path / 'out')


class TestQuestionSchemaSplit:

    def _mini_schema(self) -> ExamSchema:
        return ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=1,
                    stem=r'$2-3x \le 12$',
                    steps=[r'2-3x \le 12', r'-3x \le 10', r'x \ge -10/3'],
                    final=r'\left[-10/3, \infty\right)',
                ),
                ExamQuestion(
                    number=2,
                    stem=r'$3x-5 < 4x-6$',
                    steps=[r'3x-5 < 4x-6', r'x > 1'],
                    final=r'(1, \infty)',
                ),
            ],
        )

    def _merged_q1_q2(self) -> Question:
        return Question(
            question_id='question_001',
            question_number=1,
            page_references=[1],
            student_steps=[
                StudentStep(step_number=1, raw_text=r'2-3x \le 12', symbolic=SymbolicPayload(kind='relation', repr='2 - 3*x <= 12')),
                StudentStep(step_number=2, raw_text=r'-3x \le 10', symbolic=SymbolicPayload(kind='relation', repr='-3*x <= 10')),
                StudentStep(step_number=3, raw_text=r'x \ge -\frac{10}{3}', symbolic=SymbolicPayload(kind='relation', repr='x >= -10/3')),
                StudentStep(step_number=4, raw_text=r'HP = [-\frac{10}{3}, \infty)', symbolic=SymbolicPayload(kind='expression', repr='HP = [-10/3, oo)')),
                StudentStep(step_number=5, raw_text=r'3x-5 < 4x-6', symbolic=SymbolicPayload(kind='relation', repr='3*x - 5 < 4*x - 6')),
                StudentStep(step_number=6, raw_text=r'-x < -1', symbolic=SymbolicPayload(kind='relation', repr='-x < -1')),
                StudentStep(step_number=7, raw_text=r'x > 1', symbolic=SymbolicPayload(kind='relation', repr='x > 1')),
                StudentStep(step_number=8, raw_text=r'HP = (1, \infty)', symbolic=SymbolicPayload(kind='expression', repr='HP = (1, oo)')),
            ],
            student_final_answer=r'(1, \infty)',
        )

    def test_split_merged_q1_q2(self) -> None:
        merged = self._merged_q1_q2()
        latex = (
            r'\begin{aligned}' + '\n'
            r'1) \quad 2-3x \le 12 \\' + '\n'
            r'x \ge -10/3 \\' + '\n'
            r'2) \quad 3x-5 < 4x-6 \\' + '\n'
            r'x > 1' + '\n'
            r'\end{aligned}'
        )
        questions, latex_map = split_questions_by_exam_schema(
            [merged],
            self._mini_schema(),
            {1: latex},
        )
        assert [q.question_number for q in questions] == [1, 2]
        assert len(questions[0].student_steps) == 4
        assert len(questions[1].student_steps) == 4
        assert '10/3' in (questions[0].student_final_answer or '')
        assert '1' in (questions[1].student_final_answer or '')
        assert 1 in latex_map and 2 in latex_map
        assert '3x-5' in latex_map[2] or '4x-6' in latex_map[2]

    def test_split_noop_without_schema(self) -> None:
        merged = self._merged_q1_q2()
        questions, latex_map = split_questions_by_exam_schema([merged], None, {1: 'tex'})
        assert len(questions) == 1
        assert questions[0].question_number == 1
        assert len(questions[0].student_steps) == 8
        assert latex_map[1] == 'tex'

    def test_split_noop_single_schema_question(self) -> None:
        schema = ExamSchema(
            questions=[ExamQuestion(number=1, stem=r'$2-3x \le 12$', final=r'[-10/3, oo)')],
        )
        merged = self._merged_q1_q2()
        questions, _ = split_questions_by_exam_schema([merged], schema, {})
        assert len(questions) == 1
        assert len(questions[0].student_steps) == 8

    def test_extractor_splits_with_schema(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        page = PageRecognition(
            page_number=1,
            questions=[
                RecognizedQuestion(
                    question_number=1,
                    latex_document=(
                        r'\begin{aligned}' + '\n'
                        r'1) 2-3x \le 12 \\' + '\n'
                        r'2) 3x-5 < 4x-6' + '\n'
                        r'\end{aligned}'
                    ),
                    steps=[
                        RecognizedStep(step_number=1, raw_text=r'2-3x \le 12', symbolic=SymbolicPayload(kind='relation', repr='2-3x <= 12')),
                        RecognizedStep(step_number=2, raw_text=r'HP = [-10/3, oo)', symbolic=SymbolicPayload(kind='expression', repr='HP = [-10/3, oo)')),
                        RecognizedStep(step_number=3, raw_text=r'3x-5 < 4x-6', symbolic=SymbolicPayload(kind='relation', repr='3x-5 < 4x-6')),
                        RecognizedStep(step_number=4, raw_text=r'HP = (1, oo)', symbolic=SymbolicPayload(kind='expression', repr='HP = (1, oo)')),
                    ],
                    final_answer='(1, oo)',
                )
            ],
        )
        _write_recognition(recognition_dir / 'page_001_recognition.json', page)
        output_dir = tmp_path / 'questions'
        result = QuestionExtractor(exam_schema=self._mini_schema()).extract_from_dir(
            recognition_dir, output_dir
        )
        assert [q.question_number for q in result.questions] == [1, 2]
        assert (output_dir / 'question_001' / 'question.json').is_file()
        assert (output_dir / 'question_002' / 'question.json').is_file()
        assert (output_dir / 'question_002' / 'latex_source.tex').is_file()


class TestLatex:

    def test_escape_latex_text(self) -> None:
        assert escape_latex_text('a_b & 50%') == 'a\\_b \\& 50\\%'

    def test_normalize_prefers_symbolic_then_latex(self) -> None:
        step = StudentStep(step_number=1, raw_text='raw', latex='x < 4', symbolic=SymbolicPayload(kind='relation', repr='x < 4'))
        assert normalize_step_latex(step) == 'x < 4'
        step2 = StudentStep(step_number=1, raw_text='raw', latex='x < 4')
        assert normalize_step_latex(step2) == 'x < 4'

    def test_normalize_falls_back_to_escaped_raw(self) -> None:
        step = StudentStep(step_number=1, raw_text='a_b\nc', latex='')
        assert normalize_step_latex(step) == 'a\\_b c'

    def test_format_aligned_line_with_inequality(self) -> None:
        assert format_aligned_line('2x - 3 < 5') == '2x - 3 &< 5'
        assert format_aligned_line('2x = 10') == '2x &= 10'

    def test_strip_final_answer_prefix(self) -> None:
        assert strip_final_answer_prefix('Jawaban akhir: x < 4') == 'x < 4'
        assert strip_final_answer_prefix('final answer - y=1') == 'y=1'

    def test_build_student_latex_aligned(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='...', latex='2x - 3 < 5'), StudentStep(step_number=2, raw_text='...', latex='2x < 8'), StudentStep(step_number=3, raw_text='...', latex='x < 4')], student_final_answer='Jawaban akhir: x < 4')
        tex = build_student_latex(question)
        assert '\\begin{aligned}' in tex
        assert '\\end{aligned}' in tex
        assert '2x - 3 &< 5' in tex
        assert '2x &< 8' in tex
        assert 'x &< 4' in tex
        assert '% final answer' in tex
        assert 'x < 4' in tex
        assert 'Jawaban akhir' not in tex.split('% final answer', 1)[1]

    def test_builder_writes_student_tex_without_mutating_question_json(self, tmp_path: Path) -> None:
        question_dir = tmp_path / 'question_001'
        question_dir.mkdir()
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='keep_me_raw', latex='x < 4')], student_final_answer='x < 4')
        question_path = question_dir / 'question.json'
        original = question.model_dump_json(indent=2)
        question_path.write_text(original, encoding='utf-8')
        result = LatexBuilder().build_dir(tmp_path)
        tex_path = question_dir / 'student.tex'
        assert tex_path.is_file()
        assert result.artifacts[0].path == tex_path
        assert 'x &< 4' in tex_path.read_text(encoding='utf-8')
        assert question_path.read_text(encoding='utf-8') == original
        assert 'keep_me_raw' in question_path.read_text(encoding='utf-8')

    def test_builder_missing_questions(self, tmp_path: Path) -> None:
        with pytest.raises(QuestionsNotFoundError):
            LatexBuilder().build_dir(tmp_path)

class TestMathInequality:

    def test_normalize_strips_ampersand_and_prefix(self) -> None:
        assert normalize_math_text('Jawaban akhir: x &< 4') == 'x < 4'

    def test_parse_equation_and_inequality(self) -> None:
        x = Symbol('x')
        eq = parse_relation('2x+5=15', x)
        assert isinstance(eq, Eq)
        ineq = parse_relation('2x - 3 < 5', x)
        assert isinstance(ineq, Lt)

    def test_parse_rejects_non_relation(self) -> None:
        with pytest.raises(MathParseError):
            parse_relation('just words without operators')

    def test_equivalence_valid_equation_transform(self) -> None:
        x = Symbol('x')
        prev = parse_relation('2x+5=15', x)
        nxt = parse_relation('2x=10', x)
        assert relations_equivalent(prev, nxt, x) is True

    def test_equivalence_invalid_equation_transform(self) -> None:
        x = Symbol('x')
        prev = parse_relation('2x+5=15', x)
        nxt = parse_relation('2x=20', x)
        assert relations_equivalent(prev, nxt, x) is False

    def test_equivalence_inequality_chain(self) -> None:
        x = Symbol('x')
        a = parse_relation('2x-3<5', x)
        b = parse_relation('2x<8', x)
        c = parse_relation('x<4', x)
        assert relations_equivalent(a, b, x) is True
        assert relations_equivalent(b, c, x) is True

    def test_relations_form_equivalent_distinguishes_stages(self) -> None:
        x = Symbol('x')
        early = parse_relation('2-3x<=12', x)
        mid = parse_relation('-3x<=10', x)
        late = parse_relation('x>=-10/3', x)
        assert relations_equivalent(early, late, x) is True
        assert relations_form_equivalent(early, late) is False
        assert relations_form_equivalent(mid, parse_relation('2-3x-2<=12-2', x)) is True
        assert relations_form_equivalent(late, late) is True
        assert relations_form_equivalent(
            parse_relation('x>1', x), parse_relation('1<x', x)
        ) is True
        assert relations_form_equivalent(
            parse_relation('x>1', x), parse_relation('x<1', x)
        ) is False

    def test_parse_abs_forms(self) -> None:
        x = Symbol('x')
        plain = parse_relation('|x|<2', x)
        lvert = parse_relation('\\lvert x\\rvert < 2', x)
        abs_cmd = parse_relation('\\abs{x}<2', x)
        assert 'Abs' in str(plain)
        assert relations_equivalent(plain, lvert, x) is True
        assert relations_equivalent(plain, abs_cmd, x) is True

    def test_equivalence_abs_less_than_compound(self) -> None:
        x = Symbol('x')
        abs_form = parse_relation('|x|<2', x)
        compound = parse_relation('-2<x<2', x)
        assert relations_equivalent(abs_form, compound, x) is True

    def test_equivalence_abs_greater_than_or(self) -> None:
        x = Symbol('x')
        abs_form = parse_relation('|x|>2', x)
        disjunct = parse_relation('x<-2 or x>2', x)
        assert relations_equivalent(abs_form, disjunct, x) is True

    def test_equivalence_abs_shifted_chain(self) -> None:
        x = Symbol('x')
        a = parse_relation('|x-1|<3', x)
        b = parse_relation('-3<x-1<3', x)
        c = parse_relation('-2<x<4', x)
        assert relations_equivalent(a, b, x) is True
        assert relations_equivalent(b, c, x) is True

    def test_interval_membership_equivalent_to_compound(self) -> None:
        x = Symbol('x')
        membership = parse_relation('x \\in (1,3)', x)
        compound = parse_relation('1<x<3', x)
        assert relations_equivalent(membership, compound, x) is True
        closed = parse_relation('x \\in [0,2]', x)
        closed_ineq = parse_relation('0<=x<=2', x)
        assert relations_equivalent(closed, closed_ineq, x) is True

    def test_interval_union_equivalent_to_or(self) -> None:
        x = Symbol('x')
        union = parse_relation('x \\in (-\\infty,1) \\cup (1,\\infty)', x)
        disjunct = parse_relation('x<1 or x>1', x)
        assert relations_equivalent(union, disjunct, x) is True
        bare = parse_relation('(-\\infty,1) \\cup (1,\\infty)', x)
        assert relations_equivalent(bare, disjunct, x) is True

    def test_bare_interval_rewrites_to_inequality(self) -> None:
        x = Symbol('x')
        interval = parse_relation('[-10/3, \\infty)', x)
        ineq = parse_relation('x \\geq -10/3', x)
        assert relations_equivalent(interval, ineq, x) is True

    def test_hp_interval_rewrites_to_inequality(self) -> None:
        import warnings

        x = Symbol('x')
        assert normalize_math_text('HP = (-1/2, 2/3]') == '-1/2 < x <= 2/3'
        assert normalize_math_text('hp = [0,1]') == '0 <= x <= 1'
        assert normalize_math_text('HP=(-10/3, oo)') == '-10/3 < x < oo'

        with warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            hp = parse_relation('HP = (-1/2, 2/3]', x)
            expected = parse_relation('-1/2 < x <= 2/3', x)
            assert relations_equivalent(hp, expected, x) is True
            closed = parse_relation('hp = [0,1]', x)
            assert relations_equivalent(closed, parse_relation('0<=x<=1', x), x) is True

    def test_left_right_interval_and_hp_union(self) -> None:
        import warnings

        x = Symbol('x')
        assert normalize_math_text(r'\left(-1/2, 2/3\right]') == '-1/2 < x <= 2/3'
        assert normalize_math_text(r'HP = \left[-10/3, \infty\right)') == '-10/3 <= x < oo'
        assert normalize_math_text(r'HP = (-4, 0) \cup (2, \infty)') == '-4 < x < 0 or 2 < x < oo'

        with warnings.catch_warnings():
            warnings.simplefilter('error', DeprecationWarning)
            left = parse_relation(r'\left(-1/2, 2/3\right]', x)
            assert relations_equivalent(left, parse_relation('-1/2 < x <= 2/3', x), x) is True
            hp_closed = parse_relation(r'HP = \left[-10/3, \infty\right)', x)
            assert relations_equivalent(hp_closed, parse_relation('x >= -10/3', x), x) is True
            hp_union = parse_relation(r'HP = (-4, 0) \cup (2, \infty)', x)
            expected_union = parse_relation('-4 < x < 0 or 2 < x < oo', x)
            assert relations_equivalent(hp_union, expected_union, x) is True
            std_union = parse_relation(r'(-\infty, -1) \cup \left(1/3, 3\right)', x)
            assert relations_equivalent(
                std_union,
                parse_relation(r'x < -1 or 1/3 < x < 3', x),
                x,
            ) is True

    def test_frac_normalize_preserves_division(self) -> None:
        from sympy import Rational
        from sympy.utilities.exceptions import SymPyDeprecationWarning

        import warnings

        x = Symbol('x')
        assert normalize_math_text(r'-\frac{10}{3}') == '-((10)/(3))'
        assert normalize_math_text(r'\frac{\frac{1}{2}}{3}') == '((((1)/(2)))/(3))'
        assert normalize_math_text(r'\frac{1}{\frac{2}{3}}') == '((1)/(((2)/(3))))'
        assert normalize_math_text(r'\dfrac{1}{2}') == '((1)/(2))'
        assert normalize_math_text(r'HP = \left[-\frac{10}{3}, \infty\right)') == (
            '-((10)/(3)) <= x < oo'
        )

        with warnings.catch_warnings():
            warnings.simplefilter('error', SymPyDeprecationWarning)
            rel = parse_relation(r'x \geq -\frac{10}{3}', x)
            expected = parse_relation(f'x >= -{Rational(10, 3)}', x)
            assert relations_equivalent(rel, expected, x) is True
            hp = parse_relation(r'\left[-\frac{10}{3}, \infty\right)', x)
            assert relations_equivalent(hp, parse_relation(r'x >= -10/3', x), x) is True

    def test_juxtaposed_or_hp_paren_interval_no_sympy_deprecation(self) -> None:
        from sympy.utilities.exceptions import SymPyDeprecationWarning

        import warnings

        from app.services.math.parser import parse_math_step

        x = Symbol('x')
        assert normalize_math_text('HP(1,oo)') == '1 < x < oo'
        assert normalize_math_text(r'(-\infty, 1)(1, \infty)') == (
            '-oo < x < 1 or 1 < x < oo'
        )

        with warnings.catch_warnings():
            warnings.simplefilter('error', SymPyDeprecationWarning)
            hp = parse_relation('HP(1,oo)', x)
            assert relations_equivalent(hp, parse_relation('1 < x < oo', x), x) is True
            juxta = parse_relation(r'(-\infty, 1)(1, \infty)', x)
            expected = parse_relation(r'x < 1 or x > 1', x)
            assert relations_equivalent(juxta, expected, x) is True
            step = parse_math_step('HP(1,oo)', x)
            assert step.kind == 'relation'

    def test_domain_neq_equivalent_to_or(self) -> None:
        x = Symbol('x')
        neq = parse_relation('x \\neq 1', x)
        disjunct = parse_relation('x<1 or x>1', x)
        assert relations_equivalent(neq, disjunct, x) is True

    def test_validator_known_valid_and_invalid_transforms(self) -> None:
        valid_q = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x+5=15'), StudentStep(step_number=2, raw_text='', latex='2x=10'), StudentStep(step_number=3, raw_text='', latex='x=5')], student_final_answer='x=5')
        invalid_q = Question(question_id='question_002', question_number=2, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x+5=15'), StudentStep(step_number=2, raw_text='', latex='2x=20')])
        validator = SymPyStepValidator()
        valid_result = validator.validate_question(valid_q)
        invalid_result = validator.validate_question(invalid_q)
        assert [s.status for s in valid_result.steps] == [ValidationStatus.VALID, ValidationStatus.VALID, ValidationStatus.VALID]
        assert valid_result.final_answer_status is not None
        assert valid_result.final_answer_status.status == ValidationStatus.VALID
        assert invalid_result.steps[1].status == ValidationStatus.INVALID

    def test_validator_inequality_chain(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x-3<5'), StudentStep(step_number=2, raw_text='', latex='2x<8'), StudentStep(step_number=3, raw_text='', latex='x<4')], student_final_answer='Jawaban akhir: x < 4')
        result = SymPyStepValidator().validate_question(question)
        assert all((s.status == ValidationStatus.VALID for s in result.steps))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

    def test_validator_unparseable_is_uncertain(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='lihat gambar', latex='')])
        result = SymPyStepValidator().validate_question(question)
        assert result.steps[0].status == ValidationStatus.UNCERTAIN

    def test_validator_abs_inequality_chain(self) -> None:
        question = Question(question_id='question_002', question_number=2, student_steps=[StudentStep(step_number=1, raw_text='', latex='|x-1|<3'), StudentStep(step_number=2, raw_text='', latex='-3<x-1<3'), StudentStep(step_number=3, raw_text='', latex='-2<x<4')], student_final_answer='-2 < x < 4')
        result = SymPyStepValidator().validate_question(question)
        assert all((s.status == ValidationStatus.VALID for s in result.steps))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

    def test_validator_abs_wrong_transform_is_invalid(self) -> None:
        question = Question(question_id='question_002', question_number=2, student_steps=[StudentStep(step_number=1, raw_text='', latex='|x|<2'), StudentStep(step_number=2, raw_text='', latex='x<2')])
        result = SymPyStepValidator().validate_question(question)
        assert result.steps[0].status == ValidationStatus.VALID
        assert result.steps[1].status == ValidationStatus.INVALID

    def test_validator_abs_greater_than_or_chain(self) -> None:
        question = Question(question_id='question_002', question_number=2, student_steps=[StudentStep(step_number=1, raw_text='', latex='|x|>2'), StudentStep(step_number=2, raw_text='', latex='x<-2 or x>2')], student_final_answer='x < -2 or x > 2')
        result = SymPyStepValidator().validate_question(question)
        assert all((s.status == ValidationStatus.VALID for s in result.steps))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

    def test_validator_domain_inequality_chain(self) -> None:
        question = Question(question_id='question_003', question_number=3, student_steps=[StudentStep(step_number=1, raw_text='', latex='x \\neq 1'), StudentStep(step_number=2, raw_text='', latex='x<1 or x>1')], student_final_answer='x \\in (-\\infty,1) \\cup (1,\\infty)')
        result = SymPyStepValidator().validate_question(question)
        assert all((s.status == ValidationStatus.VALID for s in result.steps))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

    def test_validator_domain_interval_final(self) -> None:
        question = Question(question_id='question_003', question_number=3, student_steps=[StudentStep(step_number=1, raw_text='', latex='x \\in (1,3)'), StudentStep(step_number=2, raw_text='', latex='1<x<3')], student_final_answer='1 < x < 3')
        result = SymPyStepValidator().validate_question(question)
        assert all((s.status == ValidationStatus.VALID for s in result.steps))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

    def test_validator_interval_pair_does_not_crash(self) -> None:
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='', latex='x >= -10/3'),
                StudentStep(step_number=2, raw_text='', latex='Interval(-10/3, oo)'),
            ],
            student_final_answer='Interval(-10/3, oo)',
        )
        result = SymPyStepValidator().validate_question(question)
        assert result.steps[0].status == ValidationStatus.VALID
        assert result.steps[1].status == ValidationStatus.VALID
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.VALID

class TestLlmHybrid:

    def test_hybrid_preserves_llm_uncertain(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='lihat gambar', latex='')])
        judge = RecordingJudge({'status': 'uncertain', 'reason': 'unclear', 'confidence': 0.3})
        result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(question)
        assert result.steps[0].status == ValidationStatus.UNCERTAIN
        assert result.steps[0].method == ValidationMethod.LLM
        assert judge.calls

    def test_hybrid_llm_can_mark_valid_when_sympy_uncertain(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='not parseable', latex='')])
        judge = RecordingJudge({'status': 'valid', 'reason': 'looks ok', 'confidence': 0.7})
        result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(question)
        assert result.steps[0].status == ValidationStatus.VALID
        assert result.steps[0].method == ValidationMethod.LLM

    def test_hybrid_does_not_overwrite_sympy_invalid(self) -> None:
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x+5=15'), StudentStep(step_number=2, raw_text='', latex='2x=20')])
        judge = RecordingJudge({'status': 'valid', 'reason': 'should not be used', 'confidence': 0.9})
        result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(question)
        assert result.steps[1].status == ValidationStatus.INVALID
        assert result.steps[1].method == ValidationMethod.SYMPY
        assert judge.calls == []

    def test_llm_judge_invalid_json_stays_uncertain(self, tmp_path: Path) -> None:
        prompt = tmp_path / 'validation.txt'
        prompt.write_text('prev={{previous_step}}\ncur={{current_step}}\nextra={{extra_context}}', encoding='utf-8')

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={'message': {'content': 'not-json'}})
        client = OllamaClient(base_url='http://ollama.test', timeout_seconds=5, max_retries=0, transport=httpx.MockTransport(handler))
        judge = LlmStepJudge(client=client, model='reason-test', prompt_path=prompt)
        step = StudentStep(step_number=2, raw_text='??', latex='')
        result = judge.judge_transition(step_number=2, previous=StudentStep(step_number=1, raw_text='a', latex='a'), current=step)
        assert result.status == ValidationStatus.UNCERTAIN
        assert result.method == ValidationMethod.LLM

    def test_llm_judge_salvages_broken_reason_quotes(self, tmp_path: Path) -> None:
        prompt = tmp_path / 'validation.txt'
        prompt.write_text(
            'prev={{previous_step}}\ncur={{current_step}}\nextra={{extra_context}}',
            encoding='utf-8',
        )
        broken = (
            '{\n'
            '  "status": "invalid",\n'
            '  "reason": "set [-10/3, oo) became "x>1" incorrectly",\n'
            '  "confidence": 0.91\n'
            '}'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={'message': {'content': broken}})

        client = OllamaClient(
            base_url='http://ollama.test',
            timeout_seconds=5,
            max_retries=0,
            transport=httpx.MockTransport(handler),
        )
        judge = LlmStepJudge(client=client, model='reason-test', prompt_path=prompt)
        result = judge.judge_transition(
            step_number=2,
            previous=StudentStep(step_number=1, raw_text='a', latex='a'),
            current=StudentStep(step_number=2, raw_text='b', latex='b'),
        )
        assert result.status == ValidationStatus.INVALID
        assert result.method == ValidationMethod.LLM
        assert 'x>1' in result.reason
        assert result.confidence == pytest.approx(0.91)

    def test_ollama_generate_text_only(self) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert 'images' not in body['messages'][0]
            return httpx.Response(200, json={'message': {'content': '{"status":"uncertain","reason":"r","confidence":0.5}'}})
        client = OllamaClient(base_url='http://ollama.test', max_retries=0, transport=httpx.MockTransport(handler))
        content = client.generate('prompt', 'reason-test')
        assert 'uncertain' in content

class TestGrading:

    def test_allocate_step_max_scores_uses_student_count_only(self) -> None:
        rubric = _sample_rubric()
        # Non-final pool = 2+4+2 = 8; five student steps get full pool.
        per_step, final_max, part_max = allocate_step_max_scores(rubric, 5)
        assert final_max == pytest.approx(2.0)
        assert part_max == {}
        assert len(per_step) == 5
        assert sum(per_step) == pytest.approx(8.0)

        validation = QuestionValidation(
            question_number=1,
            question_id='question_001',
            steps=[_step(i, ValidationStatus.VALID) for i in range(1, 6)],
            final_answer_status=_step(0, ValidationStatus.VALID),
        )
        grade = aggregate_question_grade(
            question_id='question_001',
            question_number=1,
            validation=validation,
            rubric=rubric,
        )
        assert grade.score == pytest.approx(10.0)
        assert sum(s.max_score for s in grade.steps) == pytest.approx(8.0)

    def test_aggregate_full_credit(self) -> None:
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID), _step(3, ValidationStatus.VALID), _step(4, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        grade = aggregate_question_grade(question_id='question_001', question_number=1, validation=validation, rubric=_sample_rubric())
        assert grade.score == pytest.approx(10.0)
        assert grade.maximum_score == 10
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT
        assert all((s.score == pytest.approx(2.0) for s in grade.steps))
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(2.0)

    def test_aggregate_partial_credit_not_zero_total(self) -> None:
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.INVALID, 'algebra error'), _step(3, ValidationStatus.VALID), _step(4, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.INVALID, 'wrong answer'))
        grade = aggregate_question_grade(question_id='question_001', question_number=1, validation=validation, rubric=_sample_rubric())
        assert grade.score == pytest.approx(6.0)
        assert 0 < grade.score < grade.maximum_score
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT
        assert grade.steps[2].error_type.value == 'carry_forward'

    def test_aggregate_uncertain_requires_review(self) -> None:
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.UNCERTAIN, 'ambiguous'), _step(3, ValidationStatus.VALID), _step(4, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        grade = aggregate_question_grade(question_id='question_001', question_number=1, validation=validation, rubric=_sample_rubric())
        assert grade.score == pytest.approx(9.0)
        assert grade.review_status == ReviewStatus.REVIEW_REQUIRED
        assert grade.steps[1].status.value == 'review'

    def test_aggregate_standard_only_final_no_fake_full_consistency(self) -> None:
        validation = QuestionValidation(
            question_number=1,
            question_id='question_001',
            steps=[_step(1, ValidationStatus.VALID)],
            final_answer_status=None,
        )
        grade = aggregate_question_grade(
            question_id='question_001',
            question_number=1,
            validation=validation,
            rubric=_sample_rubric(),
            standard_final_status=ValidationStatus.VALID,
            standard_final_reason='matches',
        )
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(2.0)
        assert 'standard compare only' in grade.final_answer.feedback

    def test_step_grader_writes_grading_json_without_mutating_question(self, tmp_path: Path) -> None:
        standard = tmp_path / 'standards' / 'exam_001'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'rubrics' / 'question_001.json').write_text(_sample_rubric().model_dump_json(indent=2), encoding='utf-8')
        qdir = tmp_path / 'questions' / 'question_001'
        qdir.mkdir(parents=True)
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='keep', latex='x-4<0'), StudentStep(step_number=2, raw_text='keep', latex='x<4')], student_final_answer='x<4')
        qpath = qdir / 'question.json'
        original = question.model_dump_json(indent=2)
        qpath.write_text(original, encoding='utf-8')
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        (qdir / 'validation.json').write_text(validation.model_dump_json(indent=2), encoding='utf-8')
        grader = StepGrader(RubricLoader(standard))
        grade = GradeController(grader, standard).grade(tmp_path / 'questions')
        assert (qdir / 'grading.json').is_file()
        assert grade.grades[0].score == pytest.approx(10.0)
        assert qpath.read_text(encoding='utf-8') == original
        assert 'keep' in qpath.read_text(encoding='utf-8')

    def test_step_grader_missing_validation_errors(self, tmp_path: Path) -> None:
        standard = tmp_path / 'standards' / 'exam_001'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'rubrics' / 'question_001.json').write_text(_sample_rubric().model_dump_json(indent=2), encoding='utf-8')
        qdir = tmp_path / 'questions' / 'question_001'
        qdir.mkdir(parents=True)
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='x<4')])
        (qdir / 'question.json').write_text(question.model_dump_json(indent=2), encoding='utf-8')
        with pytest.raises(ValidationNotFoundError):
            GradeController(StepGrader(RubricLoader(standard)), standard).grade(tmp_path / 'questions')

    def test_extract_final_answer_from_tex(self) -> None:
        tex = '% header\n\\begin{aligned}\nx &< 4\n\\end{aligned}\n\n% final answer\nx < 4\n'
        assert extract_final_answer_from_tex(tex) == 'x < 4'
        assert extract_final_answer_from_tex('no marker here') is None

    def test_extract_solution_steps_from_tex_q001(self) -> None:
        tex = Path('data/output/standards/exam_001/solutions/question_001.tex').read_text(encoding='utf-8')
        steps = extract_solution_steps_from_tex(tex)
        assert len(steps) >= 2
        assert '3x' in steps[0].replace(' ', '')
        assert '12' in steps[0]
        assert 'x' in steps[-1] and '10' in steps[-1]

    def test_extract_solution_steps_ignores_final_answer_section(self) -> None:
        tex = '\\begin{aligned}\nx &< 4 \\\\\n\\end{aligned}\n\n% final answer\nx < 4\n'
        steps = extract_solution_steps_from_tex(tex)
        assert steps == ['x < 4']

    def test_standard_solution_path(self) -> None:
        path = standard_solution_path(Path('data/output/standards/exam_001'), 1)
        assert path.as_posix().endswith('solutions/question_001.tex')

    def test_comparer_match_q1_repo_standard(self) -> None:
        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='', latex=r'2-3x\leq12'),
                StudentStep(step_number=2, raw_text='', latex=r'x\geq-\frac{10}{3}'),
            ],
            student_final_answer=r'\left[-\frac{10}{3}, \infty\right)',
        )
        result = StandardFinalComparer(standard).compare(question)
        assert result is not None
        status, reason = result
        assert status == ValidationStatus.VALID
        assert 'matches' in reason

    def test_comparer_interval_symbolic_vs_schema(self) -> None:
        from app.models.recognition import SymbolicPayload

        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_final_symbolic=SymbolicPayload(
                kind='expression',
                repr='Interval(-10/3, oo)',
            ),
            student_final_answer='HP',
        )
        result = StandardFinalComparer(standard).compare(question)
        assert result is not None
        assert result[0] == ValidationStatus.VALID

    def test_comparer_interval_open_differs(self) -> None:
        from app.models.recognition import SymbolicPayload

        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_final_symbolic=SymbolicPayload(
                kind='expression',
                repr='Interval(-10/3, oo, left_open=True)',
            ),
        )
        result = StandardFinalComparer(standard).compare(question)
        assert result is not None
        assert result[0] != ValidationStatus.UNCERTAIN
        assert result[0] == ValidationStatus.INVALID

    def test_match_schema_prefers_symbolic(self) -> None:
        from app.functions.question_split import match_schema_final, match_schema_stem
        from app.models.recognition import SymbolicPayload

        q = ExamQuestion(
            number=1,
            stem='ignored latex',
            stem_symbolic=SymbolicPayload(kind='relation', repr='2-3*x <= 12'),
            final='ignored',
            final_symbolic=SymbolicPayload(
                kind='relation',
                repr='-((10)/(3)) <= x < oo',
            ),
        )
        assert match_schema_stem('2-3x <= 12', q)
        assert match_schema_final('-((10)/(3)) <= x < oo', q)
        assert not match_schema_stem('x > 99', q)
        # Substring must not equate x>1 with x>10
        short = ExamQuestion(
            number=2,
            stem='s',
            final='x>10',
            final_symbolic=SymbolicPayload(kind='relation', repr='x>10'),
        )
        assert not match_schema_final('x>1', short)

    def test_standard_step_texts_prefer_symbolic(self) -> None:
        from app.functions.standard_extract import standard_step_texts
        from app.models.recognition import SymbolicPayload

        q = ExamQuestion(
            number=1,
            stem='$x>0$',
            steps=[r'x > 0', r'\text{skip}'],
            steps_symbolic=[
                SymbolicPayload(kind='relation', repr='x > 0'),
                None,
            ],
            final='(0, oo)',
        )
        tex = r'\begin{aligned}x &> 1 \\ x &> 2\end{aligned}'
        texts = standard_step_texts(q, tex)
        assert texts[0] == 'x > 0'
        assert texts[1] == 'x > 2' or 'x > 1' in texts[1] or texts[1].startswith('x')

        gapped = ExamQuestion(
            number=3,
            stem='s',
            steps=['x>0', '', 'x>2'],
            steps_symbolic=[
                SymbolicPayload(kind='relation', repr='x>0'),
                None,
                SymbolicPayload(kind='relation', repr='x>2'),
            ],
        )
        gapped_texts = standard_step_texts(gapped, None)
        assert gapped_texts == ['x>0', '', 'x>2']

    def test_comparer_mismatch_invalid(self) -> None:
        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[StudentStep(step_number=1, raw_text='', latex='x<5')],
            student_final_answer='x < 5',
        )
        result = StandardFinalComparer(standard).compare(question)
        assert result is not None
        assert result[0] == ValidationStatus.INVALID

    def test_comparer_missing_solution_returns_none(self, tmp_path: Path) -> None:
        standard = tmp_path / 'exam'
        (standard / 'solutions').mkdir(parents=True)
        question = Question(question_id='question_001', question_number=1, student_final_answer='x<4')
        assert StandardFinalComparer(standard).compare(question) is None
        assert StandardFinalComparer(standard).compare_steps(question) is None

    def test_compare_steps_match_q001_order(self) -> None:
        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='', latex=r'2-3x\leq12'),
                StudentStep(step_number=2, raw_text='', latex=r'2-3x-2\leq12-2'),
                StudentStep(step_number=3, raw_text='', latex=r'-3x\leq10'),
            ],
            student_final_answer=r'\left[-\frac{10}{3}, \infty\right)',
        )
        results = StandardFinalComparer(standard).compare_steps(question)
        assert results is not None
        assert results[1][0] == ValidationStatus.VALID
        assert results[2][0] == ValidationStatus.VALID
        assert results[3][0] == ValidationStatus.VALID

    def test_compare_steps_mismatch_invalid(self) -> None:
        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='', latex=r'2-3x\leq12'),
                StudentStep(step_number=2, raw_text='', latex=r'-3x\leq11'),
                StudentStep(step_number=3, raw_text='', latex=r'-3x\leq10'),
            ],
        )
        results = StandardFinalComparer(standard).compare_steps(question)
        assert results is not None
        assert results[1][0] == ValidationStatus.VALID
        assert results[2][0] == ValidationStatus.INVALID
        assert 'no matching standard step' in results[2][1]
        assert results[3][0] == ValidationStatus.VALID
        # -3x≤10 is equivalent to key step 2 (2-3x-2≤12-2) after soft-align cursor
        assert 'standard step 2' in results[3][1]

    def test_compare_steps_skips_to_later_standard(self) -> None:
        """Student may jump to a later key step (not index-aligned)."""
        standard = Path('data/output/standards/exam_001')
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='', latex=r'2-3x\leq12'),
                StudentStep(step_number=2, raw_text='', latex=r'x\geq -\frac{10}{3}'),
            ],
        )
        results = StandardFinalComparer(standard).compare_steps(question)
        assert results is not None
        assert results[1][0] == ValidationStatus.VALID
        assert results[2][0] == ValidationStatus.VALID
        # Key steps 4–5 are the ÷(-1/3) / x≥-10/3 forms; sequential index
        # align would have compared student step 2 to key step 2 (Invalid).
        assert 'standard step 4' in results[2][1] or 'standard step 5' in results[2][1]
        assert 'standard step 2' not in results[2][1]

    def test_align_student_steps_noncontiguous(self) -> None:
        aligned = align_student_steps_to_standard(
            [
                (1, [True, False, True]),
                (2, [True, False, True]),
            ]
        )
        assert aligned[1] == (ValidationStatus.VALID, 'step matches standard step 1')
        assert aligned[2] == (ValidationStatus.VALID, 'step matches standard step 3')

    def test_align_student_steps_no_double_claim(self) -> None:
        aligned = align_student_steps_to_standard(
            [
                (1, [True, False]),
                (2, [True, False]),
            ]
        )
        assert aligned[1][0] == ValidationStatus.VALID
        assert aligned[2][0] == ValidationStatus.INVALID
        assert 'no matching standard step' in aligned[2][1]

    def test_align_student_steps_figure_skip_does_not_consume(self) -> None:
        aligned = align_student_steps_to_standard(
            [
                (1, None),
                (2, [True, False]),
            ],
            skip_reasons={1: 'figure step skipped for standard align'},
        )
        assert aligned[1][0] == ValidationStatus.UNCERTAIN
        assert aligned[2] == (ValidationStatus.VALID, 'step matches standard step 1')

    def test_align_student_steps_empty_input(self) -> None:
        assert align_student_steps_to_standard([]) == {}

    def test_aggregate_standard_step_mismatch_keeps_consistency_credit(self) -> None:
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID), _step(3, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        grade = aggregate_question_grade(question_id='question_001', question_number=1, validation=validation, rubric=_sample_rubric(), standard_final_status=ValidationStatus.VALID, standard_final_reason='matches', standard_step_results={1: (ValidationStatus.VALID, 'step matches standard'), 2: (ValidationStatus.INVALID, 'step differs from standard'), 3: (ValidationStatus.VALID, 'step matches standard')})
        # Soft-align mismatch is audit-only; consistency VALID still earns full step credit.
        assert grade.steps[1].score == pytest.approx(grade.steps[0].score)
        assert 'standard:' in grade.steps[1].feedback
        assert grade.standard_step_statuses == {'1': 'valid', '2': 'invalid', '3': 'valid'}
        assert grade.score == pytest.approx(10.0)
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT

    def test_aggregate_unaligned_step_keeps_consistency_credit(self) -> None:
        validation = QuestionValidation(
            question_number=1,
            question_id='question_001',
            steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID)],
            final_answer_status=_step(0, ValidationStatus.VALID),
        )
        grade = aggregate_question_grade(
            question_id='question_001',
            question_number=1,
            validation=validation,
            rubric=_sample_rubric(),
            standard_step_results={1: (ValidationStatus.VALID, 'step matches standard')},
        )
        assert grade.steps[1].score == pytest.approx(grade.steps[0].score)
        assert 'no matching standard step' in grade.steps[1].feedback
        assert grade.standard_step_statuses == {'1': 'valid', '2': 'invalid'}

    def test_comparer_prose_uncertain(self, tmp_path: Path) -> None:
        standard = tmp_path / 'exam'
        sol = standard / 'solutions'
        sol.mkdir(parents=True)
        (sol / 'question_001.tex').write_text('% final answer\nf kontinu di a\n', encoding='utf-8')
        question = Question(question_id='question_001', question_number=1, student_final_answer='f kontinu di a')
        result = StandardFinalComparer(standard).compare(question)
        assert result is not None
        assert result[0] == ValidationStatus.UNCERTAIN

    def test_aggregate_standard_mismatch_zeros_final_only(self) -> None:
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID), _step(3, ValidationStatus.VALID), _step(4, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        grade = aggregate_question_grade(question_id='question_001', question_number=1, validation=validation, rubric=_sample_rubric(), standard_final_status=ValidationStatus.INVALID, standard_final_reason='differs from standard')
        assert grade.score == pytest.approx(8.0)
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(0.0)
        assert grade.standard_final_status == ValidationStatus.INVALID
        assert 'standard:' in grade.final_answer.feedback

    def test_part_scoring_critical_points_and_figure(self) -> None:
        from app.models.grading import Rubric, RubricCriterion

        rubric = Rubric(
            question=4,
            maximum_score=10,
            criteria=[
                RubricCriterion(id='algebra', points=3),
                RubricCriterion(id='critical_points', points=2),
                RubricCriterion(id='figure', points=2),
                RubricCriterion(id='final_answer', points=3),
            ],
        )
        validation = QuestionValidation(
            question_number=4,
            question_id='question_004',
            steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID)],
            final_answer_status=_step(0, ValidationStatus.VALID),
        )
        grade = aggregate_question_grade(
            question_id='question_004',
            question_number=4,
            validation=validation,
            rubric=rubric,
            standard_final_status=ValidationStatus.VALID,
            part_statuses={
                'critical_points': (ValidationStatus.VALID, 'matches milestone'),
                'figure': (ValidationStatus.VALID, 'figure step present'),
            },
        )
        assert grade.score == pytest.approx(10.0)
        part_feedback = ' '.join(s.feedback for s in grade.steps)
        assert 'part:critical_points' in part_feedback
        assert 'part:figure' in part_feedback

        miss = aggregate_question_grade(
            question_id='question_004',
            question_number=4,
            validation=validation,
            rubric=rubric,
            standard_final_status=ValidationStatus.VALID,
            part_statuses={
                'critical_points': (ValidationStatus.INVALID, 'no match'),
                'figure': (ValidationStatus.INVALID, 'no figure step'),
            },
        )
        # algebra 3 + final 3 = 6; critical/figure zeroed
        assert miss.score == pytest.approx(6.0)

        partial = aggregate_question_grade(
            question_id='question_004',
            question_number=4,
            validation=validation,
            rubric=rubric,
            standard_final_status=ValidationStatus.VALID,
            part_statuses={
                'critical_points': (
                    ValidationStatus.INVALID,
                    'matches 1/3 of milestone critical_points',
                    1 / 3,
                ),
                'figure': (ValidationStatus.VALID, 'figure step present'),
            },
        )
        # algebra 3 + critical 2*(1/3) rounded + figure 2 + final 3
        assert partial.score == pytest.approx(8.6667, abs=1e-4)

    def test_milestone_coverage_and_figure_role_skip(self, tmp_path: Path) -> None:
        from app.models.exam_schema import ExamMilestone
        from app.models.recognition import SymbolicPayload

        schema = ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=1,
                    stem='s',
                    steps=['x > 1'],
                    steps_symbolic=[
                        SymbolicPayload(kind='relation', repr='x > 1'),
                    ],
                    milestones=[
                        ExamMilestone(
                            role='critical_points',
                            steps=['x = 0', 'x = 1', 'x = 2'],
                        ),
                        ExamMilestone(
                            role='sign_chart',
                            steps=['x < 0'],
                        ),
                    ],
                )
            ],
        )
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(
                    step_number=1,
                    raw_text='x>1',
                    role='figure',
                    symbolic=SymbolicPayload(kind='relation', repr='x > 1'),
                ),
                StudentStep(
                    step_number=2,
                    raw_text='x=0',
                    role='critical_points',
                    symbolic=SymbolicPayload(kind='relation', repr='x = 0'),
                ),
            ],
        )
        comparer = StandardFinalComparer(tmp_path, exam_schema=schema)
        aligned = comparer.compare_steps(question)
        assert aligned is not None
        assert aligned[1][0] == ValidationStatus.UNCERTAIN
        assert 'figure' in aligned[1][1]
        marks = comparer.compare_milestones(question)
        status, reason, fraction = marks['critical_points']
        assert status != ValidationStatus.VALID
        # one of three roots, and the sign-chart atom misses: mean of 1/3 and 0
        assert fraction == pytest.approx((1 / 3 + 0) / 2)
        assert '1/3' in reason

        covered = question.model_copy(
            update={
                'student_steps': [
                    StudentStep(
                        step_number=1,
                        raw_text='x=0',
                        symbolic=SymbolicPayload(kind='relation', repr='x = 0'),
                    ),
                    StudentStep(
                        step_number=2,
                        raw_text='x=1',
                        symbolic=SymbolicPayload(kind='relation', repr='x = 1'),
                    ),
                    StudentStep(
                        step_number=3,
                        raw_text='x=2',
                        symbolic=SymbolicPayload(kind='relation', repr='x = 2'),
                    ),
                    StudentStep(
                        step_number=4,
                        raw_text='x<0',
                        symbolic=SymbolicPayload(kind='relation', repr='x < 0'),
                    ),
                ]
            }
        )
        full = comparer.compare_milestones(covered)
        assert full['critical_points'][0] == ValidationStatus.VALID
        assert full['critical_points'][2] == pytest.approx(1.0)

    def test_compare_steps_none_without_algebra_bank(self, tmp_path: Path) -> None:
        schema = ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=1,
                    stem='s',
                    final='x>1',
                )
            ],
        )
        question = Question(
            question_id='question_001',
            question_number=1,
            student_steps=[
                StudentStep(step_number=1, raw_text='x>0', latex='x>0'),
            ],
        )
        assert (
            StandardFinalComparer(tmp_path, exam_schema=schema).compare_steps(question)
            is None
        )

    def test_build_exam_question_without_hp_has_empty_final(self) -> None:
        tex = r'''
\begin{enumerate}
\item $x>0$
\begin{align}
x &> 0 \\
x &> 1
\end{align}
\end{enumerate}
'''
        schema = build_exam_schema(tex, source='no-hp')
        assert schema.questions[0].final == ''
        assert schema.questions[0].final_symbolic is None

    def test_best_method_align_prefers_quadratic_bank(self, tmp_path: Path) -> None:
        from app.models.exam_schema import (
            ExamMethod,
            ExamQuestion,
            ExamSchema,
        )
        from app.models.question import StudentStep
        from app.models.recognition import SymbolicPayload

        schema = ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=4,
                    stem='2x^2-5x-3<0',
                    steps=['2*x**2 - 5*x - 3 < 0'],
                    steps_symbolic=[
                        SymbolicPayload(
                            kind='relation', repr='2*x**2 - 5*x - 3 < 0'
                        )
                    ],
                    methods=[
                        ExamMethod(
                            id='factoring',
                            label='Pemaktoran',
                            steps=['(2*x + 1)*(x - 3) = 0'],
                            steps_symbolic=[
                                SymbolicPayload(
                                    kind='relation',
                                    repr='(2*x + 1)*(x - 3) = 0',
                                )
                            ],
                        ),
                        ExamMethod(
                            id='quadratic_formula',
                            label='Rumus ABC',
                            steps=['x = (-b + sqrt(b**2 - 4*a*c))/(2*a)'],
                            steps_symbolic=[
                                SymbolicPayload(
                                    kind='relation',
                                    repr='x = (5 + 7)/4',
                                )
                            ],
                        ),
                    ],
                    final='(-1/2, 3)',
                )
            ],
        )
        standard = tmp_path / 'exam'
        standard.mkdir()
        (standard / 'exam_schema.json').write_text(
            schema.model_dump_json(indent=2), encoding='utf-8'
        )
        question = Question(
            question_id='question_004',
            question_number=4,
            student_steps=[
                StudentStep(
                    step_number=1,
                    raw_text='2x^2-5x-3<0',
                    symbolic=SymbolicPayload(
                        kind='relation', repr='2*x**2 - 5*x - 3 < 0'
                    ),
                ),
                StudentStep(
                    step_number=2,
                    raw_text='x=(5+7)/4',
                    symbolic=SymbolicPayload(
                        kind='relation', repr='x = (5 + 7)/4'
                    ),
                ),
            ],
        )
        aligned = StandardFinalComparer(standard, exam_schema=schema).compare_steps(
            question
        )
        assert aligned is not None
        assert aligned[1][0] == ValidationStatus.VALID
        assert aligned[2][0] == ValidationStatus.VALID
        assert 'quadratic_formula' in aligned[2][1]

    def test_step_grader_with_standard_match(self, tmp_path: Path) -> None:
        standard = tmp_path / 'standards' / 'exam_001'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'solutions').mkdir(parents=True)
        (standard / 'rubrics' / 'question_001.json').write_text(_sample_rubric().model_dump_json(indent=2), encoding='utf-8')
        (standard / 'solutions' / 'question_001.tex').write_text('% final answer\nx < 4\n', encoding='utf-8')
        qdir = tmp_path / 'questions' / 'question_001'
        qdir.mkdir(parents=True)
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x-3<5'), StudentStep(step_number=2, raw_text='', latex='x<4')], student_final_answer='x<4')
        (qdir / 'question.json').write_text(question.model_dump_json(indent=2), encoding='utf-8')
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        (qdir / 'validation.json').write_text(validation.model_dump_json(indent=2), encoding='utf-8')
        grader = StepGrader(RubricLoader(standard), standard_comparer=StandardFinalComparer(standard))
        grade = GradeController(grader, standard).grade(tmp_path / 'questions')
        assert grade.grades[0].score == pytest.approx(10.0)
        assert grade.grades[0].standard_final_status == ValidationStatus.VALID

    def test_step_grader_with_standard_mismatch(self, tmp_path: Path) -> None:
        standard = tmp_path / 'standards' / 'exam_001'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'solutions').mkdir(parents=True)
        (standard / 'rubrics' / 'question_001.json').write_text(_sample_rubric().model_dump_json(indent=2), encoding='utf-8')
        (standard / 'solutions' / 'question_001.tex').write_text('% final answer\nx < 4\n', encoding='utf-8')
        qdir = tmp_path / 'questions' / 'question_001'
        qdir.mkdir(parents=True)
        question = Question(question_id='question_001', question_number=1, student_steps=[StudentStep(step_number=1, raw_text='', latex='2x-3<5'), StudentStep(step_number=2, raw_text='', latex='x<4')], student_final_answer='x<5')
        (qdir / 'question.json').write_text(question.model_dump_json(indent=2), encoding='utf-8')
        validation = QuestionValidation(question_number=1, question_id='question_001', steps=[_step(1, ValidationStatus.VALID), _step(2, ValidationStatus.VALID)], final_answer_status=_step(0, ValidationStatus.VALID))
        (qdir / 'validation.json').write_text(validation.model_dump_json(indent=2), encoding='utf-8')
        grader = StepGrader(RubricLoader(standard), standard_comparer=StandardFinalComparer(standard))
        grade = GradeController(grader, standard).grade(tmp_path / 'questions')
        g = grade.grades[0]
        assert g.standard_final_status == ValidationStatus.INVALID
        assert g.final_answer is not None
        assert g.final_answer.score == pytest.approx(0.0)
        assert g.score == pytest.approx(8.0)

class TestKunciIngest:

    def test_extract_question_stems_mini(self) -> None:
        stems = extract_question_stems(_MINI_KUNCI)
        assert len(stems) == 2
        assert stems[0][0] == 1 and '2-3x' in stems[0][1]
        assert stems[1][0] == 2 and '3x-5' in stems[1][1]
        for _, stem in stems:
            assert 'HP' not in stem
            assert 'align' not in stem.lower()
            assert 'Penyelesaian' not in stem

    def test_load_question_stems_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / 'empty_kunci'
        empty.mkdir()
        assert load_question_stems_from_kunci(empty) == []
        assert load_question_stems_from_kunci(tmp_path / 'missing') == []

    def test_load_question_stems_from_file(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci.tex'
        kunci.write_text(_MINI_KUNCI, encoding='utf-8')
        stems = load_question_stems_from_kunci(kunci)
        assert len(stems) == 2
        assert stems[0][0] == 1
        assert '2-3x' in stems[0][1]

    def test_repo_stems_no_hp_leak(self) -> None:
        path = Path('data/input/kunci_jawaban/jawaban_tugas_1.tex')
        stems = extract_question_stems(path.read_text(encoding='utf-8'))
        assert len(stems) >= 6
        assert '2-3x' in stems[0][1]
        joined = ' '.join(s for _, s in stems)
        assert 'infty' not in joined.lower()
        assert 'Penyelesaian' not in joined

    def test_build_exam_schema_mini_no_tikz(self) -> None:
        schema = build_exam_schema(_MINI_KUNCI, source='mini')
        assert schema.source == 'mini'
        assert len(schema.questions) == 2
        q1 = schema.questions[0]
        assert q1.expects_figure is False
        assert 'figure' not in {p.kind for p in q1.parts}
        assert 'algebra' in {p.kind for p in q1.parts}
        assert 'hp' in {p.kind for p in q1.parts}
        assert 'HP' not in q1.stem
        assert q1.stem_symbolic is not None
        assert q1.stem_symbolic.kind == 'relation'
        assert '<=' in q1.stem_symbolic.repr
        assert '*' in q1.stem_symbolic.repr or '3x' in q1.stem_symbolic.repr.replace(' ', '')
        assert q1.final_symbolic is not None
        assert 'oo' in q1.final_symbolic.repr
        assert len(q1.steps_symbolic) == len(q1.steps)
        assert all(s is not None for s in q1.steps_symbolic)
        block = format_recognition_question_block(schema)
        assert '2-3x' in block
        assert 'expects_figure' not in block
        assert 'infty' not in block.lower()

    def test_multi_method_schema_and_rubric(self) -> None:
        from app.functions.kunci_ingest import rubric_from_parts

        multi = r'''
\begin{enumerate}
\item $2x^{2}-5x-3 < 0$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah-langkah Penyelesaian
\begin{align}
2x^2 - 5x - 3 &< 0 \\
\text{Cari akar-akar persamaan } 2x^2 - 5x - 3 &= 0
\end{align}
\item Metode 1: Pemaktoran
\begin{align}
(2x + 1)(x - 3) &= 0 \\
x &= -\frac{1}{2}
\end{align}
\item Metode 2: Rumus ABC
\begin{align}
x_1,x_2 &= \frac{-b \pm \sqrt{b^2 - 4ac}}{2a} \\
x_1 &= 3
\end{align}
\item Analisis Tanda
\begin{align}
\text{Selang } x < -\frac{1}{2}: \quad & 4 > 0
\end{align}
\item Gambar Garis Bilangan
\begin{center}
\begin{tikzpicture}
\draw (0,0)--(1,0);
\end{tikzpicture}
\end{center}
\item HP: $\left(-\frac{1}{2}, 3\right)$
\end{itemize}
\end{enumerate}
'''
        schema = build_exam_schema(multi, source='multi')
        q = schema.questions[0]
        assert len(q.methods) == 2
        assert {m.id for m in q.methods} == {'factoring', 'quadratic_formula'}
        assert len(q.steps) == 2
        shared_blob = ' '.join(q.steps)
        assert 'b^2' not in shared_blob.replace(' ', '')
        assert 'pm' not in shared_blob
        kinds = {p.kind for p in q.parts}
        assert kinds == {'algebra', 'sign_chart', 'figure', 'hp'}
        assert 'sign_chart' in {m.role for m in q.milestones}
        assert 'hp' in {m.role for m in q.milestones}
        rubric = rubric_from_parts(q.number, q.parts)
        assert rubric.maximum_score == 10
        assert sum(c.points for c in rubric.criteria) == pytest.approx(10.0)
        ids = {c.id for c in rubric.criteria}
        assert ids == {'algebra', 'critical_points', 'figure', 'final_answer'}

        single = build_exam_schema(_MINI_KUNCI, source='mini')
        q1 = single.questions[0]
        assert q1.methods == []
        assert len(q1.steps) >= 1
        assert 'algebra' in {p.kind for p in q1.parts}

        rendered = ingest_kunci_tex(multi, source_note='multi.tex')[0][1]
        assert '% method: factoring' in rendered
        assert '% method: quadratic_formula' in rendered
        assert '% role: sign_chart' in rendered
        assert '% final answer' in rendered

    def test_latex_to_symbolic_skips_text_only(self) -> None:
        from app.functions.symbolic_from_latex import latex_to_symbolic_payload

        assert latex_to_symbolic_payload(r'\text{Cari akar-akar}') is None
        assert latex_to_symbolic_payload('') is None
        payload = latex_to_symbolic_payload(r'x \geq -\frac{10}{3}')
        assert payload is not None
        assert payload.kind == 'relation'
        assert '>=' in payload.repr
        assert 'oo' not in payload.repr

    def test_implies_normalize_and_symbolic(self) -> None:
        from sympy.logic.boolalg import And

        from app.functions.symbolic_from_latex import (
            coalesce_step_symbolic,
            latex_to_symbolic_payload,
        )
        from app.models.recognition import SymbolicPayload
        from app.services.math.parser import parse_math_step

        for raw in (
            r'-3x = 0 \implies x = 0',
            r'-3x = 0 \Rightarrow x = 0',
            '-3x = 0 => x = 0',
        ):
            normalized = normalize_math_text(raw)
            assert ' and ' in normalized
            assert 'x = 0' in normalized.replace(' ', '') or 'x=0' in normalized.replace(
                ' ', ''
            )

        payload = latex_to_symbolic_payload(r'-3x = 0 \implies x = 0')
        assert payload is not None
        assert payload.kind == 'relation'
        assert 'and' in payload.repr
        assert '-3' in payload.repr.replace(' ', '')
        assert 'x = 0' in payload.repr or 'x=0' in payload.repr.replace(' ', '')

        truncated = SymbolicPayload(kind='expression', repr='-3*x = 0')
        fixed = coalesce_step_symbolic(r'-3x = 0 \implies x = 0', truncated)
        assert fixed is not None
        assert fixed.kind == 'relation'
        assert 'and' in fixed.repr
        assert 'x = 0' in fixed.repr or 'x=0' in fixed.repr.replace(' ', '')

        kind_only = coalesce_step_symbolic(
            '-3*x = 0',
            SymbolicPayload(kind='expression', repr='-3*x = 0'),
        )
        assert kind_only is not None
        assert kind_only.kind == 'relation'
        assert kind_only.repr == '-3*x = 0'

        x = Symbol('x')
        step = parse_math_step('-3*x = 0 and x = 0', x)
        assert step.kind == 'relation'
        assert isinstance(step.value, And)

    def test_build_exam_schema_text_steps_null_symbolic(self) -> None:
        tex = r'''
\begin{enumerate}
\item $x > 0$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah
\begin{align}
\text{Cari akar} \\
x &> 0
\end{align}
\item HP: $(0, \infty)$
\end{itemize}
\end{enumerate}
'''
        schema = build_exam_schema(tex, source='text-step')
        q = schema.questions[0]
        assert len(q.steps) == 2
        assert len(q.steps_symbolic) == 2
        assert q.steps_symbolic[0] is None
        assert q.steps_symbolic[1] is not None
        assert q.steps_symbolic[1].kind == 'relation'

    def test_soal_marker_overrides_enumerate_index(self) -> None:
        tex = r'''
\begin{enumerate}
% soal ke 2
\item $3x-5 > 1$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah
\begin{align}
3x &> 6
\end{align}
\item HP: $(2, \infty)$
\end{itemize}
% soal ke 5
\item $x < 0$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah
\begin{align}
x &< 0
\end{align}
\item HP: $(-\infty, 0)$
\end{itemize}
\end{enumerate}
'''
        stems = extract_question_stems(tex)
        assert [n for n, _ in stems] == [2, 5]
        assert '3x-5' in stems[0][1]
        assert 'x < 0' in stems[1][1] or 'x<0' in stems[1][1].replace(' ', '')
        schema = build_exam_schema(tex, source='markers')
        assert [q.number for q in schema.questions] == [2, 5]
        assert all(q.expects_figure is False for q in schema.questions)
        items = split_enumerate_items(tex)
        assert extract_soal_number(items[0]) == 2
        assert extract_soal_number(items[1]) == 5

    def test_gambar_marker_sets_expects_figure_without_tikz(self) -> None:
        tex = r'''
\begin{enumerate}
% soal ke 3
\item $x > 1$
% jawaban soal ke 3
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah
\begin{align}
x &> 1
\end{align}
% gambar soal ke 3
\item HP: $(1, \infty)$
\end{itemize}
\end{enumerate}
'''
        items = split_enumerate_items(tex)
        assert len(items) == 1
        assert item_expects_figure(items[0]) is True
        schema = build_exam_schema(tex, source='gambar-marker')
        assert len(schema.questions) == 1
        q = schema.questions[0]
        assert q.number == 3
        assert q.expects_figure is True
        assert 'figure' in {p.kind for p in q.parts}
        assert 'HP' not in q.stem
        block = format_recognition_question_block(schema)
        assert '[expects_figure]' in block

    def test_build_exam_schema_with_tikz(self) -> None:
        tex = r'''
\begin{enumerate}
\item $x > 0$
\textbf{Penyelesaian:}
\begin{itemize}
\item Langkah
\begin{align}
x &> 0
\end{align}
\item Gambar
\begin{tikzpicture}
\draw (0,0)--(1,0);
\end{tikzpicture}
\item HP: $(0, \infty)$
\end{itemize}
\end{enumerate}
'''
        schema = build_exam_schema(tex, source='tikz')
        assert len(schema.questions) == 1
        q = schema.questions[0]
        assert q.expects_figure is True
        assert [p.kind for p in q.parts] == ['algebra', 'figure', 'hp']
        block = format_recognition_question_block(schema)
        assert '[expects_figure]' in block
        assert 'infty' not in block  # HP must not leak into recognition block
        assert q.final  # schema itself still has final for grading metadata

    def test_ingester_writes_exam_schema(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci.tex'
        kunci.write_text(_MINI_KUNCI, encoding='utf-8')
        standard = tmp_path / 'standards' / 'exam'
        written = KunciIngester(standard).ingest_file(kunci)
        schema_file = exam_schema_path(standard)
        assert schema_file in written
        assert schema_file.is_file()
        loaded = load_exam_schema(standard)
        assert loaded is not None
        assert len(loaded.questions) == 2
        assert loaded.questions[0].stem
        assert loaded.questions[0].final_symbolic is not None
        assert 'oo' in loaded.questions[0].final_symbolic.repr
        rubric_path = standard / 'rubrics' / 'question_001.json'
        assert rubric_path in written
        assert rubric_path.is_file()
        from app.models.grading import Rubric

        rubric = Rubric.model_validate_json(rubric_path.read_text(encoding='utf-8'))
        assert rubric.maximum_score == 10
        assert sum(c.points for c in rubric.criteria) == pytest.approx(10.0)

    def test_repo_exam_schema_at_least_six(self) -> None:
        path = Path('data/input/kunci_jawaban/jawaban_tugas_1.tex')
        schema = build_exam_schema(path.read_text(encoding='utf-8'), source=path.name)
        assert len(schema.questions) >= 6
        assert schema.questions[0].expects_figure is True
        assert schema.questions[0].final_symbolic is not None
        assert 'oo' in schema.questions[0].final_symbolic.repr
        block = format_recognition_question_block(schema)
        assert 'expects_figure' in block
        assert 'Penyelesaian' not in block

    def test_split_enumerate_items_mini(self) -> None:
        items = split_enumerate_items(_MINI_KUNCI)
        assert len(items) == 2
        assert '2-3x' in items[0]
        assert '3x-5' in items[1]

    def test_extract_hp_and_steps_mini(self) -> None:
        items = split_enumerate_items(_MINI_KUNCI)
        steps = extract_align_steps(items[0])
        assert len(steps) >= 2
        assert 'text' not in steps[0].lower()
        assert extract_hp_final(items[0]) is not None
        assert '10' in (extract_hp_final(items[0]) or '')

    def test_quad_text_strip_nested_frac(self) -> None:
        item = r'''
\item $x>0$
\begin{align}
-3x \cdot \left(-\frac{1}{3}\right) &\geq 10 \cdot \left(-\frac{1}{3}\right) \quad \text{(Kali kedua ruas dengan $-\frac{1}{3}$)} \\
x &\geq -\frac{10}{3}
\end{align}
\item HP: $[-\frac{10}{3}, \infty)$
'''
        steps = extract_align_steps(item)
        assert len(steps) == 2
        assert 'text' not in steps[0].lower()
        assert 'quad' not in steps[0].lower()
        assert r'\frac{1}{3}' in steps[0] or r'\frac{10}{3}' in steps[1]

    def test_ingest_kunci_tex_pairs(self) -> None:
        pairs = ingest_kunci_tex(_MINI_KUNCI, source_note='mini')
        assert len(pairs) == 2
        assert pairs[0][0] == 1
        final = extract_final_answer_from_tex(pairs[0][1])
        assert final is not None
        assert '10' in final

    def test_ingester_writes_solutions(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci.tex'
        kunci.write_text(_MINI_KUNCI, encoding='utf-8')
        standard = tmp_path / 'standards' / 'exam'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'rubrics' / 'keep.json').write_text('{}', encoding='utf-8')
        written = KunciIngester(standard).ingest_file(kunci)
        assert len(written) == 5  # 2 solutions + schema + 2 rubrics
        assert (standard / 'solutions' / 'question_001.tex').is_file()
        assert (standard / 'solutions' / 'question_002.tex').is_file()
        assert (standard / 'exam_schema.json').is_file()
        assert (standard / 'rubrics' / 'question_001.json').is_file()
        assert (standard / 'rubrics' / 'keep.json').is_file()

    def test_controller_ingest_dir(self, tmp_path: Path) -> None:
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir()
        (kunci_dir / 'a.tex').write_text(_MINI_KUNCI, encoding='utf-8')
        standard = tmp_path / 'std'
        result = IngestKunciController().ingest(kunci_path=None, kunci_dir=kunci_dir, standard_dir=standard)
        assert len(result.written) == 5  # 2 solutions + schema + 2 rubrics
        assert result.schema_path is not None
        assert result.schema_path.is_file()
        assert (standard / 'rubrics' / 'question_001.json').is_file()

    def test_repo_jawaban_tugas_1_at_least_six(self) -> None:
        path = Path('data/input/kunci_jawaban/jawaban_tugas_1.tex')
        assert path.is_file()
        pairs = ingest_kunci_tex(path.read_text(encoding='utf-8'), source_note=path.name)
        assert len(pairs) >= 6
        q1_final = extract_final_answer_from_tex(pairs[0][1])
        assert q1_final is not None
        assert '10' in q1_final and '3' in q1_final

class TestReport:

    def test_aggregate_full_auto_accept(self, tmp_path: Path) -> None:
        report = aggregate_exam_report([_report_question_grade(1, 10.0, 10.0)], _metadata(tmp_path))
        assert report.total_score == pytest.approx(10.0)
        assert report.maximum_total == pytest.approx(10.0)
        assert report.overall_status == ReviewStatus.AUTO_ACCEPT
        assert len(report.questions) == 1

    def test_aggregate_review_required_overall(self, tmp_path: Path) -> None:
        report = aggregate_exam_report([_report_question_grade(1, 10.0, 10.0), _report_question_grade(2, 5.0, 10.0, review=ReviewStatus.REVIEW_REQUIRED)], _metadata(tmp_path))
        assert report.total_score == pytest.approx(15.0)
        assert report.overall_status == ReviewStatus.REVIEW_REQUIRED
        header, row = summary_csv_rows(report)
        assert header == ['student_id', 'q1', 'q2', 'total', 'status']
        assert row[0] == 'student_001'
        assert row[1] == '10'
        assert row[2] == '5'
        assert row[3] == '15'
        assert row[4] == 'REVIEW_REQUIRED'

    def test_reporter_writes_three_formats(self, tmp_path: Path) -> None:
        report = aggregate_exam_report([_report_question_grade(1, 10.0, 10.0)], _metadata(tmp_path))
        out = tmp_path / 'output' / 'exam_001'
        paths = JsonCsvHtmlReporter().write(report, out)
        assert len(paths) == 3
        assert (out / 'report.json').is_file()
        assert (out / 'summary.csv').is_file()
        assert (out / 'report.html').is_file()
        csv_text = (out / 'summary.csv').read_text(encoding='utf-8')
        assert 'student_id,q1,total,status' in csv_text
        assert 'student_001,10,10,AUTO_ACCEPT' in csv_text
        html = (out / 'report.html').read_text(encoding='utf-8')
        assert 'student_001' in html
        assert 'AUTO_ACCEPT' in html
        payload = (out / 'report.json').read_text(encoding='utf-8')
        assert '"total_score": 10.0' in payload or '"total_score": 10' in payload
        assert 'recognition-v1' in payload

    def test_controller_missing_grading_errors(self, tmp_path: Path) -> None:
        questions = tmp_path / 'questions'
        questions.mkdir()
        with pytest.raises(GradingNotFoundError):
            ReportController(JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards' / 'exam_001').report(questions, tmp_path / 'out')

    def test_controller_does_not_mutate_grading(self, tmp_path: Path) -> None:
        questions = tmp_path / 'questions'
        qdir = questions / 'question_001'
        qdir.mkdir(parents=True)
        grade = _report_question_grade(1, 10.0, 10.0)
        gpath = qdir / 'grading.json'
        original = grade.model_dump_json(indent=2)
        gpath.write_text(original, encoding='utf-8')
        qpath = qdir / 'question.json'
        qpath.write_text('{"keep": true}', encoding='utf-8')
        result = ReportController(JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards', vision_model='v', reasoning_model='r').report(questions, tmp_path / 'out', student_id='student_001')
        assert result.exam_report.total_score == pytest.approx(10.0)
        assert gpath.read_text(encoding='utf-8') == original
        assert qpath.read_text(encoding='utf-8') == '{"keep": true}'
        assert result.report_json_path.is_file()

class TestCliProcess:

    def test_process_controller_runs_all_stages(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / 'pages'
        recognition_dir = tmp_path / 'recognition'
        questions_dir = tmp_path / 'questions'
        output_dir = tmp_path / 'output'
        pdf = tmp_path / 'answer.pdf'
        pdf.write_bytes(b'%PDF')
        render = MagicMock()
        render.render.return_value = RenderResult(pages=[_page()], output_dir=pages_dir, metadata_path=pages_dir / 'pages.json')
        recognize = MagicMock()
        recognize.recognize_pages.return_value = RecognizeResult(pages=[], output_dir=recognition_dir, artifact_paths=[])
        extract = MagicMock()
        extract.extract.return_value = ExtractResult(questions=[], output_dir=questions_dir, artifact_paths=[])
        latex = MagicMock()
        latex.build.return_value = LatexResult(artifacts=[], questions_dir=questions_dir)
        validate = MagicMock()
        validate.validate.return_value = ValidateResult(validations=[], questions_dir=questions_dir, artifact_paths=[])
        grade = MagicMock()
        grade.grade.return_value = GradeResult(grades=[_process_question_grade()], questions_dir=questions_dir, standard_dir=tmp_path / 'standards', artifact_paths=[])
        report = MagicMock()
        report.report.return_value = _report_result(tmp_path)
        progress_events: list[ProcessStage] = []
        cleared: list[tuple[Path, list[str]]] = []
        output_dir.mkdir(parents=True)
        stale = output_dir / 'pages'
        stale.mkdir()
        (stale / 'old.png').write_bytes(b'x')
        standards = output_dir / 'standards'
        standards.mkdir()
        (standards / 'keep.txt').write_text('keep', encoding='utf-8')
        controller = ProcessController(render_controller=render, recognize_controller=recognize, extract_controller=extract, latex_controller=latex, validate_controller=validate, grade_controller=grade, report_controller=report, on_progress=lambda p: progress_events.append(p.stage), on_output_cleared=lambda root, names: cleared.append((root, names)))
        result = controller.process(pdf, pages_dir=pages_dir, recognition_dir=recognition_dir, questions_dir=questions_dir, output_dir=output_dir, dpi=200, student_id='student_001', workspace_root=output_dir)
        assert progress_events == [ProcessStage.RENDER, ProcessStage.RECOGNIZE, ProcessStage.EXTRACT, ProcessStage.LATEX, ProcessStage.VALIDATE, ProcessStage.GRADE, ProcessStage.REPORT]
        assert cleared and cleared[0][0] == output_dir
        assert 'pages' in cleared[0][1]
        assert not stale.exists()
        assert (standards / 'keep.txt').is_file()
        assert result.total_score == pytest.approx(8.0)
        assert result.maximum_total == pytest.approx(10.0)
        assert len(result.questions) == 1
        render.render.assert_called_once()
        recognize.recognize_pages.assert_called_once()
        extract.extract.assert_called_once()
        latex.build.assert_called_once()
        validate.validate.assert_called_once()
        grade.grade.assert_called_once()
        report.report.assert_called_once()

    def test_process_from_crops_skips_render_and_wipe(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / 'pages'
        pages_dir.mkdir()
        (pages_dir / 'pages.json').write_text(
            '[{"page_number":1,"image":"page_001.png","width":10,"height":10}]',
            encoding='utf-8',
        )
        crops = tmp_path / 'crops' / 'page_001'
        crops.mkdir(parents=True)
        (crops / 'page_001_regions.json').write_text(
            '{"page_number":1,"source":"ink","regions":[]}',
            encoding='utf-8',
        )
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        stale_recognition = recognition_dir / 'page_009_recognition.json'
        stale_recognition.write_text('{}', encoding='utf-8')
        questions_dir = tmp_path / 'questions'
        questions_dir.mkdir()
        leftover = questions_dir / 'question_099' / 'question.json'
        leftover.parent.mkdir()
        leftover.write_text('{}', encoding='utf-8')
        output_dir = tmp_path / 'output'
        render = MagicMock()
        recognize = MagicMock()
        recognize.recognize_pages.return_value = RecognizeResult(
            pages=[], output_dir=recognition_dir, artifact_paths=[]
        )
        extract = MagicMock()
        extract.extract.return_value = ExtractResult(
            questions=[], output_dir=questions_dir, artifact_paths=[]
        )
        latex = MagicMock()
        latex.build.return_value = LatexResult(artifacts=[], questions_dir=questions_dir)
        validate = MagicMock()
        validate.validate.return_value = ValidateResult(
            validations=[], questions_dir=questions_dir, artifact_paths=[]
        )
        grade = MagicMock()
        grade.grade.return_value = GradeResult(
            grades=[_process_question_grade()],
            questions_dir=questions_dir,
            standard_dir=tmp_path / 'standards',
            artifact_paths=[],
        )
        report = MagicMock()
        report.report.return_value = _report_result(tmp_path)
        cleared: list = []
        controller = ProcessController(
            render_controller=render,
            recognize_controller=recognize,
            extract_controller=extract,
            latex_controller=latex,
            validate_controller=validate,
            grade_controller=grade,
            report_controller=report,
            on_output_cleared=lambda root, names: cleared.append((root, names)),
        )
        result = controller.process_from_crops(
            pages_dir=pages_dir,
            recognition_dir=recognition_dir,
            questions_dir=questions_dir,
            output_dir=output_dir,
            student_id='student_001',
            crops_dir=tmp_path / 'crops',
        )
        assert cleared == []
        assert not leftover.exists()
        assert not stale_recognition.exists()
        assert (pages_dir / 'pages.json').is_file()
        assert (crops / 'page_001_regions.json').is_file()
        render.render.assert_not_called()
        recognize.recognize_pages.assert_called_once()
        assert recognize.recognize_pages.call_args.kwargs.get('from_crops') is True
        assert result.total_score == pytest.approx(8.0)

    def test_cli_process_success(self, tmp_path: Path, monkeypatch, capsys) -> None:
        pdf = tmp_path / 'answer.pdf'
        pdf.write_bytes(b'%PDF')
        questions_dir = tmp_path / 'questions'
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('\n'.join(['ollama:', '  vision_model: "vision-test"', '  reasoning_model: "reason-test"', 'pdf:', f"  output_dir: {(tmp_path / 'pages').as_posix()}", 'recognition:', f"  output_dir: {(tmp_path / 'recognition').as_posix()}", 'questions:', f'  output_dir: {questions_dir.as_posix()}', 'grading:', f"  standard_dir: {(tmp_path / 'standards').as_posix()}", 'report:', f'  output_dir: {output_dir.as_posix()}']), encoding='utf-8')
        fake_result = MagicMock()
        fake_result.student_id = 'student_001'
        fake_result.questions = [MagicMock(question_number=1, score=8.0, maximum_score=10.0, review_status=ReviewStatus.AUTO_ACCEPT)]
        fake_result.total_score = 8.0
        fake_result.maximum_total = 10.0
        fake_result.overall_status = ReviewStatus.AUTO_ACCEPT
        fake_result.output_dir = output_dir
        fake_result.report_json_path = output_dir / 'report.json'
        fake_result.summary_csv_path = output_dir / 'summary.csv'
        fake_result.report_html_path = output_dir / 'report.html'

        class FakeProcessController:

            def __init__(self, **kwargs) -> None:
                self.on_progress = kwargs.get('on_progress')

            def process(self, *args, **kwargs):
                if self.on_progress:
                    from app.models.process import ProcessProgress
                    self.on_progress(ProcessProgress(stage=ProcessStage.RENDER, completed=1, total=7))
                    self.on_progress(ProcessProgress(stage=ProcessStage.REPORT, completed=7, total=7))
                return fake_result
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: FakeProcessController(**kwargs))
        exit_code = main(['--config', str(config_path), 'process', str(pdf), '--output', str(output_dir), '--student-id', 'student_001'])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert 'Membersihkan' in out
        assert 'Vision:' in out
        assert 'vision-test' in out
        assert 'Progress' in out
        assert 'PDF rendering' in out
        assert 'Results' in out
        assert '8/10' in out
        assert 'Artifacts' in out

    def test_cli_process_resolves_bare_filename(self, tmp_path: Path, monkeypatch, capsys) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        pdf = jawaban / 'smoke_inequality.pdf'
        pdf.write_bytes(b'%PDF')
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('\n'.join(['ollama:', '  vision_model: "vision-test"', 'input:', f'  jawaban_dir: {jawaban.as_posix()}', 'report:', f'  output_dir: {output_dir.as_posix()}']), encoding='utf-8')
        selected: list[Path] = []

        class CapturingProcessController:

            def __init__(self, **kwargs) -> None:
                pass

            def process(self, pdf_path, **kwargs):
                selected.append(Path(pdf_path))
                from app.models.process import ProcessResult
                return ProcessResult(student_id='student_001', questions=[], total_score=0.0, maximum_total=0.0, overall_status=ReviewStatus.AUTO_ACCEPT, output_dir=output_dir, report_json_path=None, summary_csv_path=None, report_html_path=None, questions_dir=tmp_path / 'questions', pages_dir=tmp_path / 'pages', recognition_dir=tmp_path / 'recognition')
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: CapturingProcessController(**kwargs))
        exit_code = main(['--config', str(config_path), 'process', 'smoke_inequality.pdf'])
        assert exit_code == 0
        assert selected == [pdf]

    def test_process_controller_skip_reset_leaves_workspace(self, tmp_path: Path) -> None:
        pages_dir = tmp_path / 'pages'
        recognition_dir = tmp_path / 'recognition'
        questions_dir = tmp_path / 'questions'
        output_dir = tmp_path / 'output'
        output_dir.mkdir()
        stale = output_dir / 'keep_me.txt'
        stale.write_text('stale', encoding='utf-8')
        pdf = tmp_path / 'answer.pdf'
        pdf.write_bytes(b'%PDF')
        render = MagicMock()
        render.render.return_value = RenderResult(pages=[_page()], output_dir=pages_dir, metadata_path=pages_dir / 'pages.json')
        recognize = MagicMock()
        recognize.recognize_pages.return_value = RecognizeResult(pages=[], output_dir=recognition_dir, artifact_paths=[])
        extract = MagicMock()
        extract.extract.return_value = ExtractResult(questions=[], output_dir=questions_dir, artifact_paths=[])
        latex = MagicMock()
        latex.build.return_value = LatexResult(artifacts=[], questions_dir=questions_dir)
        validate = MagicMock()
        validate.validate.return_value = ValidateResult(validations=[], questions_dir=questions_dir, artifact_paths=[])
        grade = MagicMock()
        grade.grade.return_value = GradeResult(grades=[_process_question_grade()], questions_dir=questions_dir, standard_dir=tmp_path / 'standards', artifact_paths=[])
        report = MagicMock()
        report.report.return_value = _report_result(tmp_path)
        ProcessController(render_controller=render, recognize_controller=recognize, extract_controller=extract, latex_controller=latex, validate_controller=validate, grade_controller=grade, report_controller=report).process(pdf, pages_dir=pages_dir, recognition_dir=recognition_dir, questions_dir=questions_dir, output_dir=output_dir, dpi=200, workspace_root=output_dir, reset_workspace=False)
        assert stale.is_file()

    def test_cli_process_domain_error(self, tmp_path: Path, monkeypatch, capsys) -> None:
        pdf = tmp_path / 'missing.pdf'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('ollama:\n  vision_model: "vision-test"\n', encoding='utf-8')

        class FailingProcessController:

            def __init__(self, **kwargs) -> None:
                pass

            def process(self, *args, **kwargs):
                raise PdfNotFoundError(pdf)
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: FailingProcessController(**kwargs))
        exit_code = main(['--config', str(config_path), 'process', str(pdf)])
        assert exit_code == 1
        err = capsys.readouterr().err
        assert 'Error' in err
        assert 'PDF not found' in err

    def test_cli_process_unexpected_error(self, tmp_path: Path, monkeypatch, capsys) -> None:
        pdf = tmp_path / 'answer.pdf'
        pdf.write_bytes(b'%PDF')
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('ollama:\n  vision_model: "vision-test"\n', encoding='utf-8')

        class BoomProcessController:

            def __init__(self, **kwargs) -> None:
                pass

            def process(self, *args, **kwargs):
                raise RuntimeError('boom unexpected')
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: BoomProcessController(**kwargs))
        exit_code = main(['--config', str(config_path), 'process', str(pdf)])
        assert exit_code == 2
        err = capsys.readouterr().err
        assert 'Error' in err
        assert 'boom unexpected' in err

    def test_cli_process_requires_vision_model(self, tmp_path: Path, capsys) -> None:
        pdf = tmp_path / 'answer.pdf'
        pdf.write_bytes(b'%PDF')
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('ollama:\n  vision_model: ""\n', encoding='utf-8')
        exit_code = main(['--config', str(config_path), 'process', str(pdf)])
        assert exit_code == 1
        assert 'Vision model is not configured' in capsys.readouterr().err

    def test_cli_process_interactive_pdf_choice(self, tmp_path: Path, monkeypatch, capsys) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        pdf_a = jawaban / 'alpha.pdf'
        pdf_b = jawaban / 'beta.pdf'
        pdf_a.write_bytes(b'%PDF')
        pdf_b.write_bytes(b'%PDF')
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('\n'.join(['ollama:', '  vision_model: "vision-test"', 'input:', f'  jawaban_dir: {jawaban.as_posix()}', 'report:', f'  output_dir: {output_dir.as_posix()}']), encoding='utf-8')
        selected: list[Path] = []

        class CapturingProcessController:

            def __init__(self, **kwargs) -> None:
                pass

            def process(self, pdf_path, **kwargs):
                selected.append(Path(pdf_path))
                from app.models.process import ProcessResult
                from app.models.grading import ReviewStatus
                return ProcessResult(student_id='student_001', questions=[], total_score=0.0, maximum_total=0.0, overall_status=ReviewStatus.AUTO_ACCEPT, output_dir=output_dir, report_json_path=None, summary_csv_path=None, report_html_path=None, questions_dir=tmp_path / 'questions', pages_dir=tmp_path / 'pages', recognition_dir=tmp_path / 'recognition')
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: CapturingProcessController(**kwargs))
        monkeypatch.setattr('builtins.input', lambda _prompt='': '2')
        exit_code = main(['--config', str(config_path), 'process'])
        assert exit_code == 0
        assert selected == [pdf_b]
        out = capsys.readouterr().out
        assert 'PDF tersedia' in out
        assert 'beta.pdf' in out
        assert 'Memproses:' in out

    def test_cli_process_no_pdfs_in_jawaban(self, tmp_path: Path, capsys) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        config_path = tmp_path / 'config.yaml'
        config_path.write_text('\n'.join(['ollama:', '  vision_model: "vision-test"', 'input:', f'  jawaban_dir: {jawaban.as_posix()}']), encoding='utf-8')
        exit_code = main(['--config', str(config_path), 'process'])
        assert exit_code == 1
        assert 'No PDF files found' in capsys.readouterr().err

    def test_cli_process_continue_then_exit(self, tmp_path: Path, monkeypatch, capsys) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        pdf_a = jawaban / 'alpha.pdf'
        pdf_b = jawaban / 'beta.pdf'
        pdf_a.write_bytes(b'%PDF')
        pdf_b.write_bytes(b'%PDF')
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text(
            '\n'.join(
                [
                    'ollama:',
                    '  vision_model: "vision-test"',
                    'input:',
                    f'  jawaban_dir: {jawaban.as_posix()}',
                    'report:',
                    f'  output_dir: {output_dir.as_posix()}',
                ]
            ),
            encoding='utf-8',
        )
        selected: list[Path] = []

        class CapturingProcessController:
            def __init__(self, **kwargs) -> None:
                pass

            def process(self, pdf_path, **kwargs):
                selected.append(Path(pdf_path))
                from app.models.process import ProcessResult

                return ProcessResult(
                    student_id='student_001',
                    questions=[],
                    total_score=0.0,
                    maximum_total=0.0,
                    overall_status=ReviewStatus.AUTO_ACCEPT,
                    output_dir=output_dir,
                    report_json_path=None,
                    summary_csv_path=None,
                    report_html_path=None,
                    questions_dir=tmp_path / 'questions',
                    pages_dir=tmp_path / 'pages',
                    recognition_dir=tmp_path / 'recognition',
                )

        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.cli.sys.stdin', stdin)
        monkeypatch.setattr('app.views.exit_view.sys.stdin', stdin)
        # first process uses argv pdf; then continue menu 1; pick beta; then exit 2
        answers = iter(['1', '2', '2'])
        monkeypatch.setattr('builtins.input', lambda _p='': next(answers))
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: CapturingProcessController(**kwargs))
        reset_interactive_session_flag()
        exit_code = main(
            ['--config', str(config_path), 'process', str(pdf_a)]
        )
        assert exit_code == 0
        assert selected == [pdf_a, pdf_b]
        out = capsys.readouterr().out
        assert 'Selesai.' in out
        assert 'Proses PDF lain' in out

    def test_cli_menu_finish_defaults_student_id(self, tmp_path: Path, monkeypatch, capsys) -> None:
        jawaban = tmp_path / 'jawaban'
        jawaban.mkdir()
        pages_dir = tmp_path / 'pages'
        pages_dir.mkdir()
        (pages_dir / 'pages.json').write_text(
            '[{"page_number":1,"image":"page_001.png","width":10,"height":10}]',
            encoding='utf-8',
        )
        crops_dir = tmp_path / 'crops' / 'page_001'
        crops_dir.mkdir(parents=True)
        (crops_dir / 'page_001_regions.json').write_text(
            '{"page_number":1,"source":"ink","regions":[]}',
            encoding='utf-8',
        )
        output_dir = tmp_path / 'output'
        config_path = tmp_path / 'config.yaml'
        config_path.write_text(
            '\n'.join(
                [
                    'ollama:',
                    '  vision_model: "vision-test"',
                    'input:',
                    f'  jawaban_dir: {jawaban.as_posix()}',
                    'pdf:',
                    f'  output_dir: {pages_dir.as_posix()}',
                    'recognition:',
                    f'  crops_dir: {(tmp_path / "crops").as_posix()}',
                    f'  output_dir: {(tmp_path / "recognition").as_posix()}',
                    'report:',
                    f'  output_dir: {output_dir.as_posix()}',
                ]
            ),
            encoding='utf-8',
        )
        captured: list[str] = []

        class CapturingProcessController:
            def __init__(self, **kwargs) -> None:
                pass

            def process_from_crops(self, **kwargs):
                captured.append(kwargs.get('student_id'))
                from app.models.process import ProcessResult

                return ProcessResult(
                    student_id=kwargs.get('student_id') or 'student_001',
                    questions=[],
                    total_score=0.0,
                    maximum_total=0.0,
                    overall_status=ReviewStatus.AUTO_ACCEPT,
                    output_dir=output_dir,
                    report_json_path=None,
                    summary_csv_path=None,
                    report_html_path=None,
                    questions_dir=tmp_path / 'questions',
                    pages_dir=pages_dir,
                    recognition_dir=tmp_path / 'recognition',
                )

        stdin = MagicMock()
        stdin.isatty.return_value = True
        monkeypatch.setattr('app.cli.sys.stdin', stdin)
        answers = iter(['4', '5'])
        monkeypatch.setattr('builtins.input', lambda _p='': next(answers))
        monkeypatch.setattr('app.cli.build_process_controller', lambda config, **kwargs: CapturingProcessController(**kwargs))
        exit_code = main(['--config', str(config_path), 'menu'])
        assert exit_code == 0
        assert captured == ['student_001']
