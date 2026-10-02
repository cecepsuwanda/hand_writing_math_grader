from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import ValidationError
from sympy import Eq, FiniteSet, Lt, Rational, Symbol
from sympy.logic.boolalg import And

from app.capabilities.registry import ALL_CAPABILITY_IDS, apply_capabilities
from app.cli import build_parser, main
from app.commands import COMMANDS, Command, flows
from app.commands.crops import LabelCommand
from app.commands.menu_actions import CliMenuActions
from app.config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    GradingConfig,
    OllamaConfig,
    OutputConfig,
    RecognitionConfig,
    ReportConfig,
    ReportPdfConfig,
    load_config,
)
from app.controllers.extract_controller import ExtractController
from app.controllers.ingest_kunci_controller import IngestKunciController
from app.controllers.menu_controller import MenuController, exit_code_for
from app.controllers.question_review_controller import QuestionReviewController
from app.controllers.recognize_controller import RecognizeController
from app.controllers.report_controller import ReportController
from app.exceptions import (
    AmbiguousKunciDirError,
    ConfigNotFoundError,
    CropsRegionsMissingError,
    EmptyExtractionError,
    EmptyPdfError,
    GradingNotFoundError,
    InvalidPdfError,
    InvalidPdfSelectionError,
    InvalidRecognitionJsonError,
    MathParseError,
    NoKunciTexError,
    NoRegionsJsonError,
    OllamaModelNotConfiguredError,
    OllamaRequestError,
    OllamaTimeoutError,
    OllamaUnavailableError,
    OperationCancelledError,
    PdfNotFoundError,
    QuestionArtifactsInvalidError,
    QuestionCropsInvalidError,
    QuestionsNotFoundError,
    RecognitionNotFoundError,
    RecognitionPathMismatchError,
    RegionsArtifactMissingError,
    ReportPdfError,
    RunNotSpecifiedError,
    StandardDirMismatchError,
    UnknownTopicError,
    ValidationNotFoundError,
)
from app.functions.json_extract import (
    extract_json_object,
    repair_json_escapes,
    repair_llm_json_syntax,
    salvage_judgement_object,
)
from app.functions.kunci_ingest import (
    build_exam_schema,
    extract_align_steps,
    extract_hp_final,
    extract_question_stems,
    extract_soal_number,
    format_recognition_question_block,
    ingest_kunci_tex,
    item_expects_figure,
    load_exam_schema,
    load_question_stems_from_kunci,
    rubric_from_parts,
    split_enumerate_items,
)
from app.functions.latex_transforms import (
    build_student_latex,
    escape_latex_text,
    format_aligned_line,
    normalize_step_latex,
    strip_final_answer_prefix,
)
from app.functions.latex_compile import latex_error_summary, pdflatex_command
from app.functions.latex_report import (
    build_question_view,
    graphics_path,
    latex_math_or_text,
    latex_stem,
    latex_text,
)
from app.functions.page_names import page_image_filename, page_recognition_filename
from app.functions.artifact_guard import changed_files, snapshot_files
from app.functions.grading_artifact import grading_artifact_paths, load_question_grades
from app.functions.menu_choices import (
    MAIN_MENU,
    MAIN_MENU_PROMPT,
    MenuChoice,
    parse_continue_or_exit,
    parse_main_menu_choice,
    parse_topic_choice,
    parse_yes_no,
)
from app.functions.paths import (
    list_jawaban_pdfs,
    list_kunci_tex,
    parse_kunci_choice,
    parse_path_choice,
    parse_pdf_choice,
    parse_run_choice,
    resolve_jawaban_pdf,
)
from app.functions.question_crops import load_question_crops, write_question_crops
from app.functions.question_merge import collect_latex_documents, merge_page_recognitions
from app.functions.question_names import parse_question_ref
from app.functions.question_review import review_flags
from app.functions.regions_artifact import write_regions_artifact
from app.functions.question_split import (
    match_schema_final,
    match_schema_stem,
    split_questions_by_exam_schema,
)
from app.functions.report_aggregate import aggregate_exam_report, summary_csv_rows
from app.functions.run_layout import (
    RunLayout,
    build_run_layout,
    layout_for_pdf,
    list_run_dirs,
    resolve_run_name,
    safe_run_name,
    sanitize_run_name,
)
from app.functions.score_aggregate import aggregate_question_grade, allocate_step_max_scores
from app.functions.standards_layout import standards_folder_name
from app.functions.standard_extract import (
    exam_schema_path,
    extract_final_answer_from_tex,
    extract_solution_steps_from_tex,
    standard_solution_path,
    standard_step_texts,
)
from app.functions.step_align import align_student_steps_to_standard
from app.functions.step_references import final_reference_index, reference_indices, step_checks_for
from app.functions.symbolic_from_latex import coalesce_step_symbolic, latex_to_symbolic_payload
from app.functions.validation_artifact import (
    load_question_artifact,
    question_artifact_paths,
    write_validation_artifact,
)
from app.functions.workspace_reset import clear_output_workspace, prepare_pipeline_workspace
from app.interfaces.menu_actions import MenuActions
from app.interfaces.validator import StepValidator
from app.models.defaults import DEFAULT_STUDENT_ID
from app.models.exam_schema import ExamMethod, ExamMilestone, ExamPart, ExamQuestion, ExamSchema
from app.models.grading import (
    GradeResult,
    QuestionGrade,
    ReviewStatus,
    Rubric,
    RubricCriterion,
    StepGradeStatus,
)
from app.models.page import Page, RenderResult
from app.models.process import (
    PROCESS_STAGES,
    ProcessProgress,
    ProcessStage,
    QuestionScoreSummary,
)
from app.models.question_crops import LabelMode
from app.models.question_review import ReviewFlag
from app.models.report import PromptVersions, QuestionReportDetail
from app.models.question import (
    ExtractResult,
    ImageRegionRef,
    Question,
    SegmentationStatus,
    StudentStep,
)
from app.models.recognition import (
    DetectedRegion,
    PageRecognition,
    RecognizeResult,
    RecognizedQuestion,
    RecognizedStep,
    Region,
    SymbolicPayload,
)
from app.models.validation import (
    QuestionValidation,
    StepCheck,
    StepValidation,
    ValidateResult,
    ValidationMethod,
    ValidationStatus,
)
from app.services.grading.latex_report import LatexReportWriter
from app.services.grading.report import JsonCsvHtmlReporter
from app.services.grading.standard_comparer import StandardFinalComparer
from app.services.latex.builder import LatexBuilder
from app.services.math.equivalence import relations_equivalent, relations_form_equivalent
from app.services.math.hybrid_validator import HybridStepValidator
from app.services.math.parser import normalize_math_text, parse_math_step, parse_relation
from app.services.math.role_checks import numeric_relation_holds, zero_makers
from app.services.math.sympy_validator import SymPyStepValidator
from app.services.pdf.renderer import PyMuPdfRenderer
from app.services.latex.pdflatex_compiler import PdfLatexCompiler, resolve_pdflatex
from app.services.pipeline_factory import (
    build_ingest_kunci_controller,
    build_pdf_compiler,
    build_process_controller,
    build_validate_controller,
    current_prompt_versions,
    prepare_run_workspace,
)
from app.services.questions.extractor import QuestionExtractor
from app.services.standards.kunci_ingester import KunciIngester
from app.services.vision.factory import ink_params_from_config
from app.services.standards.standard_dir import resolve_standard_dir
from app.topics.registry import (
    assert_unique_standards_folders,
    get_pack,
    known_topic_ids,
    list_packs,
    resolve_pack,
)
from app.topics.runtime import get_active_pack, using_pack
from app.views.error_view import print_error, print_warning
from app.views.exit_view import (
    mark_interactive_session_done,
    prompt_continue_or_exit,
    reset_interactive_session_flag,
    wait_for_exit,
)
from app.views.prompt_view import (
    ask_yes_no,
    is_interactive,
    prompt_choice,
    read_line,
    wait_for_edit,
)
from app.views.question_crops_view import print_question_crops_missing
from app.views.result_view import print_grade_result, print_recognize_result, print_report_result
from app.views.style import bold, box, for_stream, visible_len
from tests.support.asserts import assert_all_valid, assert_contains, assert_step_statuses
from tests.support.builders import (
    MINI_KUNCI,
    Q1_KUNCI,
    make_figure,
    make_page,
    make_process_result,
    make_question,
    make_rational_inequality_question,
    make_report_metadata,
    make_report_question_grade,
    make_step,
    make_step_grade,
    make_validation,
    sample_rubric,
    write_fake_png_bytes,
    write_pdf,
    write_crop_workspace,
    write_png,
    write_question_dir,
    write_recognition,
    write_report_workspace,
)
from tests.support.fakes import (
    FakeClient,
    FakeLatexRunner,
    FakeProposer,
    RecordingJudge,
    RecordingMenuActions,
)
from tests.support.harness import (
    CliHarness,
    GradingWorkspace,
    ProcessHarness,
    make_llm_judge,
    make_ollama_client,
    make_recognizer,
    patch_inputs,
    patch_tty,
    q1_standard,
)


class TestConfig:

    def test_default_config_path_points_at_package_yaml(self) -> None:
        assert DEFAULT_CONFIG_PATH.name == 'config.yaml'
        assert DEFAULT_CONFIG_PATH.parent.name == 'config'
        assert DEFAULT_CONFIG_PATH.is_file()

    def test_load_config_default_reads_package_yaml(self) -> None:
        config = load_config()
        assert config.pdf.dpi == 200
        assert config.input.jawaban_dir == Path('data/input/jawaban')
        assert config.input.kunci_jawaban_dir == Path('data/input/kunci_jawaban')
        assert config.output.root_dir == Path('data/output')
        assert isinstance(config.output.root_dir, Path)
        assert config.grading.standards_root == Path('data/output/standards')
        assert config.grading.topic_id == '1.5'
        assert config.ollama.base_url == 'http://localhost:11434'
        assert config.recognition.ink.min_row_ink_ratio == 0.002
        ink = ink_params_from_config(config)
        assert ink.min_row_ink_ratio == 0.002
        assert ink.merge_gap_ratio == config.recognition.ink.merge_gap_ratio
        assert config.report.pdf.enabled is True
        assert config.report.pdf.passes == 2

    def test_report_pdf_config_from_yaml_and_env(self, tmp_path: Path, monkeypatch) -> None:
        path = tmp_path / 'config.yaml'
        path.write_text('report:\n  pdf:\n    enabled: false\n    passes: 1\n', encoding='utf-8')
        monkeypatch.delenv('PDFLATEX_PATH', raising=False)
        pdf = load_config(path).report.pdf
        assert (pdf.enabled, pdf.passes, pdf.pdflatex_path) == (False, 1, '')
        monkeypatch.setenv('PDFLATEX_PATH', 'C:/tex/pdflatex.exe')
        assert load_config(path).report.pdf.pdflatex_path == 'C:/tex/pdflatex.exe'

    def test_load_config_explicit_missing_path_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigNotFoundError, match='missing.yaml'):
            load_config(tmp_path / 'missing.yaml')
        assert load_config(DEFAULT_CONFIG_PATH).pdf.dpi == 200

    def test_cli_typo_in_config_path_exits_with_domain_error(self, tmp_path: Path, capsys) -> None:
        assert main(['--config', str(tmp_path / 'typo.yaml'), 'grade']) == 1
        assert_contains(capsys.readouterr().err, 'Config file not found', 'typo.yaml')

    def test_legacy_standard_dir_key_is_ignored_with_warning(self, tmp_path: Path, caplog) -> None:
        path = tmp_path / 'config.yaml'
        path.write_text('grading:\n  standard_dir: data/output/standards/exam_001\n', encoding='utf-8')
        with caplog.at_level('WARNING', logger='app.config'):
            config = load_config(path)
        assert config.grading.standards_root == Path('data/output/standards')
        assert 'grading.standard_dir is ignored' in caplog.text

    @pytest.mark.parametrize(
        ('topic_id', 'folder'),
        [('1.5', 'topik_1'), ('2', 'topik_2'), (None, 'topik_1'), ('  ', 'topik_1')],
    )
    def test_resolve_standard_dir_per_topic(self, tmp_path: Path, topic_id, folder: str) -> None:
        config = AppConfig(grading=GradingConfig(standards_root=tmp_path / 'std'))
        assert resolve_standard_dir(config, topic_id=topic_id) == tmp_path / 'std' / folder

    def test_resolve_standard_dir_explicit_override_wins(self, tmp_path: Path) -> None:
        config = AppConfig(grading=GradingConfig(standards_root=tmp_path / 'std', topic_id='2'))
        assert resolve_standard_dir(config, topic_id='1.5', standard_dir=tmp_path / 'x') == tmp_path / 'x'
        assert resolve_standard_dir(config) == tmp_path / 'std' / 'topik_2'

    def test_resolve_standard_dir_rejects_unknown_topic(self, tmp_path: Path) -> None:
        with pytest.raises(UnknownTopicError):
            resolve_standard_dir(AppConfig(), topic_id='99')

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

class TestMenuChoices:

    def test_parse_main_menu_choice(self) -> None:
        assert parse_main_menu_choice('1') == 'select_topic'
        assert parse_main_menu_choice('topic') == 'select_topic'
        assert parse_main_menu_choice('2') == 'ingest'
        assert parse_main_menu_choice('ingest') == 'ingest'
        assert parse_main_menu_choice('3') == 'propose_crops'
        assert parse_main_menu_choice('propose') == 'propose_crops'
        assert parse_main_menu_choice('4') == 'recrop'
        assert parse_main_menu_choice('recrop') == 'recrop'
        assert parse_main_menu_choice('5') == 'label_questions'
        assert parse_main_menu_choice('label-questions') == 'label_questions'
        assert parse_main_menu_choice('6') == 'relabel_questions'
        assert parse_main_menu_choice('relabel') == 'relabel_questions'
        assert parse_main_menu_choice('7') == 'finish'
        assert parse_main_menu_choice('proses') == 'finish'
        assert parse_main_menu_choice('8') == 'finish_questions'
        assert parse_main_menu_choice('lanjut-soal') == 'finish_questions'
        assert parse_main_menu_choice('9') == 'exit'
        assert parse_main_menu_choice('keluar') == 'exit'
        with pytest.raises(ValueError):
            parse_main_menu_choice('10')
        with pytest.raises(ValueError):
            parse_main_menu_choice('  ')

    def test_menu_table_drives_indexes_and_prompt(self) -> None:
        assert [parse_main_menu_choice(str(i)) for i in range(1, len(MAIN_MENU) + 1)] == list(MenuChoice)
        assert MAIN_MENU_PROMPT == f'Pilihan [1-{len(MAIN_MENU)}]: '
        assert parse_main_menu_choice('7') is MenuChoice.FINISH

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [('', True), (' Y ', True), ('yes', True), ('n', False), ('NO', False)],
    )
    def test_parse_yes_no(self, raw: str, expected: bool) -> None:
        assert parse_yes_no(raw) is expected

    def test_parse_yes_no_rejects_other(self) -> None:
        with pytest.raises(ValueError):
            parse_yes_no('maybe')

    @pytest.mark.parametrize(
        ('raw', 'expected'),
        [('1', 'continue'), ('ya', 'continue'), ('2', 'exit'), ('q', 'exit')],
    )
    def test_parse_continue_or_exit(self, raw: str, expected: str) -> None:
        assert parse_continue_or_exit(raw) == expected

    def test_parse_continue_or_exit_rejects_other(self) -> None:
        with pytest.raises(ValueError):
            parse_continue_or_exit('x')

    @pytest.mark.parametrize(
        ('ref', 'expected'),
        [('question_007', 'question_007'), ('question_7', 'question_007'), ('12', 'question_012')],
    )
    def test_parse_question_ref(self, ref: str, expected: str) -> None:
        assert parse_question_ref(ref) == expected

    @pytest.mark.parametrize('ref', ['question_x', '', 'question_000'])
    def test_parse_question_ref_rejects_bad(self, ref: str) -> None:
        with pytest.raises(ValueError):
            parse_question_ref(ref)

class TestRunLayout:

    def test_safe_run_name_keeps_spaces_and_replaces_illegal_chars(self) -> None:
        assert safe_run_name(Path('tugas 1 matsi_Fathi Rizky.pdf')) == 'tugas 1 matsi_Fathi Rizky'
        assert safe_run_name(Path('a*b?c<d>.pdf')) == 'a_b_c_d_'
        assert sanitize_run_name('nilai: 8|10') == 'nilai_ 8_10'
        assert safe_run_name(Path('trailing. .pdf')) == 'trailing'

    def test_safe_run_name_guards_reserved_and_empty(self) -> None:
        assert safe_run_name(Path('standards.pdf')) == 'standards_run'
        assert safe_run_name(Path('CON.pdf')) == 'CON_run'
        assert sanitize_run_name('...') == 'run'

    def test_build_run_layout_subdirs(self, tmp_path: Path) -> None:
        layout = build_run_layout(tmp_path, 'answer')
        assert layout.root == tmp_path / 'answer'
        assert layout.name == 'answer'
        assert layout.pages_dir == tmp_path / 'answer' / 'pages'
        assert layout.crops_dir == tmp_path / 'answer' / 'crops'
        assert layout.recognition_dir == tmp_path / 'answer' / 'recognition'
        assert layout.questions_dir == tmp_path / 'answer' / 'questions'
        assert layout.report_dir == tmp_path / 'answer'
        assert layout_for_pdf(tmp_path, Path('x/answer.pdf')) == layout

    def test_list_run_dirs_skips_standards_and_flat_legacy(self, tmp_path: Path) -> None:
        (tmp_path / 'standards' / 'exam_001').mkdir(parents=True)
        (tmp_path / 'pages').mkdir()
        (tmp_path / 'pages' / 'page_001.png').write_bytes(b'x')
        (tmp_path / 'beta' / 'questions').mkdir(parents=True)
        (tmp_path / 'Alpha' / 'pages').mkdir(parents=True)
        (tmp_path / 'empty').mkdir()
        assert [p.name for p in list_run_dirs(tmp_path)] == ['Alpha', 'beta']
        assert list_run_dirs(tmp_path / 'missing') == []

    def test_resolve_run_name_accepts_folder_or_pdf(self) -> None:
        assert resolve_run_name('smoke_inequality') == 'smoke_inequality'
        assert resolve_run_name('smoke_inequality.pdf') == 'smoke_inequality'
        assert resolve_run_name('data/input/jawaban/tugas 1.PDF') == 'tugas 1'

    def test_parse_run_choice(self, tmp_path: Path) -> None:
        runs = [tmp_path / 'alpha', tmp_path / 'beta']
        assert parse_run_choice(runs, '2') == runs[1]
        assert parse_run_choice(runs, 'ALPHA') == runs[0]
        with pytest.raises(ValueError):
            parse_run_choice(runs, 'gamma')

class TestOutputReset:

    def test_prepare_run_workspace_only_clears_own_run(self, tmp_path: Path) -> None:
        root = tmp_path / 'output'
        rubric = root / 'standards' / 'exam_001' / 'rubric.json'
        rubric.parent.mkdir(parents=True)
        rubric.write_text('{}', encoding='utf-8')
        other = build_run_layout(root, 'other')
        other.questions_dir.mkdir(parents=True)
        (other.root / 'report.json').write_text('{}', encoding='utf-8')
        layout = build_run_layout(root, 'answer')
        layout.pages_dir.mkdir(parents=True)
        (layout.pages_dir / 'page_001.png').write_bytes(b'x')
        (layout.root / 'report.json').write_text('{}', encoding='utf-8')
        removed = prepare_run_workspace(layout)
        assert sorted(removed) == ['pages', 'report.json']
        assert not (layout.pages_dir / 'page_001.png').exists()
        assert not (layout.root / 'report.json').exists()
        for directory in (layout.pages_dir, layout.crops_dir, layout.recognition_dir, layout.questions_dir):
            assert directory.is_dir()
        assert rubric.is_file()
        assert (other.root / 'report.json').is_file()
        assert other.questions_dir.is_dir()

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

    def test_prepare_run_workspace_preserve_crops(self, tmp_path: Path) -> None:
        layout = build_run_layout(tmp_path / 'output', 'answer')
        regions = write_crop_workspace(layout.pages_dir, layout.crops_dir)
        (layout.root / 'report.json').write_text('{}', encoding='utf-8')
        removed = prepare_run_workspace(layout, preserve_crops=True)
        assert 'crops' not in removed
        assert sorted(removed) == ['pages', 'report.json']
        assert regions.is_file()

    @pytest.mark.parametrize('preserve_crops', [False, True])
    def test_prepare_run_workspace_keeps_standards_inside_run(self, tmp_path: Path, preserve_crops: bool) -> None:
        layout = build_run_layout(tmp_path / 'output', 'answer')
        kept = layout.root / 'standards' / 'keep.json'
        kept.parent.mkdir(parents=True)
        kept.write_text('{}', encoding='utf-8')
        prepare_run_workspace(layout, preserve_crops=preserve_crops)
        assert kept.is_file()

    @pytest.mark.parametrize('inside_root', [True, False], ids=['crops-in-root', 'crops-outside-root'])
    def test_prepare_pipeline_workspace_keep_crops(self, tmp_path: Path, inside_root: bool) -> None:
        root = tmp_path / 'output'
        crops_dir = (root if inside_root else tmp_path) / 'my_crops'
        regions = write_crop_workspace(root / 'pages', crops_dir)
        removed = prepare_pipeline_workspace(
            root,
            pages_dir=root / 'pages',
            recognition_dir=root / 'recognition',
            questions_dir=root / 'questions',
            crops_dir=crops_dir,
            keep_crops=True,
        )
        assert regions.is_file()
        assert 'my_crops' not in removed
        assert not (root / 'pages' / 'pages.json').exists()

class TestStyleView:

    def test_box_pads_by_visible_width_with_ansi(self, monkeypatch) -> None:
        monkeypatch.setattr('app.views.style.colors_enabled', lambda: True)
        rendered = box([bold('Error'), 'plain message here'])
        assert '\033[1m' in rendered
        widths = {visible_len(line) for line in rendered.splitlines()}
        assert len(widths) == 1

    def test_print_error_keeps_multiline_message_inside_box(self, capsys) -> None:
        print_error(ValueError('line one\nline two is longer'))
        lines = capsys.readouterr().err.rstrip('\n').splitlines()
        assert [line[0] for line in lines] == ['┌', '│', '│', '│', '└']
        assert len({len(line) for line in lines}) == 1

    def test_redirected_stderr_gets_no_ansi_even_when_stdout_is_tty(self, monkeypatch, capsys) -> None:
        monkeypatch.setattr('app.views.style.colors_enabled', lambda: True)
        print_error(ValueError('boom'))
        print_warning('careful')
        err = capsys.readouterr().err
        assert '\033[' not in err
        assert_contains(err, 'boom', 'careful')

    def test_for_stream_keeps_ansi_for_tty(self) -> None:
        tty = MagicMock()
        tty.isatty.return_value = True
        closed = MagicMock()
        closed.isatty.side_effect = ValueError('closed')
        colored = '\033[31mx\033[0m'
        assert for_stream(colored, tty) == colored
        assert for_stream(colored, closed) == 'x'

    def test_question_crops_missing_names_real_folder(self, tmp_path: Path, capsys) -> None:
        print_question_crops_missing(tmp_path / 'crops')
        assert str(tmp_path / 'crops' / 'question_crops') in capsys.readouterr().err

class TestExitView:

    def test_wait_for_exit_skips_when_stdin_not_tty(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        patch_tty(monkeypatch, False)
        prompts = patch_inputs(monkeypatch)
        wait_for_exit()
        assert prompts == []

    def test_wait_for_exit_prompts_when_stdin_is_tty(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        patch_tty(monkeypatch)
        prompts = patch_inputs(monkeypatch, '')
        wait_for_exit()
        assert len(prompts) == 1
        assert 'Enter' in prompts[0]

    def test_wait_for_exit_ignores_eof(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        patch_tty(monkeypatch)
        monkeypatch.setattr('builtins.input', MagicMock(side_effect=EOFError))
        wait_for_exit()

    def test_wait_for_exit_skips_after_interactive_session(self, monkeypatch) -> None:
        reset_interactive_session_flag()
        mark_interactive_session_done()
        patch_tty(monkeypatch)
        prompts = patch_inputs(monkeypatch)
        wait_for_exit()
        assert prompts == []
        reset_interactive_session_flag()

    def test_prompt_continue_or_exit_non_tty(self, monkeypatch) -> None:
        patch_tty(monkeypatch, False)
        assert prompt_continue_or_exit() == 'exit'

    @pytest.mark.parametrize(
        ('answers', 'expected'),
        [(['1'], 'continue'), (['2'], 'exit'), (['x', '2'], 'exit')],
        ids=['continue', 'exit', 'retries_then_exit'],
    )
    def test_prompt_continue_or_exit_choice(self, monkeypatch, answers: list[str], expected: str) -> None:
        patch_tty(monkeypatch)
        patch_inputs(monkeypatch, *answers)
        assert prompt_continue_or_exit() == expected

class TestPromptView:

    @staticmethod
    def _answers(*answers: str):
        """``input_fn`` that replays ``answers`` then raises EOFError."""
        remaining = iter(answers)

        def input_fn(_prompt: str = '') -> str:
            try:
                return next(remaining)
            except StopIteration:
                raise EOFError from None
        return input_fn

    @pytest.mark.parametrize(
        ('answers', 'expected'),
        [([''], True), (['y'], True), (['n'], False), (['maybe', 'n'], False)],
        ids=['empty', 'yes', 'no', 'retries_then_no'],
    )
    def test_ask_yes_no(self, capsys, answers: list[str], expected: bool) -> None:
        assert ask_yes_no('OK? ', input_fn=self._answers(*answers)) is expected
        assert ('Please answer' in capsys.readouterr().out) is (len(answers) > 1)

    def test_ask_yes_no_eof_counts_as_yes(self) -> None:
        assert ask_yes_no('OK? ', input_fn=self._answers()) is True

    def test_read_line_returns_none_on_interrupt(self) -> None:
        def interrupted(_prompt: str = '') -> str:
            raise KeyboardInterrupt
        assert read_line('x', input_fn=interrupted) is None

    def test_wait_for_edit_prints_and_tolerates_eof(self, capsys) -> None:
        assert wait_for_edit('edit the file', input_fn=self._answers()) is False
        assert 'edit the file' in capsys.readouterr().out

    def test_wait_for_edit_enter_returns_true(self) -> None:
        assert wait_for_edit('edit', input_fn=self._answers('')) is True

    @staticmethod
    def _interrupted(_prompt: str = '') -> str:
        raise KeyboardInterrupt

    def test_ask_yes_no_ctrl_c_cancels(self) -> None:
        with pytest.raises(OperationCancelledError, match='Ctrl\\+C'):
            ask_yes_no('OK? ', input_fn=self._interrupted)

    def test_wait_for_edit_ctrl_c_cancels(self) -> None:
        with pytest.raises(OperationCancelledError):
            wait_for_edit('edit', input_fn=self._interrupted)

    def test_prompt_choice_ctrl_c_raises_domain_error(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidPdfSelectionError, match='cancelled'):
            prompt_choice(
                [tmp_path / 'a.pdf'],
                parse=parse_pdf_choice,
                error_cls=InvalidPdfSelectionError,
                on_selected=lambda _p: None,
                input_fn=self._interrupted,
            )

    def test_prompt_choice_retries_then_selects(self, tmp_path: Path, capsys) -> None:
        pdfs = [tmp_path / 'a.pdf', tmp_path / 'b.pdf']
        picked: list[Path] = []
        selected = prompt_choice(
            pdfs,
            parse=parse_pdf_choice,
            error_cls=InvalidPdfSelectionError,
            on_selected=picked.append,
            input_fn=self._answers('9', '2'),
        )
        assert selected == pdfs[1]
        assert picked == [pdfs[1]]
        assert 'Invalid PDF selection' in capsys.readouterr().err

    def test_prompt_choice_eof_raises_domain_error(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidPdfSelectionError, match='no input'):
            prompt_choice(
                [tmp_path / 'a.pdf'],
                parse=parse_pdf_choice,
                error_cls=InvalidPdfSelectionError,
                on_selected=lambda _p: None,
                input_fn=self._answers(),
            )

    def test_is_interactive(self, monkeypatch) -> None:
        patch_tty(monkeypatch, False)
        assert is_interactive() is False
        assert is_interactive(self._answers()) is True
        patch_tty(monkeypatch)
        assert is_interactive() is True

    def test_warnings_go_to_stderr(self, capsys) -> None:
        print_question_crops_missing(Path('crops'))
        captured = capsys.readouterr()
        assert captured.out == ''
        assert 'belum ditetapkan' in captured.err

class TestPdfRenderer:

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
        client = make_ollama_client(handler)
        content = client.generate_with_image('prompt', write_fake_png_bytes(tmp_path), 'vision-test')
        assert 'page_number' in content

    def test_generate_falls_back_to_thinking_when_content_empty(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={'message': {'content': '', 'thinking': '{"ok": true}'}, 'done_reason': 'length'})
        client = make_ollama_client(handler)
        content = client.generate_with_image('prompt', write_fake_png_bytes(tmp_path), 'vision-test')
        assert content == '{"ok": true}'

    def test_generate_retries_on_timeout_then_succeeds(self, tmp_path: Path) -> None:
        calls = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls['n'] += 1
            if calls['n'] == 1:
                raise httpx.ReadTimeout('slow')
            return httpx.Response(200, json={'message': {'content': '{"ok": true}'}})
        client = make_ollama_client(handler, timeout_seconds=1, max_retries=1)
        content = client.generate_with_image('prompt', write_fake_png_bytes(tmp_path), 'vision-test')
        assert content == '{"ok": true}'
        assert calls['n'] == 2

    def test_generate_timeout_exhausted(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout('slow')
        client = make_ollama_client(handler, timeout_seconds=1, max_retries=1)
        with pytest.raises(OllamaTimeoutError):
            client.generate_with_image('prompt', write_fake_png_bytes(tmp_path), 'vision-test')

    def test_generate_connection_error(self, tmp_path: Path) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError('offline')
        client = make_ollama_client(handler, timeout_seconds=1)
        with pytest.raises(OllamaUnavailableError):
            client.generate_with_image('prompt', write_fake_png_bytes(tmp_path), 'vision-test')

    def test_generate_text_only_sends_no_images(self) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert 'images' not in body['messages'][0]
            return httpx.Response(200, json={'message': {'content': '{"status":"uncertain","reason":"r","confidence":0.5}'}})
        client = make_ollama_client(handler)
        content = client.generate('prompt', 'reason-test')
        assert 'uncertain' in content

    def test_generate_does_not_retry_client_error(self) -> None:
        calls = {'n': 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls['n'] += 1
            return httpx.Response(404, text='model "nope" not found')
        client = make_ollama_client(handler, max_retries=2)
        with pytest.raises(OllamaRequestError, match='404'):
            client.generate('prompt', 'nope')
        assert calls['n'] == 1

    def test_generate_wraps_invalid_json_body(self) -> None:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='<html>proxy error</html>')
        client = make_ollama_client(handler)
        with pytest.raises(OllamaUnavailableError, match='invalid JSON'):
            client.generate('prompt', 'reason-test')

class TestVisionRecognizer:

    def test_recognizer_invalid_json_keeps_image(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / 'page_001.png', (40, 40), (255, 255, 255))
        out = tmp_path / 'recognition'
        client = FakeClient('not json at all')
        proposer = FakeProposer(region=Region(x=0, y=0, width=20, height=20))
        recognizer = make_recognizer(tmp_path, client, proposer=proposer)
        with pytest.raises(InvalidRecognitionJsonError) as exc_info:
            recognizer.recognize_page(image, 1)
        assert image.is_file()
        assert not (out / 'page_001_recognition.json').exists()
        assert 'response_preview' in str(exc_info.value)
        assert len(client.calls) == 3
        failed = list((tmp_path / 'crops' / 'page_001').glob('*_crop_math_failed.txt'))
        assert len(failed) == 1

    def test_recognizer_retries_then_accepts_valid_json(self, tmp_path: Path) -> None:
        image = write_png(tmp_path / 'page_001.png', (40, 40), (255, 255, 255))
        good = '{"question_number":1,"steps":[],"final_answer":"x>0","confidence":0.9}'
        client = FakeClient(['not json', 'still bad', good])
        proposer = FakeProposer(region=Region(x=0, y=0, width=20, height=20))
        page = make_recognizer(tmp_path, client, proposer=proposer).recognize_page(image, 1)
        assert page.questions[0].final_answer == 'x>0'
        assert len(client.calls) == 3

    def test_recognizer_requires_model(self, tmp_path: Path) -> None:
        image = tmp_path / 'page_001.png'
        image.write_bytes(b'png')
        recognizer = make_recognizer(tmp_path, FakeClient('{}'), model='')
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

        def recognize_page(_image: Path, page_number: int) -> PageRecognition:
            (recognition_dir / page_recognition_filename(page_number)).write_text('{}', encoding='utf-8')
            return PageRecognition(page_number=page_number, questions=[])

        recognizer.recognize_page.side_effect = recognize_page
        controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
        pages_dir = tmp_path / 'pages'
        pages_dir.mkdir()
        (pages_dir / 'page_001.png').write_bytes(b'x')
        pages = [Page(page_number=1, image='page_001.png', width=10, height=10)]
        result = controller.recognize_pages(pages, pages_dir, recognition_dir)
        assert result.output_dir == recognition_dir
        assert result.artifact_paths == [recognition_dir / 'page_001_recognition.json']

    def test_recognize_pages_omits_artifact_recognizer_never_wrote(self, tmp_path: Path, capsys) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        recognizer = MagicMock()
        recognizer.output_dir = recognition_dir
        recognizer.recognize_page.return_value = PageRecognition(page_number=1, questions=[])
        controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
        pages = [Page(page_number=1, image='page_001.png', width=10, height=10)]
        result = controller.recognize_pages(pages, tmp_path / 'pages', recognition_dir)
        assert result.artifact_paths == []
        print_recognize_result(result)
        assert '(tidak ada JSON)' in capsys.readouterr().out

    def test_recognize_pages_from_crops_calls_from_crops_api(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        recognizer = MagicMock()
        recognizer.output_dir = recognition_dir
        recognizer.recognize_page_from_crops.return_value = PageRecognition(
            page_number=1, questions=[]
        )
        controller = RecognizeController(renderer=MagicMock(), recognizer=recognizer)
        pages_dir = tmp_path / 'pages'
        pages_dir.mkdir()
        (pages_dir / 'page_001.png').write_bytes(b'x')
        pages = [Page(page_number=1, image='page_001.png', width=10, height=10)]
        result = controller.recognize_pages(
            pages, pages_dir, recognition_dir, from_crops=True
        )
        assert len(result.pages) == 1
        recognizer.recognize_page_from_crops.assert_called_once()
        recognizer.recognize_page.assert_not_called()

class TestQuestionMergeExtract:

    def test_extract_controller_force_without_runner_is_wiring_error(self, tmp_path: Path) -> None:
        recognition = tmp_path / 'recognition'
        recognition.mkdir()
        write_recognition(recognition / page_recognition_filename(1), PageRecognition(page_number=1, questions=[]))
        controller = ExtractController(extractor=MagicMock())
        with pytest.raises(ValueError, match='recognize_runner'):
            controller.extract(tmp_path / 'recognition', tmp_path / 'q', force_recognize=True)

    def test_extract_controller_without_json_or_runner_reports_missing(self, tmp_path: Path) -> None:
        with pytest.raises(RecognitionNotFoundError):
            ExtractController(extractor=MagicMock()).extract(tmp_path / 'empty', tmp_path / 'q')

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
        write_recognition(recognition_dir / 'page_001_recognition.json', PageRecognition(page_number=1, questions=[RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='x>0', latex='')], final_answer='x>0', latex_document='DOC_A'), RecognizedQuestion(question_number=0, steps=[RecognizedStep(step_number=1, raw_text='x<1', latex='')], final_answer='x<1', latex_document='DOC_B')]))
        output_dir = tmp_path / 'questions'
        QuestionExtractor().extract_from_dir(recognition_dir, output_dir)
        assert (output_dir / 'question_001' / 'latex_source.tex').read_text(encoding='utf-8').strip() == 'DOC_A'
        assert (output_dir / 'question_002' / 'latex_source.tex').read_text(encoding='utf-8').strip() == 'DOC_B'

    def test_extractor_writes_question_json(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        write_recognition(
            recognition_dir / 'page_001_recognition.json',
            PageRecognition(
                page_number=1,
                questions=[
                    RecognizedQuestion(
                        question_number=1,
                        steps=[
                            RecognizedStep(
                                step_number=1,
                                raw_text='2x<8',
                                symbolic=SymbolicPayload(kind='relation', repr='2*x<8'),
                            )
                        ],
                        final_answer='x<4',
                        latex_document=r'\begin{aligned}2x<8\end{aligned}',
                    )
                ],
                prompt_version='recognition-v1',
                model='test',
            ),
        )
        output_dir = tmp_path / 'questions'
        result = QuestionExtractor().extract_from_dir(recognition_dir, output_dir)
        assert len(result.questions) == 1
        artifact = output_dir / 'question_001' / 'question.json'
        assert artifact.is_file()
        assert (output_dir / 'question_001' / 'recognition_pages.json').is_file()
        assert (output_dir / 'question_001' / 'latex_source.tex').is_file()
        payload = json.loads(artifact.read_text(encoding='utf-8'))
        assert payload['student_final_answer'] == 'x<4'
        assert payload['question_id'] == 'question_001'
        assert '\\\\begin{aligned}' not in artifact.read_text(encoding='utf-8')
        assert result.questions[0].student_steps[0].latex == ''
        assert result.artifact_paths[0] == artifact

    def test_extractor_missing_recognition_dir(self, tmp_path: Path) -> None:
        with pytest.raises(RecognitionNotFoundError):
            QuestionExtractor().extract_from_dir(tmp_path / 'missing', tmp_path / 'out')

    def test_extractor_empty_questions(self, tmp_path: Path) -> None:
        recognition_dir = tmp_path / 'recognition'
        recognition_dir.mkdir()
        write_recognition(recognition_dir / 'page_001_recognition.json', PageRecognition(page_number=1, questions=[]))
        with pytest.raises(EmptyExtractionError):
            QuestionExtractor().extract_from_dir(recognition_dir, tmp_path / 'out')


class TestQuestionReview:

    class EditingInput:
        """Scripted answers; a callable answer edits files then counts as Enter."""

        def __init__(self, *answers) -> None:
            self._answers = list(answers)
            self.prompts: list[str] = []

        def __call__(self, prompt: str = '') -> str:
            self.prompts.append(prompt)
            answer = self._answers.pop(0)
            if callable(answer):
                answer()
                return ''
            return answer

    @staticmethod
    def _workspace(tmp_path: Path, *, latex_source: str = '') -> tuple[Path, Path]:
        questions_dir = tmp_path / 'questions'
        question = make_question(steps=[make_step(1, raw_text='x<4', symbolic_repr='x < 4', confidence=0.9)])
        path = write_question_dir(questions_dir, question, latex_source=latex_source)
        return questions_dir, path

    @staticmethod
    def _rewrite_repr(path: Path, new_repr: str) -> None:
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload['student_steps'][0]['symbolic']['repr'] = new_repr
        path.write_text(json.dumps(payload), encoding='utf-8')

    @pytest.mark.parametrize(
        ('step', 'expected'),
        [
            (make_step(1, raw_text='x<4', symbolic_repr='x < 4', confidence=0.9), []),
            (make_step(1, raw_text='x<4', symbolic_repr='x < 4', confidence=0.5), [ReviewFlag.LOW_CONFIDENCE]),
            (make_step(1, raw_text='x<[uncertain]', symbolic_repr='x < 4', confidence=0.9), [ReviewFlag.UNCERTAIN_MARK]),
            (make_step(1, raw_text='x<4', confidence=0.9), [ReviewFlag.MISSING_SYMBOLIC]),
            (make_step(1, raw_text='garis', symbolic_repr=SymbolicPayload(kind='figure'), confidence=0.9), []),
            (make_step(1, raw_text='garis bilangan', role='figure', confidence=0.9), []),
        ],
        ids=['clean', 'low-confidence', 'uncertain-mark', 'missing-symbolic', 'figure-without-repr', 'figure-role'],
    )
    def test_review_flags(self, step: StudentStep, expected: list[ReviewFlag]) -> None:
        flagged = review_flags(make_question(steps=[step]), min_confidence=0.8)
        assert [f.flags for f in flagged] == ([expected] if expected else [])

    def test_accept_keeps_artifacts(self, tmp_path: Path) -> None:
        questions_dir, _ = self._workspace(tmp_path, latex_source='x<4')
        answers = self.EditingInput('y')
        result = QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, input_fn=answers)
        assert result.ok
        assert result.edited_ids == []
        assert answers.prompts == ['Transkripsi OK? [y/n]: ']
        assert (questions_dir / 'question_001' / 'latex_source.tex').is_file()

    def test_edit_reloads_and_drops_latex_source(self, tmp_path: Path, capsys) -> None:
        questions_dir, path = self._workspace(tmp_path, latex_source='x<4')
        answers = self.EditingInput('n', lambda: self._rewrite_repr(path, 'x < 5'), 'y')
        result = QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, input_fn=answers)
        assert result.edited_ids == ['question_001']
        assert result.items[0].question.student_steps[0].symbolic.repr == 'x < 5'
        assert not (questions_dir / 'question_001' / 'latex_source.tex').exists()
        assert 'question_001' in capsys.readouterr().out

    def test_broken_json_waits_for_fix(self, tmp_path: Path) -> None:
        questions_dir, path = self._workspace(tmp_path)
        good = path.read_text(encoding='utf-8')
        path.write_text('{broken', encoding='utf-8')
        answers = self.EditingInput(lambda: path.write_text(good, encoding='utf-8'), 'y')
        result = QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, input_fn=answers)
        assert result.ok
        assert answers.prompts[-1] == 'Transkripsi OK? [y/n]: '
        assert result.edited_ids == ['question_001']

    @pytest.mark.parametrize(
        ('json_offset', 'expected'),
        [(10, ['question_001']), (0, []), (-10, [])],
        ids=['json-newer', 'same-time', 'sidecar-newer'],
    )
    def test_prune_stale_latex_sources(self, tmp_path: Path, json_offset: int, expected: list[str]) -> None:
        questions_dir, path = self._workspace(tmp_path, latex_source='x<4')
        sidecar = path.parent / 'latex_source.tex'
        base = sidecar.stat().st_mtime
        os.utime(sidecar, (base, base))
        os.utime(path, (base + json_offset, base + json_offset))
        before = path.read_bytes()
        assert QuestionReviewController(min_confidence=0.8).prune_stale_latex_sources(questions_dir) == expected
        assert sidecar.exists() is (not expected)
        assert path.read_bytes() == before

    def test_force_yes_skips_prompt(self, tmp_path: Path) -> None:
        questions_dir, _ = self._workspace(tmp_path)
        answers = self.EditingInput()
        result = QuestionReviewController(min_confidence=0.8).review_loop(
            questions_dir, force_yes=True, input_fn=answers
        )
        assert result.ok
        assert answers.prompts == []

    @pytest.mark.parametrize(
        'corrupt',
        [
            lambda path: path.write_text('{broken', encoding='utf-8'),
            lambda path: path.write_text(
                make_question(number=2, steps=[make_step(1, symbolic_repr='x < 4')]).model_dump_json(),
                encoding='utf-8',
            ),
        ],
        ids=['unparseable', 'id-mismatch'],
    )
    def test_force_yes_raises_on_invalid(self, tmp_path: Path, corrupt) -> None:
        questions_dir, path = self._workspace(tmp_path)
        corrupt(path)
        with pytest.raises(QuestionArtifactsInvalidError, match='question_001'):
            QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, force_yes=True)

    @staticmethod
    def _edit_payload(path: Path, **changes) -> None:
        payload = json.loads(path.read_text(encoding='utf-8'))
        payload.update(changes)
        path.write_text(json.dumps(payload), encoding='utf-8')

    @pytest.mark.parametrize(
        ('changes', 'message'),
        [
            ({'question_number': 2}, 'question_number 2'),
            ({'question_number': 0}, 'question_number must be >= 1'),
        ],
        ids=['number-mismatch', 'number-zero'],
    )
    def test_collect_rejects_number_not_matching_folder(self, tmp_path: Path, changes: dict, message: str) -> None:
        questions_dir, path = self._workspace(tmp_path)
        self._edit_payload(path, **changes)
        result = QuestionReviewController(min_confidence=0.8).collect(questions_dir)
        assert not result.ok
        assert message in result.errors[0]

    def test_collect_rejects_duplicate_step_numbers(self, tmp_path: Path) -> None:
        questions_dir = tmp_path / 'questions'
        question = make_question(steps=[make_step(1, symbolic_repr='x < 4'), make_step(1, symbolic_repr='x < 5')])
        write_question_dir(questions_dir, question)
        result = QuestionReviewController(min_confidence=0.8).collect(questions_dir)
        assert result.errors == ['question_001/question.json: step_number duplikat: 1']

    def test_eof_while_invalid_raises_instead_of_looping(self, tmp_path: Path) -> None:
        questions_dir, path = self._workspace(tmp_path)
        path.write_text('{broken', encoding='utf-8')

        def eof(_prompt: str = '') -> str:
            raise EOFError

        with pytest.raises(QuestionArtifactsInvalidError):
            QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, input_fn=eof)

    def test_ctrl_c_at_confirm_cancels(self, tmp_path: Path) -> None:
        questions_dir, _ = self._workspace(tmp_path)

        def interrupted(_prompt: str = '') -> str:
            raise KeyboardInterrupt

        with pytest.raises(OperationCancelledError):
            QuestionReviewController(min_confidence=0.8).review_loop(questions_dir, input_fn=interrupted)


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
        write_recognition(recognition_dir / 'page_001_recognition.json', page)
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
        question = make_question('2x - 3 < 5', '2x < 8', 'x < 4', final='Jawaban akhir: x < 4', raw_text='...')
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
        question = make_question('x < 4', final='x < 4', raw_text='keep_me_raw')
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

    def test_build_student_latex_figure_path_posix_and_caption_one_line(self) -> None:
        figure = make_figure(caption='line one\nline two', path='data\\output\\run\\crops\\page_001\\a.png')
        tex = build_student_latex(make_question('x < 4', figures=[figure]))
        assert r'\includegraphics{data/output/run/crops/page_001/a.png}' in tex
        assert '% figure: line one line two' in tex

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
        validator = SymPyStepValidator()
        assert_all_valid(validator.validate_question(make_question('2x+5=15', '2x=10', 'x=5', final='x=5')))
        invalid_result = validator.validate_question(make_question('2x+5=15', '2x=20', number=2))
        assert invalid_result.steps[1].status == ValidationStatus.INVALID

    @pytest.mark.parametrize(
        ('latex_steps', 'final_answer'),
        [
            (['2x-3<5', '2x<8', 'x<4'], 'Jawaban akhir: x < 4'),
            (['|x-1|<3', '-3<x-1<3', '-2<x<4'], '-2 < x < 4'),
            (['|x|>2', 'x<-2 or x>2'], 'x < -2 or x > 2'),
            (['x \\neq 1', 'x<1 or x>1'], 'x \\in (-\\infty,1) \\cup (1,\\infty)'),
            (['x \\in (1,3)', '1<x<3'], '1 < x < 3'),
            (['x >= -10/3', 'Interval(-10/3, oo)'], 'Interval(-10/3, oo)'),
        ],
        ids=['linear', 'abs_less', 'abs_greater_or', 'domain_neq', 'domain_interval', 'interval_pair'],
    )
    def test_validator_valid_chain(self, latex_steps: list[str], final_answer: str) -> None:
        assert_all_valid(SymPyStepValidator().validate_question(make_question(*latex_steps, final=final_answer)))

    def test_validator_unparseable_is_uncertain(self) -> None:
        result = SymPyStepValidator().validate_question(make_question('', raw_text='lihat gambar'))
        assert_step_statuses(result, ValidationStatus.UNCERTAIN)

    def test_validator_prefers_symbolic_over_raw_noise(self) -> None:
        steps = [
            make_step(i, raw_text='noise', symbolic_repr=repr_)
            for i, repr_ in enumerate(['2*x-3<5', '2*x<8', 'x<4'], start=1)
        ]
        question = make_question(steps=steps, final_symbolic='x<4')
        assert_all_valid(SymPyStepValidator().validate_question(question))

    def test_validator_figure_step_is_uncertain(self) -> None:
        figure = make_step(1, raw_text='graph', symbolic_repr=SymbolicPayload(kind='figure', repr=''))
        result = SymPyStepValidator().validate_question(make_question(steps=[figure]))
        assert_step_statuses(result, ValidationStatus.UNCERTAIN)

    def test_validator_abs_wrong_transform_is_invalid(self) -> None:
        result = SymPyStepValidator().validate_question(make_question('|x|<2', 'x<2', number=2))
        assert_step_statuses(result, ValidationStatus.VALID, ValidationStatus.INVALID)

class TestLlmHybrid:

    @pytest.mark.parametrize(
        ('raw_text', 'verdict', 'expected'),
        [
            ('lihat gambar', {'status': 'uncertain', 'reason': 'unclear', 'confidence': 0.3}, ValidationStatus.UNCERTAIN),
            ('not parseable', {'status': 'valid', 'reason': 'looks ok', 'confidence': 0.7}, ValidationStatus.VALID),
        ],
        ids=['preserves_llm_uncertain', 'llm_marks_valid_when_sympy_uncertain'],
    )
    def test_hybrid_llm_decides_when_sympy_uncertain(self, raw_text: str, verdict: dict, expected: ValidationStatus) -> None:
        judge = RecordingJudge(verdict)
        result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(make_question('', raw_text=raw_text))
        assert_step_statuses(result, expected)
        assert result.steps[0].method == ValidationMethod.LLM
        assert judge.calls

    def test_hybrid_does_not_overwrite_sympy_invalid(self) -> None:
        judge = RecordingJudge({'status': 'valid', 'reason': 'should not be used', 'confidence': 0.9})
        result = HybridStepValidator(SymPyStepValidator(), judge).validate_question(make_question('2x+5=15', '2x=20'))
        assert result.steps[1].status == ValidationStatus.INVALID
        assert result.steps[1].method == ValidationMethod.SYMPY
        assert judge.calls == []

    def test_hybrid_accepts_step_validator_port(self) -> None:
        """Hybrid depends on StepValidator ABC, not concrete SymPy class."""
        class AlwaysUncertain(StepValidator):
            def validate_question(self, question: Question) -> QuestionValidation:
                steps = [
                    StepValidation(
                        step_number=s.step_number,
                        status=ValidationStatus.UNCERTAIN,
                        method=ValidationMethod.SYMPY,
                        reason='stub',
                    )
                    for s in question.student_steps
                ]
                return QuestionValidation(
                    question_number=question.question_number,
                    question_id=question.question_id,
                    steps=steps,
                )

        judge = RecordingJudge({'status': 'valid', 'reason': 'ok', 'confidence': 0.8})
        result = HybridStepValidator(AlwaysUncertain(), judge).validate_question(make_question('', raw_text='x'))
        assert result.steps[0].status == ValidationStatus.VALID
        assert result.steps[0].method == ValidationMethod.LLM
        assert judge.calls

    def test_llm_judge_invalid_json_stays_uncertain(self, tmp_path: Path) -> None:
        judge = make_llm_judge(tmp_path, 'not-json')
        result = judge.judge_transition(step_number=2, previous=make_step(1, 'a', raw_text='a'), current=make_step(2, raw_text='??'))
        assert result.status == ValidationStatus.UNCERTAIN
        assert result.method == ValidationMethod.LLM

    def test_llm_judge_salvages_broken_reason_quotes(self, tmp_path: Path) -> None:
        broken = (
            '{\n'
            '  "status": "invalid",\n'
            '  "reason": "set [-10/3, oo) became "x>1" incorrectly",\n'
            '  "confidence": 0.91\n'
            '}'
        )
        judge = make_llm_judge(tmp_path, broken)
        result = judge.judge_transition(step_number=2, previous=make_step(1, 'a', raw_text='a'), current=make_step(2, 'b', raw_text='b'))
        assert result.status == ValidationStatus.INVALID
        assert result.method == ValidationMethod.LLM
        assert 'x>1' in result.reason
        assert result.confidence == pytest.approx(0.91)

    def test_llm_judge_keeps_verdict_when_confidence_out_of_range(self, tmp_path: Path) -> None:
        judge = make_llm_judge(tmp_path, '{"status": "valid", "reason": "ok", "confidence": 85}')
        result = judge.judge_transition(step_number=2, previous=make_step(1, 'a', raw_text='a'), current=make_step(2, 'b', raw_text='b'))
        assert result.status == ValidationStatus.VALID
        assert result.confidence is None

    def test_validation_artifact_round_trip(self, tmp_path: Path) -> None:
        question = make_question('2x+5=15', '2x=10')
        qdir = tmp_path / question.question_id
        qdir.mkdir()
        qpath = qdir / 'question.json'
        qpath.write_text(question.model_dump_json(), encoding='utf-8')
        (tmp_path / 'question_002').mkdir()
        (tmp_path / 'question_002' / 'question.json').write_text('{broken', encoding='utf-8')
        assert question_artifact_paths(tmp_path)[0] == qpath
        loaded = load_question_artifact(qpath)
        assert loaded == question
        with pytest.raises(ValueError):
            load_question_artifact(tmp_path / 'question_002' / 'question.json')
        validation = SymPyStepValidator().validate_question(loaded)
        written = write_validation_artifact(qdir, validation)
        assert written == qdir / 'validation.json'
        assert QuestionValidation.model_validate_json(written.read_text(encoding='utf-8')) == validation

    def test_hybrid_sends_reference_step_and_check_kind(self) -> None:
        question = make_rational_inequality_question(replace={11: 'x < -4'})
        judge = RecordingJudge({'status': 'valid', 'reason': 'sign ok', 'confidence': 0.8})
        validator = HybridStepValidator(
            SymPyStepValidator(step_checks=get_pack('1.5').step_checks),
            judge,
            step_checks=get_pack('1.5').step_checks,
        )
        result = validator.validate_question(question)
        assert_all_valid(result)
        assert len(judge.calls) == 1
        kind, kwargs = judge.calls[0]
        assert kind == 'transition'
        assert kwargs['step_number'] == 11
        assert kwargs['previous'].step_number == 6
        assert 'Check kind: numeric_eval' in kwargs['extra_context']

class TestRoleAwareValidation:
    """Role steps are checked against the latest algebra step, not the step before them."""

    def _validate(self, question: Question) -> QuestionValidation:
        return SymPyStepValidator(step_checks=get_pack('1.5').step_checks).validate_question(question)

    def test_reference_indices_skip_role_steps(self) -> None:
        roles = ['algebra', 'algebra', 'critical_points', 'critical_points', 'hp', 'sign_chart', 'figure']
        checks = step_checks_for(roles, get_pack('1.5').step_checks)
        assert reference_indices(checks) == [None, 0, 1, 1, 1, 1, 1]
        assert final_reference_index(checks) == 1

    def test_hand_edited_roles_match_case_insensitively(self) -> None:
        mapping = get_pack('1.5').step_checks
        assert step_checks_for([' HP ', 'Critical_Points'], mapping) == step_checks_for(
            ['hp', 'critical_points'], mapping
        )

    def test_unmapped_roles_chain_like_before(self) -> None:
        checks = step_checks_for([None, 'unknown', 'hp'], None)
        assert checks == [StepCheck.TRANSITION] * 3
        assert reference_indices(checks) == [None, 0, 1]
        assert final_reference_index(checks) == 2
        assert final_reference_index([]) is None

    def test_zero_makers_and_numeric_relation(self) -> None:
        x = Symbol('x')
        reduced = parse_relation('-3*x/((x+4)*(x-2)) < 0', x)
        assert zero_makers(reduced, x) == FiniteSet(-4, 0, 2)
        assert numeric_relation_holds(parse_relation('(-3*3)/((3+4)*(3-2)) = -9/7', x)) is True
        assert numeric_relation_holds(parse_relation('(-3*3)/((3+4)*(3-2)) = -6/7', x)) is False
        assert numeric_relation_holds(parse_relation('x < -4', x)) is None

    def test_rational_inequality_solution_is_valid(self) -> None:
        result = self._validate(make_rational_inequality_question())
        assert_all_valid(result)
        assert result.steps[6].reason.startswith('zero_makers:')
        assert result.steps[9].reason.startswith('solution_set:')
        assert result.steps[10].reason.startswith('numeric_eval:')

    @pytest.mark.parametrize(
        ('replace', 'step_number'),
        [
            ({7: 'x-3=0 and x=3'}, 7),
            ({8: 'x+4=0 and x=4'}, 8),
            ({12: '(-3*(-2))/((-2+4)*(-2-2)) = 3/4'}, 12),
            ({10: '(-4, 0) U (0, 2)'}, 10),
        ],
        ids=['wrong_critical_point', 'inconsistent_implication', 'wrong_sign_test', 'wrong_hp'],
    )
    def test_wrong_role_step_is_invalid(self, replace: dict[int, str], step_number: int) -> None:
        result = self._validate(make_rational_inequality_question(replace=replace))
        invalid = [s.step_number for s in result.steps if s.status == ValidationStatus.INVALID]
        assert invalid == [step_number]

    def test_wrong_final_answer_is_invalid(self) -> None:
        result = self._validate(make_rational_inequality_question(final_symbolic='(-4, 0) U (0, 2)'))
        assert result.final_answer_status is not None
        assert result.final_answer_status.status == ValidationStatus.INVALID

    def test_without_step_checks_keeps_previous_step_chaining(self) -> None:
        result = SymPyStepValidator().validate_question(make_rational_inequality_question())
        assert result.steps[7].status == ValidationStatus.INVALID

class TestScoreAggregate:

    @staticmethod
    def _grade(validation: QuestionValidation, rubric: Rubric | None = None, **kwargs) -> QuestionGrade:
        return aggregate_question_grade(
            question_id=validation.question_id,
            question_number=validation.question_number,
            validation=validation,
            rubric=rubric or sample_rubric(),
            **kwargs,
        )

    def test_allocate_step_max_scores_uses_student_count_only(self) -> None:
        # Non-final pool = 2+4+2 = 8; five student steps get full pool.
        per_step, final_max, part_max = allocate_step_max_scores(sample_rubric(), 5)
        assert final_max == pytest.approx(2.0)
        assert part_max == {}
        assert len(per_step) == 5
        assert sum(per_step) == pytest.approx(8.0)
        grade = self._grade(make_validation(*[ValidationStatus.VALID] * 5))
        assert grade.score == pytest.approx(10.0)
        assert sum(s.max_score for s in grade.steps) == pytest.approx(8.0)

    def test_aggregate_full_credit(self) -> None:
        grade = self._grade(make_validation(*[ValidationStatus.VALID] * 4))
        assert grade.score == pytest.approx(10.0)
        assert grade.maximum_score == 10
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT
        assert all((s.score == pytest.approx(2.0) for s in grade.steps))
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(2.0)

    def test_aggregate_partial_credit_not_zero_total(self) -> None:
        validation = make_validation(
            ValidationStatus.VALID,
            (ValidationStatus.INVALID, 'algebra error'),
            ValidationStatus.VALID,
            ValidationStatus.VALID,
            final=(ValidationStatus.INVALID, 'wrong answer'),
        )
        grade = self._grade(validation)
        assert grade.score == pytest.approx(6.0)
        assert 0 < grade.score < grade.maximum_score
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT
        assert grade.steps[2].error_type.value == 'carry_forward'

    def test_aggregate_uncertain_requires_review(self) -> None:
        validation = make_validation(
            ValidationStatus.VALID,
            (ValidationStatus.UNCERTAIN, 'ambiguous'),
            ValidationStatus.VALID,
            ValidationStatus.VALID,
        )
        grade = self._grade(validation)
        assert grade.score == pytest.approx(9.0)
        assert grade.review_status == ReviewStatus.REVIEW_REQUIRED
        assert grade.steps[1].status.value == 'review'

    def test_aggregate_standard_only_final_no_fake_full_consistency(self) -> None:
        grade = self._grade(
            make_validation(ValidationStatus.VALID, final=None),
            standard_final_status=ValidationStatus.VALID,
            standard_final_reason='matches',
        )
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(2.0)
        assert 'standard compare only' in grade.final_answer.feedback

    def test_aggregate_standard_step_mismatch_keeps_consistency_credit(self) -> None:
        grade = self._grade(
            make_validation(*[ValidationStatus.VALID] * 3),
            standard_final_status=ValidationStatus.VALID,
            standard_final_reason='matches',
            standard_step_results={
                1: (ValidationStatus.VALID, 'step matches standard'),
                2: (ValidationStatus.INVALID, 'step differs from standard'),
                3: (ValidationStatus.VALID, 'step matches standard'),
            },
        )
        # Soft-align mismatch is audit-only; consistency VALID still earns full step credit.
        assert grade.steps[1].score == pytest.approx(grade.steps[0].score)
        assert 'standard:' in grade.steps[1].feedback
        assert grade.standard_step_statuses == {'1': 'valid', '2': 'invalid', '3': 'valid'}
        assert grade.score == pytest.approx(10.0)
        assert grade.review_status == ReviewStatus.AUTO_ACCEPT

    def test_aggregate_unaligned_step_keeps_consistency_credit(self) -> None:
        grade = self._grade(
            make_validation(ValidationStatus.VALID, ValidationStatus.VALID),
            standard_step_results={1: (ValidationStatus.VALID, 'step matches standard')},
        )
        assert grade.steps[1].score == pytest.approx(grade.steps[0].score)
        assert 'no matching standard step' in grade.steps[1].feedback
        assert grade.standard_step_statuses == {'1': 'valid', '2': 'invalid'}

    def test_aggregate_standard_mismatch_zeros_final_only(self) -> None:
        grade = self._grade(
            make_validation(*[ValidationStatus.VALID] * 4),
            standard_final_status=ValidationStatus.INVALID,
            standard_final_reason='differs from standard',
        )
        assert grade.score == pytest.approx(8.0)
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(0.0)
        assert grade.standard_final_status == ValidationStatus.INVALID
        assert 'standard:' in grade.final_answer.feedback

    def test_part_scoring_critical_points_and_figure(self) -> None:
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
        validation = make_validation(ValidationStatus.VALID, ValidationStatus.VALID, number=4)

        def grade_with(part_statuses: dict) -> QuestionGrade:
            return self._grade(
                validation, rubric, standard_final_status=ValidationStatus.VALID, part_statuses=part_statuses
            )

        grade = grade_with({
            'critical_points': (ValidationStatus.VALID, 'matches milestone'),
            'figure': (ValidationStatus.VALID, 'figure step present'),
        })
        assert grade.score == pytest.approx(10.0)
        part_feedback = ' '.join(s.feedback for s in grade.steps)
        assert 'part:critical_points' in part_feedback
        assert 'part:figure' in part_feedback
        assert grade.part_statuses == {'critical_points': 'valid', 'figure': 'valid'}
        assert sum(1 for s in grade.steps if s.step_number > 0) == 2

        miss = grade_with({
            'critical_points': (ValidationStatus.INVALID, 'no match'),
            'figure': (ValidationStatus.INVALID, 'no figure step'),
        })
        # algebra 3 + final 3 = 6; critical/figure zeroed
        assert miss.score == pytest.approx(6.0)

        partial = grade_with({
            'critical_points': (ValidationStatus.INVALID, 'matches 1/3 of milestone critical_points', 1 / 3),
            'figure': (ValidationStatus.VALID, 'figure step present'),
        })
        # algebra 3 + critical 2*(1/3) rounded + figure 2 + final 3
        assert partial.score == pytest.approx(8.6667, abs=1e-4)

class TestStepGrader:

    def test_step_grader_writes_grading_json_without_mutating_question(self, tmp_path: Path) -> None:
        workspace = GradingWorkspace(tmp_path)
        qpath = workspace.add_question(
            make_question('x-4<0', 'x<4', final='x<4', raw_text='keep'),
            make_validation(ValidationStatus.VALID, ValidationStatus.VALID),
        )
        original = qpath.read_text(encoding='utf-8')
        grade = workspace.grade()
        assert (qpath.parent / 'grading.json').is_file()
        assert grade.grades[0].score == pytest.approx(10.0)
        assert qpath.read_text(encoding='utf-8') == original
        assert 'keep' in original

    def test_step_grader_missing_validation_errors(self, tmp_path: Path) -> None:
        workspace = GradingWorkspace(tmp_path)
        workspace.add_question(make_question('x<4'))
        with pytest.raises(ValidationNotFoundError):
            workspace.grade()

    @pytest.mark.parametrize(
        ('final', 'standard_status', 'score', 'final_score'),
        [
            ('x<4', ValidationStatus.VALID, 10.0, 2.0),
            ('x<5', ValidationStatus.INVALID, 8.0, 0.0),
        ],
        ids=['match', 'mismatch'],
    )
    def test_step_grader_with_standard(
        self, tmp_path: Path, final: str, standard_status: ValidationStatus, score: float, final_score: float
    ) -> None:
        workspace = GradingWorkspace(tmp_path)
        workspace.add_solution()
        workspace.add_question(
            make_question('2x-3<5', 'x<4', final=final),
            make_validation(ValidationStatus.VALID, ValidationStatus.VALID),
        )
        grade = workspace.grade(with_comparer=True).grades[0]
        assert grade.standard_final_status == standard_status
        assert grade.final_answer is not None
        assert grade.final_answer.score == pytest.approx(final_score)
        assert grade.score == pytest.approx(score)

class TestStandardExtract:

    def test_extract_final_answer_from_tex(self) -> None:
        tex = '% header\n\\begin{aligned}\nx &< 4\n\\end{aligned}\n\n% final answer\nx < 4\n'
        assert extract_final_answer_from_tex(tex) == 'x < 4'
        assert extract_final_answer_from_tex('no marker here') is None

    def test_extract_solution_steps_from_tex_q001(self, tmp_path: Path) -> None:
        tex = standard_solution_path(q1_standard(tmp_path), 1).read_text(encoding='utf-8')
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
        path = standard_solution_path(Path('standards/exam_001'), 1)
        assert path.as_posix().endswith('solutions/question_001.tex')

    def test_match_schema_prefers_symbolic(self) -> None:
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
        assert standard_step_texts(q, tex) == ['x > 0', 'x > 2']

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

class TestStandardComparer:

    def test_comparer_match_q1_standard(self, tmp_path: Path) -> None:
        question = make_question(
            r'2-3x\leq12', r'x\geq-\frac{10}{3}', final=r'\left[-\frac{10}{3}, \infty\right)'
        )
        result = StandardFinalComparer(q1_standard(tmp_path)).compare(question)
        assert result is not None
        status, reason = result
        assert status == ValidationStatus.VALID
        assert 'matches' in reason

    def test_comparer_interval_symbolic_vs_schema(self, tmp_path: Path) -> None:
        question = make_question(
            final='HP', final_symbolic=SymbolicPayload(kind='expression', repr='Interval(-10/3, oo)')
        )
        result = StandardFinalComparer(q1_standard(tmp_path)).compare(question)
        assert result is not None
        assert result[0] == ValidationStatus.VALID

    def test_comparer_interval_open_differs(self, tmp_path: Path) -> None:
        question = make_question(
            final_symbolic=SymbolicPayload(kind='expression', repr='Interval(-10/3, oo, left_open=True)')
        )
        result = StandardFinalComparer(q1_standard(tmp_path)).compare(question)
        assert result is not None
        assert result[0] == ValidationStatus.INVALID

    def test_comparer_mismatch_invalid(self, tmp_path: Path) -> None:
        result = StandardFinalComparer(q1_standard(tmp_path)).compare(make_question('x<5', final='x < 5'))
        assert result is not None
        assert result[0] == ValidationStatus.INVALID

    def test_comparer_missing_solution_returns_none(self, tmp_path: Path) -> None:
        standard = tmp_path / 'exam'
        (standard / 'solutions').mkdir(parents=True)
        question = make_question(final='x<4')
        assert StandardFinalComparer(standard).compare(question) is None
        assert StandardFinalComparer(standard).compare_steps(question) is None

    def test_compare_steps_match_q001_order(self, tmp_path: Path) -> None:
        question = make_question(
            r'2-3x\leq12', r'2-3x-2\leq12-2', r'-3x\leq10', final=r'\left[-\frac{10}{3}, \infty\right)'
        )
        results = StandardFinalComparer(q1_standard(tmp_path)).compare_steps(question)
        assert results is not None
        assert [results[n][0] for n in (1, 2, 3)] == [ValidationStatus.VALID] * 3

    def test_compare_steps_mismatch_invalid(self, tmp_path: Path) -> None:
        question = make_question(r'2-3x\leq12', r'-3x\leq11', r'-3x\leq10')
        results = StandardFinalComparer(q1_standard(tmp_path)).compare_steps(question)
        assert results is not None
        assert results[1][0] == ValidationStatus.VALID
        assert results[2][0] == ValidationStatus.INVALID
        assert 'no matching standard step' in results[2][1]
        assert results[3][0] == ValidationStatus.VALID
        # -3x≤10 is equivalent to key step 2 (2-3x-2≤12-2) after soft-align cursor
        assert 'standard step 2' in results[3][1]

    def test_compare_steps_skips_to_later_standard(self, tmp_path: Path) -> None:
        """Student may jump to a later key step (not index-aligned)."""
        question = make_question(r'2-3x\leq12', r'x\geq -\frac{10}{3}')
        results = StandardFinalComparer(q1_standard(tmp_path)).compare_steps(question)
        assert results is not None
        assert results[1][0] == ValidationStatus.VALID
        assert results[2][0] == ValidationStatus.VALID
        # Key steps 4–5 are the ÷(-1/3) / x≥-10/3 forms; sequential index
        # align would have compared student step 2 to key step 2 (Invalid).
        assert 'standard step 4' in results[2][1] or 'standard step 5' in results[2][1]
        assert 'standard step 2' not in results[2][1]

    def test_comparer_prose_uncertain(self, tmp_path: Path) -> None:
        standard = tmp_path / 'exam'
        sol = standard / 'solutions'
        sol.mkdir(parents=True)
        (sol / 'question_001.tex').write_text('% final answer\nf kontinu di a\n', encoding='utf-8')
        result = StandardFinalComparer(standard).compare(make_question(final='f kontinu di a'))
        assert result is not None
        assert result[0] == ValidationStatus.UNCERTAIN

    def test_milestone_coverage_and_figure_role_skip(self, tmp_path: Path) -> None:
        schema = ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=1,
                    stem='s',
                    steps=['x > 1'],
                    steps_symbolic=[SymbolicPayload(kind='relation', repr='x > 1')],
                    milestones=[
                        ExamMilestone(role='critical_points', steps=['x = 0', 'x = 1', 'x = 2']),
                        ExamMilestone(role='sign_chart', steps=['x < 0']),
                    ],
                )
            ],
        )
        question = make_question(steps=[
            make_step(1, raw_text='x>1', role='figure', symbolic_repr='x > 1'),
            make_step(2, raw_text='x=0', role='critical_points', symbolic_repr='x = 0'),
        ])
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

        covered = make_question(steps=[
            make_step(i, raw_text=raw, symbolic_repr=repr_)
            for i, (raw, repr_) in enumerate(
                [('x=0', 'x = 0'), ('x=1', 'x = 1'), ('x=2', 'x = 2'), ('x<0', 'x < 0')], start=1
            )
        ])
        full = comparer.compare_milestones(covered)
        assert full['critical_points'][0] == ValidationStatus.VALID
        assert full['critical_points'][2] == pytest.approx(1.0)

    def test_compare_steps_none_without_algebra_bank(self, tmp_path: Path) -> None:
        schema = ExamSchema(source='test', questions=[ExamQuestion(number=1, stem='s', final='x>1')])
        question = make_question('x>0', raw_text='x>0')
        assert StandardFinalComparer(tmp_path, exam_schema=schema).compare_steps(question) is None

    def test_best_method_align_prefers_quadratic_bank(self, tmp_path: Path) -> None:
        schema = ExamSchema(
            source='test',
            questions=[
                ExamQuestion(
                    number=4,
                    stem='2x^2-5x-3<0',
                    steps=['2*x**2 - 5*x - 3 < 0'],
                    steps_symbolic=[SymbolicPayload(kind='relation', repr='2*x**2 - 5*x - 3 < 0')],
                    methods=[
                        ExamMethod(
                            id='factoring',
                            label='Pemaktoran',
                            steps=['(2*x + 1)*(x - 3) = 0'],
                            steps_symbolic=[SymbolicPayload(kind='relation', repr='(2*x + 1)*(x - 3) = 0')],
                        ),
                        ExamMethod(
                            id='quadratic_formula',
                            label='Rumus ABC',
                            steps=['x = (-b + sqrt(b**2 - 4*a*c))/(2*a)'],
                            steps_symbolic=[SymbolicPayload(kind='relation', repr='x = (5 + 7)/4')],
                        ),
                    ],
                    final='(-1/2, 3)',
                )
            ],
        )
        standard = tmp_path / 'exam'
        standard.mkdir()
        (standard / 'exam_schema.json').write_text(schema.model_dump_json(indent=2), encoding='utf-8')
        question = make_question(number=4, steps=[
            make_step(1, raw_text='2x^2-5x-3<0', symbolic_repr='2*x**2 - 5*x - 3 < 0'),
            make_step(2, raw_text='x=(5+7)/4', symbolic_repr='x = (5 + 7)/4'),
        ])
        aligned = StandardFinalComparer(standard, exam_schema=schema).compare_steps(question)
        assert aligned is not None
        assert aligned[1][0] == ValidationStatus.VALID
        assert aligned[2][0] == ValidationStatus.VALID
        assert 'quadratic_formula' in aligned[2][1]

class TestStepAlign:

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

class TestKunciIngest:

    def test_extract_question_stems_mini(self) -> None:
        stems = extract_question_stems(MINI_KUNCI)
        assert len(stems) == 2
        assert stems[0][0] == 1 and '2-3x' in stems[0][1]
        assert stems[1][0] == 2 and '3x-5' in stems[1][1]
        for _, stem in stems:
            assert 'HP' not in stem
            assert 'infty' not in stem.lower()
            assert 'align' not in stem.lower()
            assert 'Penyelesaian' not in stem

    def test_load_question_stems_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / 'empty_kunci'
        empty.mkdir()
        assert load_question_stems_from_kunci(empty) == []
        assert load_question_stems_from_kunci(tmp_path / 'missing') == []

    def test_load_question_stems_from_file(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci.tex'
        kunci.write_text(MINI_KUNCI, encoding='utf-8')
        stems = load_question_stems_from_kunci(kunci)
        assert len(stems) == 2
        assert stems[0][0] == 1
        assert '2-3x' in stems[0][1]

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

    def test_build_exam_schema_mini_no_tikz(self) -> None:
        schema = build_exam_schema(MINI_KUNCI, source='mini')
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

        single = build_exam_schema(MINI_KUNCI, source='mini')
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
        assert latex_to_symbolic_payload(r'\text{Cari akar-akar}') is None
        assert latex_to_symbolic_payload('') is None
        payload = latex_to_symbolic_payload(r'x \geq -\frac{10}{3}')
        assert payload is not None
        assert payload.kind == 'relation'
        assert '>=' in payload.repr
        assert 'oo' not in payload.repr

    def test_implies_normalize_and_symbolic(self) -> None:
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

    def test_ingester_writes_schema_solutions_and_rubrics(self, tmp_path: Path) -> None:
        kunci = tmp_path / 'kunci.tex'
        kunci.write_text(MINI_KUNCI, encoding='utf-8')
        standard = tmp_path / 'standards' / 'exam'
        (standard / 'rubrics').mkdir(parents=True)
        (standard / 'rubrics' / 'keep.json').write_text('{}', encoding='utf-8')
        written = KunciIngester(standard).ingest_file(kunci)
        assert len(written) == 5  # 2 solutions + schema + 2 rubrics
        assert (standard / 'solutions' / 'question_001.tex').is_file()
        assert (standard / 'solutions' / 'question_002.tex').is_file()
        assert (standard / 'rubrics' / 'keep.json').is_file()
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
        rubric = Rubric.model_validate_json(rubric_path.read_text(encoding='utf-8'))
        assert rubric.maximum_score == 10
        assert sum(c.points for c in rubric.criteria) == pytest.approx(10.0)

    def test_split_enumerate_items_mini(self) -> None:
        items = split_enumerate_items(MINI_KUNCI)
        assert len(items) == 2
        assert '2-3x' in items[0]
        assert '3x-5' in items[1]

    def test_extract_hp_and_steps_mini(self) -> None:
        items = split_enumerate_items(MINI_KUNCI)
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
        pairs = ingest_kunci_tex(MINI_KUNCI, source_note='mini')
        assert len(pairs) == 2
        assert pairs[0][0] == 1
        final = extract_final_answer_from_tex(pairs[0][1])
        assert final is not None
        assert '10' in final

    def test_controller_ingest_dir(self, tmp_path: Path) -> None:
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir()
        (kunci_dir / 'a.tex').write_text(MINI_KUNCI, encoding='utf-8')
        standard = tmp_path / 'std'
        result = IngestKunciController(KunciIngester(standard)).ingest(
            kunci_path=None, kunci_dir=kunci_dir, standard_dir=standard
        )
        assert len(result.written) == 5  # 2 solutions + schema + 2 rubrics
        assert result.standard_dir.resolve() == standard.resolve()
        assert result.schema_path is not None
        assert result.schema_path.is_file()
        assert result.schema_path.parent.resolve() == standard.resolve()
        assert (standard / 'rubrics' / 'question_001.json').is_file()

    def test_controller_ingest_rejects_mismatched_standard_dir(
        self, tmp_path: Path
    ) -> None:
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir()
        (kunci_dir / 'a.tex').write_text(MINI_KUNCI, encoding='utf-8')
        write_dir = tmp_path / 'std_a'
        other_dir = tmp_path / 'std_b'
        other_dir.mkdir()
        with pytest.raises(StandardDirMismatchError, match='does not match'):
            IngestKunciController(KunciIngester(write_dir)).ingest(
                kunci_path=None,
                kunci_dir=kunci_dir,
                standard_dir=other_dir,
            )

    def test_ingest_dir_rejects_empty_and_ambiguous_folder(self, tmp_path: Path) -> None:
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir()
        ingester = KunciIngester(tmp_path / 'std')
        with pytest.raises(NoKunciTexError):
            ingester.ingest_dir(kunci_dir)
        (kunci_dir / 'a.tex').write_text(MINI_KUNCI, encoding='utf-8')
        (kunci_dir / 'b.tex').write_text(Q1_KUNCI, encoding='utf-8')
        with pytest.raises(AmbiguousKunciDirError, match='a.tex, b.tex'):
            ingester.ingest_dir(kunci_dir)
        assert not (tmp_path / 'std').exists()

    def test_reingest_drops_stale_questions_but_keeps_other_files(self, tmp_path: Path) -> None:
        standard = tmp_path / 'std'
        stale_rubric = standard / 'rubrics' / 'question_099.json'
        stale_solution = standard / 'solutions' / 'question_099.tex'
        notes = standard / 'notes.txt'
        for path in (stale_rubric, stale_solution, notes):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('old', encoding='utf-8')
        kunci = tmp_path / 'mini.tex'
        kunci.write_text(MINI_KUNCI, encoding='utf-8')
        KunciIngester(standard).ingest_file(kunci)
        assert not stale_rubric.exists()
        assert not stale_solution.exists()
        assert notes.is_file()
        assert (standard / 'rubrics' / 'question_002.json').is_file()

    def test_topics_ingest_into_separate_folders(self, tmp_path: Path) -> None:
        config = AppConfig(grading=GradingConfig(standards_root=tmp_path / 'standards'))
        kunci = tmp_path / 'mini.tex'
        kunci.write_text(MINI_KUNCI, encoding='utf-8')
        for topic_id in ('1.5', '2'):
            standard = resolve_standard_dir(config, topic_id=topic_id)
            controller = build_ingest_kunci_controller(config, topic_id=topic_id)
            controller.ingest(kunci_path=kunci, kunci_dir=tmp_path, standard_dir=standard)
        topics = {
            folder: load_exam_schema(tmp_path / 'standards' / folder).topic_id
            for folder in ('topik_1', 'topik_2')
        }
        assert topics == {'topik_1': '1.5', 'topik_2': '2'}

class TestReport:

    def test_aggregate_full_auto_accept(self, tmp_path: Path) -> None:
        grade = make_report_question_grade(1, 10.0, 10.0)
        grade = grade.model_copy(
            update={
                'part_statuses': {'figure': 'valid'},
                'steps': grade.steps
                + [
                    make_step_grade(
                        0,
                        0.0,
                        0.0,
                        status=StepGradeStatus.CORRECT,
                        validation=ValidationStatus.VALID,
                    )
                ],
            }
        )
        report = aggregate_exam_report([grade], make_report_metadata(tmp_path))
        assert report.total_score == pytest.approx(10.0)
        assert report.maximum_total == pytest.approx(10.0)
        assert report.overall_status == ReviewStatus.AUTO_ACCEPT
        assert len(report.questions) == 1
        assert report.questions[0].step_count == 2
        assert report.questions[0].part_statuses == {'figure': 'valid'}

    def test_aggregate_review_required_overall(self, tmp_path: Path) -> None:
        report = aggregate_exam_report([make_report_question_grade(1, 10.0, 10.0), make_report_question_grade(2, 5.0, 10.0, review=ReviewStatus.REVIEW_REQUIRED)], make_report_metadata(tmp_path))
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
        report = aggregate_exam_report([make_report_question_grade(1, 10.0, 10.0)], make_report_metadata(tmp_path))
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
        assert 'Parts' in html
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
        grade = make_report_question_grade(1, 10.0, 10.0)
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

    def test_controller_records_injected_prompt_versions(self, tmp_path: Path) -> None:
        questions = tmp_path / 'questions'
        (questions / 'question_001').mkdir(parents=True)
        (questions / 'question_001' / 'grading.json').write_text(
            make_report_question_grade(1, 10.0, 10.0).model_dump_json(), encoding='utf-8'
        )
        (questions / 'question_001' / 'question.json').write_text('{}', encoding='utf-8')
        versions = PromptVersions(recognition='rec-9', validation='val-9', grading='gr-9')
        result = ReportController(
            JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards', prompt_versions=versions
        ).report(questions, tmp_path / 'out')
        assert result.exam_report.metadata.prompt_versions == versions
        assert result.exam_report.metadata.student_id == DEFAULT_STUDENT_ID

    def test_controller_ignores_grading_without_question(self, tmp_path: Path) -> None:
        questions = tmp_path / 'questions'
        for number, score in ((1, 6.0), (2, 9.0)):
            qdir = questions / f'question_{number:03d}'
            qdir.mkdir(parents=True)
            (qdir / 'grading.json').write_text(
                make_report_question_grade(number, score, 10.0).model_dump_json(), encoding='utf-8'
            )
        (questions / 'question_001' / 'question.json').write_text('{}', encoding='utf-8')
        result = ReportController(JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards').report(
            questions, tmp_path / 'out'
        )
        assert [q.question_number for q in result.exam_report.questions] == [1]
        assert result.exam_report.total_score == pytest.approx(6.0)
        assert 'q2' not in result.summary_csv_path.read_text(encoding='utf-8')

    def test_controller_orphan_grading_only_is_not_found(self, tmp_path: Path) -> None:
        qdir = tmp_path / 'questions' / 'question_001'
        qdir.mkdir(parents=True)
        (qdir / 'grading.json').write_text(
            make_report_question_grade(1, 6.0, 10.0).model_dump_json(), encoding='utf-8'
        )
        with pytest.raises(GradingNotFoundError):
            ReportController(JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards').report(
                tmp_path / 'questions', tmp_path / 'out'
            )

    def test_factory_prompt_versions_are_non_empty(self) -> None:
        versions = current_prompt_versions()
        assert versions.recognition and versions.validation and versions.grading

    def test_load_question_grades_rejects_invalid_artifact(self, tmp_path: Path) -> None:
        good = tmp_path / 'question_001' / 'grading.json'
        good.parent.mkdir()
        good.write_text(make_report_question_grade(1, 5.0, 10.0).model_dump_json(), encoding='utf-8')
        bad = tmp_path / 'question_002' / 'grading.json'
        bad.parent.mkdir()
        bad.write_text('{"not": "a grade"}', encoding='utf-8')
        assert grading_artifact_paths(tmp_path) == [good, bad]
        assert [g.question_number for g in load_question_grades([good])] == [1]
        with pytest.raises(ValueError, match='invalid grading artifact'):
            load_question_grades([good, bad])

    def test_changed_files_detects_edit_and_delete(self, tmp_path: Path) -> None:
        kept, edited, deleted = (tmp_path / name for name in ('kept', 'edited', 'deleted'))
        for path in (kept, edited, deleted):
            path.write_text('v1', encoding='utf-8')
        snapshot = snapshot_files([kept, edited, deleted])
        assert changed_files(snapshot) == []
        edited.write_text('v2', encoding='utf-8')
        deleted.unlink()
        assert changed_files(snapshot) == [edited, deleted]

    @pytest.mark.parametrize(
        'raw, expected',
        [
            (r'2 - 3x \le 12', r'$\displaystyle 2 - 3x \le 12$'),
            (r'\frac{1}{3} \cdot 10', r'$\displaystyle \frac{1}{3} \cdot 10$'),
            ('x ≤ 3', r'$\displaystyle x \le 3$'),
            (r'\frac{1{3}', r'\texttt{\textbackslash{}frac\{1\{3\}}'),
            ('a & b', r'\texttt{a \& b}'),
            ('50%', r'\texttt{50\%}'),
            (r'\left( x', r'\texttt{\textbackslash{}left( x}'),
            (r'x \rightarrow 2', r'$\displaystyle x \rightarrow 2$'),
            (r'\left( x \rightarrow 2', r'\texttt{\textbackslash{}left( x \textbackslash{}rightarrow 2}'),
            (r'\left( x \right)', r'$\displaystyle \left( x \right)$'),
            (r'\[ x > 2 \]', r'$\displaystyle x > 2$'),
            ('$x>2$', r'$\displaystyle x>2$'),
            ('x_', r'\texttt{x\_}'),
            ('', ''),
            (r'=> -3x = 0 \n x = 0', r'$\displaystyle => -3x = 0 \quad x = 0$'),
            (r'x+1=0\n x=-1', r'$\displaystyle x+1=0 \quad x=-1$'),
            (r'x = 1\n2', r'$\displaystyle x = 1 \quad 2$'),
            (r'x \ne 2', r'$\displaystyle x \ne 2$'),
            (r'x \neq 2 \to 3', r'$\displaystyle x \neq 2 \to 3$'),
            (r'x \foo 2', r'\texttt{x \textbackslash{}foo 2}'),
            (r'\alpha \in (0, \infty)', r'$\displaystyle \alpha \in (0, \infty)$'),
        ],
    )
    def test_latex_math_or_text(self, raw: str, expected: str) -> None:
        assert latex_math_or_text(raw) == expected

    def test_latex_stem_turns_literal_newline_into_quad(self) -> None:
        assert latex_stem(r'Tentukan $x > 0$\n untuk x real') == r'Tentukan $x > 0$ \quad untuk x real'

    @pytest.mark.parametrize(
        'stem, expected',
        [
            ('Tentukan $x_1 > 0$', 'Tentukan $x_1 > 0$'),
            ('x_1 > 0 untuk semua x', r'\texttt{x\_1 > 0 untuk semua x}'),
            ('Tentukan x^2 > 4', r'\texttt{Tentukan x\textasciicircum{}2 > 4}'),
        ],
        ids=['script_in_math', 'underscore_in_text', 'caret_in_text'],
    )
    def test_latex_stem_rejects_scripts_in_text_mode(self, stem: str, expected: str) -> None:
        assert latex_stem(stem) == expected

    def test_question_view_moves_unsafe_image_path_to_missing(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        crop = tmp_path / 'run #1' / 'crops' / 'page_001' / 'page_001_region_00_solution.png'
        detail = QuestionReportDetail(question=question, grade=grade, crop_images=[crop])
        view = build_question_view(detail, tmp_path / 'custom')
        assert view.images == []
        assert len(view.missing_images) == 1
        assert 'page\\_001\\_region\\_00\\_solution.png' in view.missing_images[0]

    def test_latex_text_maps_unicode_punctuation(self) -> None:
        assert latex_text('carry\u2011forward \u2014 x_1 ≤ 2') == r'carry-forward --- x\_1 $\le$ 2'

    def test_part_row_recovers_id_after_annotator_rewrite(self) -> None:
        question, grade = self._graded_question()
        annotated = [
            s.model_copy(update={'feedback': 'Redraw the number line.'}) if s.step_number == 0 else s
            for s in grade.steps
        ]
        grade = grade.model_copy(update={'steps': annotated, 'part_statuses': {'figure': 'valid'}})
        view = build_question_view(QuestionReportDetail(question=question, grade=grade), Path('.'))
        assert [(p.number, p.comment) for p in view.parts] == [('figure', 'Redraw the number line.')]

    def test_graphics_path_relative_posix(self, tmp_path: Path) -> None:
        png = tmp_path / 'run' / 'crops' / 'page_001' / 'page_001_region_00_solution.png'
        assert graphics_path(png, tmp_path / 'run') == 'crops/page_001/page_001_region_00_solution.png'

    @staticmethod
    def _graded_question() -> tuple[Question, QuestionGrade]:
        question = make_question(
            steps=[
                make_step(1, raw_text=r'2 - 3x \le 12', symbolic_repr='2 - 3*x <= 12', role='algebra'),
                make_step(2, raw_text=r'x \le -\frac{10}{3}', symbolic_repr='x <= -10/3', role='hp'),
            ],
            final=r'x \le -\frac{10}{3}',
            figures=[make_figure('NUMBER_LINE((-oo, -10/3])', caption='filled circle at -10/3')],
        )
        grade = make_report_question_grade(1, 5.0, 10.0).model_copy(
            update={
                'steps': [
                    make_step_grade(1, 3.0, 3.0).model_copy(update={'feedback': 'first step parsed successfully'}),
                    make_step_grade(
                        2, 0.0, 3.0, status=StepGradeStatus.INCORRECT, validation=ValidationStatus.INVALID
                    ).model_copy(update={'feedback': 'solution sets differ'}),
                    make_step_grade(0, 2.0, 2.0).model_copy(update={'feedback': 'part:figure; figure step present'}),
                ],
                'final_answer': make_step_grade(2, 0.0, 2.0, validation=ValidationStatus.INVALID).model_copy(
                    update={'feedback': 'final answer differs from standard'}
                ),
            }
        )
        return question, grade

    @staticmethod
    def _write_tex(layout, student_id: str = 'student_001') -> str:
        result = ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=layout.root / 'standards',
            latex_reporter=LatexReportWriter(),
        ).report(layout.questions_dir, layout.root, student_id=student_id)
        assert result.report_tex_path == layout.root / 'report.tex'
        tex = result.report_tex_path.read_text(encoding='utf-8')
        assert '\\VAR{' not in tex and '\\BLOCK{' not in tex
        return tex

    def test_latex_report_contains_crop_ocr_and_feedback(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        crop = 'page_001_region_00_solution.png'
        layout = write_report_workspace(
            tmp_path / 'run', question, grade, crops=[crop], mapped_crops=[crop], stem=r'$2-3x \le 12$'
        )
        tex = self._write_tex(layout, student_id='Budi_01')
        assert_contains(
            tex,
            r'\begin{document}',
            r'\end{document}',
            r'\section*{Soal 1}',
            r'\textbf{Soal:} $2-3x \le 12$',
            r'keepaspectratio]{crops/page_001/page_001_region_00_solution.png}',
            r'$\displaystyle 2 - 3x \le 12$',
            r'$\displaystyle x \le -\frac{10}{3}$',
            'first step parsed successfully',
            'solution sets differ',
            'final answer differs from standard',
            'figure step present',
            r'\item{} filled circle at -10/3',
            r'\texttt{NUMBER\_LINE((-oo, -10/3])}',
            r'Budi\_\allowbreak{}01',
            r'AUTO\_ACCEPT',
        )

    def test_latex_report_falls_back_to_image_regions(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        crop = 'page_001_region_01_solution.png'
        question = question.model_copy(
            update={
                'image_regions': [
                    ImageRegionRef(page_number=1, crop_path=f'data\\output\\elsewhere\\crops\\page_001\\{crop}')
                ]
            }
        )
        layout = write_report_workspace(tmp_path / 'run', question, grade, crops=[crop])
        tex = self._write_tex(layout)
        assert f'{{crops/page_001/{crop}}}' in tex
        assert r'\textbf{Soal:}' not in tex

    def test_latex_report_missing_crop_placeholder(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(
            tmp_path / 'run', question, grade, mapped_crops=['page_001_region_05_solution.png']
        )
        tex = self._write_tex(layout)
        assert r'\fbox{crop tidak ditemukan: page\_001\_region\_05\_solution.png}' in tex
        assert r'\includegraphics' not in tex

    def test_controller_without_latex_reporter_keeps_three_outputs(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(tmp_path / 'run', question, grade)
        result = ReportController(JsonCsvHtmlReporter(), standard_dir=tmp_path / 'standards').report(
            layout.questions_dir, layout.root
        )
        assert result.report_tex_path is None
        assert not (layout.root / 'report.tex').exists()
        assert result.report_html_path.is_file()

    @staticmethod
    def _tex_folder(tmp_path: Path) -> Path:
        folder = tmp_path / 'run'
        folder.mkdir()
        (folder / 'report.tex').write_text('\\documentclass{article}', encoding='utf-8')
        (folder / 'report.pdf').write_bytes(b'old pdf')
        (folder / 'report.aux').write_text('stale', encoding='utf-8')
        return folder

    def test_pdflatex_compiler_replaces_pdf_and_cleans_up(self, tmp_path: Path) -> None:
        folder = self._tex_folder(tmp_path)
        runner = FakeLatexRunner()
        pdf = PdfLatexCompiler(Path('pdflatex.exe'), passes=2, runner=runner).compile(folder / 'report.tex')
        assert pdf == folder / 'report.pdf'
        assert pdf.read_bytes() == b'%PDF-1.5 fake'
        assert (folder / 'report.log').is_file()
        assert not (folder / 'report.aux').exists()
        assert not list(folder.glob('report_build.*'))
        assert [cwd for _command, cwd in runner.calls] == [folder, folder]
        assert runner.calls[0][0] == pdflatex_command('pdflatex.exe', 'report.tex', 'report_build')

    @pytest.mark.parametrize(
        ('executable', 'runner', 'message', 'keeps_log'),
        [
            (None, FakeLatexRunner(), 'pdflatex tidak ditemukan', False),
            (
                Path('pdflatex.exe'),
                FakeLatexRunner(returncode=1, log_text='! Undefined control sequence.\nl.38 \\foo\n'),
                r'Undefined control sequence\. \(l\.38',
                True,
            ),
            (Path('pdflatex.exe'), FakeLatexRunner(raises=subprocess.TimeoutExpired('pdflatex', 5)), 'melebihi', False),
        ],
        ids=['missing-executable', 'latex-error', 'timeout'],
    )
    def test_pdflatex_compiler_failures(
        self, tmp_path: Path, executable, runner: FakeLatexRunner, message: str, keeps_log: bool
    ) -> None:
        folder = self._tex_folder(tmp_path)
        with pytest.raises(ReportPdfError, match=message):
            PdfLatexCompiler(executable, runner=runner).compile(folder / 'report.tex')
        assert (folder / 'report.pdf').read_bytes() == b'old pdf'
        assert (folder / 'report.log').is_file() is keeps_log
        assert not list(folder.glob('report_build.*'))

    def test_pdflatex_compiler_reports_locked_pdf(self, tmp_path: Path, monkeypatch) -> None:
        folder = self._tex_folder(tmp_path)
        real_replace = os.replace

        def locked_pdf(src, dst) -> None:
            if str(dst).endswith('.pdf'):
                raise PermissionError(dst)
            real_replace(src, dst)

        monkeypatch.setattr('app.services.latex.pdflatex_compiler.os.replace', locked_pdf)
        with pytest.raises(ReportPdfError, match='sedang dibuka'):
            PdfLatexCompiler(Path('pdflatex.exe'), runner=FakeLatexRunner()).compile(folder / 'report.tex')
        assert (folder / 'report.log').is_file()
        assert not list(folder.glob('report_build.*'))

    @pytest.mark.parametrize(
        ('log_text', 'expected'),
        [
            ('This is pdfTeX\nOutput written on report.pdf\n', None),
            ('! Emergency stop.\n<*> report.tex\n', 'Emergency stop.'),
            (
                "x\n! I can't write on file `report.pdf'.\n(Press Enter)\nl.38 \\clearpage\n",
                "I can't write on file `report.pdf'. (l.38 \\clearpage)",
            ),
        ],
        ids=['clean', 'no-location', 'with-location'],
    )
    def test_latex_error_summary(self, log_text: str, expected: str | None) -> None:
        assert latex_error_summary(log_text) == expected

    def test_resolve_pdflatex_prefers_configured_file(self, tmp_path: Path, monkeypatch) -> None:
        exe = tmp_path / 'pdflatex.exe'
        exe.write_bytes(b'')
        assert resolve_pdflatex(str(exe)) == exe
        monkeypatch.setattr('app.services.latex.pdflatex_compiler.shutil.which', lambda _name: None)
        assert resolve_pdflatex(str(tmp_path / 'missing.exe')) is None

    @pytest.mark.parametrize(('enabled', 'expected'), [(True, PdfLatexCompiler), (False, type(None))], ids=['on', 'off'])
    def test_build_pdf_compiler_follows_config(self, enabled: bool, expected: type) -> None:
        config = AppConfig(report=ReportConfig(pdf=ReportPdfConfig(enabled=enabled)))
        assert isinstance(build_pdf_compiler(config), expected)

    def test_controller_compiles_pdf_after_tex(self, tmp_path: Path, capsys) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(tmp_path / 'run', question, grade)
        result = ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=layout.root / 'standards',
            latex_reporter=LatexReportWriter(),
            pdf_compiler=PdfLatexCompiler(Path('pdflatex.exe'), runner=FakeLatexRunner()),
        ).report(layout.questions_dir, layout.root)
        assert result.report_pdf_path == layout.root / 'report.pdf'
        assert result.report_pdf_path.is_file()
        print_report_result(result)
        assert f'PDF:  {result.report_pdf_path}' in capsys.readouterr().out

    def test_controller_pdf_failure_only_warns(self, tmp_path: Path, capsys) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(tmp_path / 'run', question, grade)
        result = ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=layout.root / 'standards',
            latex_reporter=LatexReportWriter(),
            pdf_compiler=PdfLatexCompiler(None),
        ).report(layout.questions_dir, layout.root)
        assert result.report_pdf_path is None
        assert result.report_tex_path.is_file()
        assert result.report_html_path.is_file()
        assert_contains(capsys.readouterr().err, 'report.pdf tidak dikompilasi', 'pdflatex tidak ditemukan')

    def test_controller_pdf_failure_removes_stale_pdf(self, tmp_path: Path) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(tmp_path / 'run', question, grade)
        stale = layout.root / 'report.pdf'
        stale.write_bytes(b'%PDF old run')
        ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=layout.root / 'standards',
            latex_reporter=LatexReportWriter(),
            pdf_compiler=PdfLatexCompiler(None),
        ).report(layout.questions_dir, layout.root)
        assert not stale.exists()

    def test_controller_locked_pdf_only_warns(self, tmp_path: Path, monkeypatch, capsys) -> None:
        question, grade = self._graded_question()
        layout = write_report_workspace(tmp_path / 'run', question, grade)
        opened = layout.root / 'report.pdf'
        opened.write_bytes(b'%PDF open in viewer')
        real_replace, real_unlink = os.replace, Path.unlink

        def locked_replace(src, dst) -> None:
            if Path(dst) == opened:
                raise PermissionError(dst)
            real_replace(src, dst)

        def locked_unlink(path: Path, missing_ok: bool = False) -> None:
            if path == opened:
                raise PermissionError(path)
            real_unlink(path, missing_ok=missing_ok)

        monkeypatch.setattr('app.services.latex.pdflatex_compiler.os.replace', locked_replace)
        monkeypatch.setattr(Path, 'unlink', locked_unlink)
        result = ReportController(
            JsonCsvHtmlReporter(),
            standard_dir=layout.root / 'standards',
            latex_reporter=LatexReportWriter(),
            pdf_compiler=PdfLatexCompiler(Path('pdflatex.exe'), runner=FakeLatexRunner()),
        ).report(layout.questions_dir, layout.root)
        assert result.report_pdf_path is None
        assert result.report_tex_path.is_file()
        assert opened.read_bytes() == b'%PDF open in viewer'
        assert 'sedang dibuka' in capsys.readouterr().err

    def test_print_grade_result_shows_part_statuses(self, capsys) -> None:
        result = GradeResult(
            grades=[
                QuestionGrade(
                    question_id='question_001',
                    question_number=1,
                    score=8.0,
                    maximum_score=10.0,
                    review_status=ReviewStatus.AUTO_ACCEPT,
                    part_statuses={'figure': 'valid', 'critical_points': 'invalid'},
                )
            ],
            questions_dir=Path('questions'),
            standard_dir=Path('standards'),
            artifact_paths=[Path('questions/question_001/grading.json')],
        )
        print_grade_result(result)
        out = capsys.readouterr().out
        assert 'parts=' in out
        assert 'figure:valid' in out
        assert 'critical_points:invalid' in out

class TestCliProcess:

    def test_pipeline_factory_wires_feedback_annotator(self) -> None:
        config = AppConfig(
            ollama=OllamaConfig(
                vision_model='v',
                reasoning_model='r',
                base_url='http://localhost:9',
            ),
            recognition=RecognitionConfig(),
        )
        controller = build_process_controller(config)
        grader = controller._grade._grader  # noqa: SLF001
        assert grader._annotator is not None  # noqa: SLF001
        assert grader._annotator._model == 'r'  # noqa: SLF001

    def test_process_controller_passes_standard_schema_to_recognizer(
        self, tmp_path: Path
    ) -> None:
        default_std = tmp_path / 'standards' / 'topik_1'
        override_std = tmp_path / 'standards' / 'override'
        default_std.mkdir(parents=True)
        override_std.mkdir(parents=True)
        (exam_schema_path(default_std)).write_text(
            ExamSchema(
                source='default',
                questions=[
                    ExamQuestion(number=1, stem='$x>0$', expects_figure=False),
                ],
            ).model_dump_json(indent=2),
            encoding='utf-8',
        )
        (exam_schema_path(override_std)).write_text(
            ExamSchema(
                source='override',
                questions=[
                    ExamQuestion(number=9, stem='$x<1$', expects_figure=True),
                ],
            ).model_dump_json(indent=2),
            encoding='utf-8',
        )
        config = AppConfig(
            ollama=OllamaConfig(vision_model='v', base_url='http://localhost:9'),
            recognition=RecognitionConfig(),
        )
        config.grading.standards_root = default_std.parent
        controller = build_process_controller(config, standard_dir=override_std)
        recognizer = controller._recognize._recognizer  # noqa: SLF001
        schema = recognizer._exam_schema  # noqa: SLF001
        assert schema is not None
        assert schema.source == 'override'
        assert schema.questions[0].number == 9
        assert schema.questions[0].expects_figure is True
        extractor = controller._extract._extractor  # noqa: SLF001
        assert extractor._exam_schema is not None  # noqa: SLF001
        assert extractor._exam_schema.source == 'override'  # noqa: SLF001

    def test_process_controller_runs_all_stages(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        stale = harness.output_dir / 'pages'
        stale.mkdir(parents=True)
        (stale / 'old.png').write_bytes(b'x')
        standards = harness.output_dir / 'standards'
        standards.mkdir()
        (standards / 'keep.txt').write_text('keep', encoding='utf-8')
        result = harness.process(student_id='student_001')
        assert harness.progress == [
            ProcessStage.RENDER,
            ProcessStage.RECOGNIZE,
            ProcessStage.EXTRACT,
            ProcessStage.LATEX,
            ProcessStage.VALIDATE,
            ProcessStage.GRADE,
            ProcessStage.REPORT,
        ]
        assert harness.cleared and harness.cleared[0][0] == harness.output_dir
        assert 'pages' in harness.cleared[0][1]
        assert not stale.exists()
        assert (standards / 'keep.txt').is_file()
        assert result.total_score == pytest.approx(8.0)
        assert result.maximum_total == pytest.approx(10.0)
        assert len(result.questions) == 1
        for stage in harness.stage_calls:
            stage.assert_called_once()

    def test_process_progress_counts_follow_stage_order(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        harness.process()
        assert [(e.completed, e.total) for e in harness.progress_events] == [
            (i, len(PROCESS_STAGES)) for i in range(1, len(PROCESS_STAGES) + 1)
        ]

    def test_process_and_process_from_crops_share_tail(self, tmp_path: Path) -> None:
        full = ProcessHarness(tmp_path)
        full_result = full.process(student_id='s1')
        crops = ProcessHarness(tmp_path)
        write_crop_workspace(crops.pages_dir, crops.crops_dir)
        crops_result = crops.process_from_crops(student_id='s1')
        assert crops_result == full_result
        assert crops.progress == full.progress[1:]
        assert crops.progress_events[0].completed == 2

    class RecordingReview:
        """Records each review call and whether LaTeX had already run."""

        def __init__(self, harness: ProcessHarness, error: Exception | None = None) -> None:
            self._harness = harness
            self._error = error
            self.calls: list[tuple[Path, bool, bool]] = []
            self.pruned: list[Path] = []

        def prune_stale_latex_sources(self, questions_dir: Path) -> list[str]:
            assert not self.calls, 'prune must run before review'
            self.pruned.append(questions_dir)
            return []

        def review_loop(self, questions_dir: Path, *, force_yes: bool = False) -> None:
            self.calls.append((questions_dir, force_yes, self._harness.latex.build.called))
            if self._error is not None:
                raise self._error

    @pytest.mark.parametrize(
        ('entry', 'kwargs', 'expected_force_yes'),
        [
            ('process', {}, False),
            ('process', {'force_yes': True}, True),
            ('process_from_crops', {}, False),
            ('process_from_crops', {'force_yes': True}, True),
        ],
        ids=['process', 'process-yes', 'from-crops', 'from-crops-yes'],
    )
    def test_question_review_runs_after_extract_before_latex(
        self, tmp_path: Path, entry: str, kwargs: dict, expected_force_yes: bool
    ) -> None:
        harness = ProcessHarness(tmp_path)
        review = self.RecordingReview(harness)
        harness.controller_options['question_review'] = review
        if entry == 'process_from_crops':
            write_crop_workspace(harness.pages_dir, harness.crops_dir)
        getattr(harness, entry)(**kwargs)
        assert review.calls == [(harness.questions_dir, expected_force_yes, False)]
        harness.latex.build.assert_called_once()

    def test_question_review_error_stops_pipeline(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        harness.controller_options['question_review'] = self.RecordingReview(
            harness, QuestionArtifactsInvalidError(['question_001: rusak'])
        )
        with pytest.raises(QuestionArtifactsInvalidError):
            harness.process(force_yes=True)
        harness.latex.build.assert_not_called()
        assert harness.progress[-1] == ProcessStage.EXTRACT

    def test_process_from_questions_keeps_edited_json(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        review = self.RecordingReview(harness)
        harness.controller_options['question_review'] = review
        path = write_question_dir(harness.questions_dir, make_question('x < 5'))
        before = path.read_bytes()
        result = harness.process_from_questions(force_yes=True)
        assert path.read_bytes() == before
        for stage in (harness.render.render, harness.recognize.recognize_pages, harness.extract.extract):
            stage.assert_not_called()
        assert review.pruned == [harness.questions_dir]
        assert review.calls == [(harness.questions_dir, True, False)]
        assert harness.progress == [
            ProcessStage.LATEX,
            ProcessStage.VALIDATE,
            ProcessStage.GRADE,
            ProcessStage.REPORT,
        ]
        assert result.total_score == pytest.approx(8.0)

    def test_process_from_questions_requires_questions(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        with pytest.raises(QuestionsNotFoundError):
            harness.process_from_questions()
        harness.latex.build.assert_not_called()

    def test_process_from_crops_requires_regions(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        harness.crops_dir.mkdir()
        with pytest.raises(CropsRegionsMissingError, match='menu 3'):
            harness.process_from_crops()
        harness.recognize.recognize_pages.assert_not_called()

    @pytest.mark.parametrize('use_existing', [True, False], ids=['reuse', 'fresh'])
    def test_process_reset_respects_use_existing_crops(self, tmp_path: Path, use_existing: bool) -> None:
        harness = ProcessHarness(tmp_path)
        regions = write_crop_workspace(harness.pages_dir, harness.crops_dir)
        harness.controller_options['crop_controller'] = MagicMock(crops_dir=harness.crops_dir)
        harness.process(crops_dir=harness.crops_dir, use_existing_crops=use_existing, force_yes=True)
        assert regions.is_file() is use_existing

    def test_process_from_crops_page_without_regions_keeps_artifacts(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        write_crop_workspace(harness.pages_dir, harness.crops_dir)
        (harness.pages_dir / 'pages.json').write_text(
            '[{"page_number":1,"image":"page_001.png","width":10,"height":10},'
            '{"page_number":2,"image":"page_002.png","width":10,"height":10}]',
            encoding='utf-8',
        )
        harness.recognition_dir.mkdir()
        kept = harness.recognition_dir / 'page_001_recognition.json'
        kept.write_text('{}', encoding='utf-8')
        with pytest.raises(CropsRegionsMissingError):
            harness.process_from_crops()
        assert kept.is_file()
        harness.recognize.recognize_pages.assert_not_called()

    def test_process_from_crops_skips_render_and_wipe(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        regions = write_crop_workspace(harness.pages_dir, harness.crops_dir)
        harness.recognition_dir.mkdir()
        stale_recognition = harness.recognition_dir / 'page_009_recognition.json'
        stale_recognition.write_text('{}', encoding='utf-8')
        leftover = harness.questions_dir / 'question_099' / 'question.json'
        leftover.parent.mkdir(parents=True)
        leftover.write_text('{}', encoding='utf-8')
        result = harness.process_from_crops(student_id='student_001')
        assert harness.cleared == []
        assert not leftover.exists()
        assert not stale_recognition.exists()
        assert (harness.pages_dir / 'pages.json').is_file()
        assert regions.is_file()
        harness.render.render.assert_not_called()
        harness.recognize.recognize_pages.assert_called_once()
        assert harness.recognize.recognize_pages.call_args.kwargs.get('from_crops') is True
        assert result.total_score == pytest.approx(8.0)

    def test_process_controller_skip_reset_leaves_workspace(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        harness.output_dir.mkdir()
        stale = harness.output_dir / 'keep_me.txt'
        stale.write_text('stale', encoding='utf-8')
        harness.process(reset_workspace=False)
        assert stale.is_file()

    def test_cli_process_success(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(
            tmp_path, monkeypatch, reasoning_model='reason-test', standards_root=tmp_path / 'standards'
        )
        pdf = cli.pdf(folder=tmp_path)
        out = cli.output_root
        cli.controller(
            progress=[
                ProcessProgress(stage=ProcessStage.RENDER, completed=1, total=7),
                ProcessProgress(stage=ProcessStage.REPORT, completed=7, total=7),
            ],
            result=make_process_result(
                tmp_path,
                questions=[
                    QuestionScoreSummary(
                        question_id='question_001',
                        question_number=1,
                        score=8.0,
                        maximum_score=10.0,
                        review_status=ReviewStatus.AUTO_ACCEPT,
                    )
                ],
                total_score=8.0,
                maximum_total=10.0,
                report_json_path=out / 'report.json',
                summary_csv_path=out / 'summary.csv',
                report_html_path=out / 'report.html',
            ),
        )
        assert cli.run('process', str(pdf), '--output', str(out), '--student-id', 'student_001') == 0
        assert_contains(
            capsys.readouterr().out,
            'Membersihkan', 'Vision:', 'vision-test', 'Progress', 'PDF rendering', 'Results', '8/10', 'Artifacts',
        )
        (builder,) = cli.builder_kwargs
        assert builder['standard_dir'] == tmp_path / 'standards' / 'topik_1'

    def test_cli_process_resolves_bare_filename(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        pdf = cli.pdf('smoke_inequality.pdf')
        fake = cli.controller()
        assert cli.run('process', 'smoke_inequality.pdf') == 0
        assert fake.pdf_paths == [pdf]

    @pytest.mark.parametrize(
        ('error', 'exit_code', 'message'),
        [
            (PdfNotFoundError(Path('missing.pdf')), 1, 'PDF not found'),
            (RuntimeError('boom unexpected'), 2, 'boom unexpected'),
        ],
        ids=['domain_error', 'unexpected_error'],
    )
    def test_cli_process_error_exit_codes(
        self, tmp_path: Path, monkeypatch, capsys, error: Exception, exit_code: int, message: str
    ) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        pdf = cli.pdf(folder=tmp_path)
        cli.controller(error=error)
        assert cli.run('process', str(pdf)) == exit_code
        assert_contains(capsys.readouterr().err, 'Error', message)

    def test_cli_process_requires_vision_model(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch, vision_model='')
        assert cli.run('process', str(cli.pdf(folder=tmp_path))) == 1
        assert 'Vision model is not configured' in capsys.readouterr().err

    def test_cli_process_interactive_pdf_choice(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        cli.pdf('alpha.pdf')
        beta = cli.pdf('beta.pdf')
        fake = cli.controller()
        cli.inputs('2')
        assert cli.run('process') == 0
        assert fake.pdf_paths == [beta]
        assert_contains(capsys.readouterr().out, 'PDF tersedia', 'beta.pdf', 'Memproses:')

    def test_cli_process_no_pdfs_in_jawaban(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        assert cli.run('process') == 1
        assert 'No PDF files found' in capsys.readouterr().err

    def test_cli_process_continue_then_exit(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        alpha = cli.pdf('alpha.pdf')
        beta = cli.pdf('beta.pdf')
        fake = cli.controller()
        cli.tty()
        # argv PDF first; then continue (1), pick beta (2), exit (2)
        cli.inputs('1', '2', '2')
        assert cli.run('process', str(alpha)) == 0
        assert fake.pdf_paths == [alpha, beta]
        assert_contains(capsys.readouterr().out, 'Selesai.', 'Proses PDF lain')

    def test_cli_process_student_id_applies_to_first_pdf_only(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        alpha = cli.pdf('alpha.pdf')
        cli.pdf('beta.pdf')
        cli.controller()
        cli.tty()
        cli.inputs('1', '2', '2')
        assert cli.run('process', str(alpha), '--student-id', 'nim_alpha') == 0
        assert [run['student_id'] for _method, _pdf, run in cli.calls] == ['nim_alpha', DEFAULT_STUDENT_ID]

    def test_cli_menu_finish_defaults_student_id(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        layout = build_run_layout(cli.output_root, 'answer')
        write_crop_workspace(layout.pages_dir, layout.crops_dir)
        cli.controller()
        cli.tty()
        cli.inputs('7', '9')
        assert cli.run('menu') == 0
        ((method, _pdf, run),) = cli.calls
        assert method == 'process_from_crops'
        assert run['student_id'] == 'student_001'
        assert run['pages_dir'] == layout.pages_dir
        assert run['recognition_dir'] == layout.recognition_dir
        assert run['questions_dir'] == layout.questions_dir
        assert run['output_dir'] == layout.report_dir
        assert run['crops_dir'] == layout.crops_dir
        assert cli.builder_kwargs[0]['crops_dir'] == layout.crops_dir
        assert cli.builder_kwargs[0]['on_question_crops_missing'] is print_question_crops_missing

    @pytest.mark.parametrize(
        ('entry', 'expected_force_yes'),
        [
            (('menu',), False),
            (('finish-questions', '--run', 'answer'), False),
            (('finish-questions', '--run', 'answer', '--yes'), True),
        ],
        ids=['menu-8', 'subcommand', 'subcommand-yes'],
    )
    def test_cli_finish_questions_continues_from_layout(
        self, tmp_path: Path, monkeypatch, entry: tuple[str, ...], expected_force_yes: bool
    ) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        layout = build_run_layout(cli.output_root, 'answer')
        layout.questions_dir.mkdir(parents=True)
        cli.controller()
        cli.tty()
        cli.inputs('8', '9')
        assert cli.run(*entry) == 0
        ((method, _pdf, run),) = cli.calls
        assert method == 'process_from_questions'
        assert run['questions_dir'] == layout.questions_dir
        assert run['output_dir'] == layout.report_dir
        assert run['crops_dir'] == layout.crops_dir
        assert run['force_yes'] is expected_force_yes

    def test_process_from_crops_warns_without_question_crops(self, tmp_path: Path, capsys) -> None:
        harness = ProcessHarness(tmp_path)
        write_crop_workspace(harness.pages_dir, harness.crops_dir)
        harness.controller_options = {
            'question_numbers': [1],
            'on_question_crops_missing': print_question_crops_missing,
        }
        harness.process_from_crops()
        assert_contains(capsys.readouterr().err, 'nomor soal belum ditetapkan', 'menu 5')
        harness.recognize.recognize_pages.assert_called_once()

    def test_process_from_crops_rejects_stale_question_crop(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        write_regions_artifact(
            harness.crops_dir / 'page_001',
            1,
            regions=[DetectedRegion(type='solution', region=Region(x=0, y=0, width=5, height=5))],
            source='ink',
        )
        write_question_crops(harness.crops_dir, {1: ['page_009_region_00_solution.png']})
        harness.controller_options = {'question_numbers': [1]}
        with pytest.raises(QuestionCropsInvalidError, match='crop tidak ditemukan'):
            harness.process_from_crops()
        harness.recognize.recognize_pages.assert_not_called()

    def test_cli_label_questions_yes_run(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch, vision_model='', standards_root=q1_standard(tmp_path).parent)
        layout = build_run_layout(cli.output_root, 'answer')
        write_regions_artifact(
            layout.crops_dir / 'page_001',
            1,
            regions=[DetectedRegion(type='solution', region=Region(x=0, y=0, width=5, height=5))],
            source='ink',
        )
        assert cli.run('label-questions', '--yes', '--run', 'answer') == 0
        assert load_question_crops(layout.crops_dir) == {1: ['page_001_region_00_solution.png']}
        assert cli.run('relabel-questions', '--yes', '--run', 'answer') == 0

    def test_cli_relabel_questions_fails_without_json(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch, vision_model='', standards_root=q1_standard(tmp_path).parent)
        layout = build_run_layout(cli.output_root, 'answer')
        write_crop_workspace(layout.pages_dir, layout.crops_dir)
        assert cli.run('relabel-questions', '--yes', '--run', 'answer') == 1
        assert 'question_crops' in capsys.readouterr().err

    def test_process_controller_reset_requires_workspace_root(self, tmp_path: Path) -> None:
        harness = ProcessHarness(tmp_path)
        with pytest.raises(ValueError, match='workspace_root'):
            harness.process(workspace_root=None)
        harness.render.render.assert_not_called()

    @staticmethod
    def _kunci_dir(tmp_path: Path, *names: str) -> Path:
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir(exist_ok=True)
        for name in names:
            (kunci_dir / name).write_text(MINI_KUNCI, encoding='utf-8')
        return kunci_dir

    def test_cli_ingest_kunci_topic_writes_its_own_folder(self, tmp_path: Path, monkeypatch, capsys) -> None:
        standards = tmp_path / 'standards'
        cli = CliHarness(tmp_path, monkeypatch, standards_root=standards)
        kunci_dir = self._kunci_dir(tmp_path, 'only.tex')
        assert cli.run('ingest-kunci', '--kunci-dir', str(kunci_dir), '--topic', '2') == 0
        assert load_exam_schema(standards / 'topik_2').topic_id == '2'
        assert not (standards / 'topik_1').exists()
        assert 'topik_2' in capsys.readouterr().out

    def test_cli_ingest_kunci_several_tex_non_tty_errors(self, tmp_path: Path, monkeypatch, capsys) -> None:
        standards = tmp_path / 'standards'
        cli = CliHarness(tmp_path, monkeypatch, standards_root=standards)
        cli.tty(False)
        kunci_dir = self._kunci_dir(tmp_path, 'a.tex', 'b.tex')
        assert cli.run('ingest-kunci', '--kunci-dir', str(kunci_dir)) == 1
        assert 'Pass the file explicitly' in capsys.readouterr().err
        assert not standards.exists()

    def test_cli_ingest_kunci_several_tex_tty_asks_which(self, tmp_path: Path, monkeypatch) -> None:
        standards = tmp_path / 'standards'
        cli = CliHarness(tmp_path, monkeypatch, standards_root=standards)
        cli.tty(True)
        cli.inputs('2')
        kunci_dir = self._kunci_dir(tmp_path, 'a.tex', 'b.tex')
        assert cli.run('ingest-kunci', '--kunci-dir', str(kunci_dir)) == 0
        assert load_exam_schema(standards / 'topik_1').source == 'b.tex'

    def test_cli_ingest_kunci_missing_file_is_domain_error(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch, standards_root=tmp_path / 'standards')
        kunci_dir = self._kunci_dir(tmp_path)
        assert cli.run('ingest-kunci', 'typo.tex', '--kunci-dir', str(kunci_dir)) == 1
        assert 'Kunci .tex not found' in capsys.readouterr().err

    def test_cli_validate_uses_topic_folder_or_standard_override(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch, standards_root=tmp_path / 'standards')
        questions = tmp_path / 'q'
        seen: list[tuple[Path, str | None]] = []

        def fake_build(config, standard_dir=None, *, topic_id=None):
            seen.append((standard_dir, topic_id))
            controller = MagicMock()
            controller.validate.return_value = ValidateResult(
                validations=[], questions_dir=questions, artifact_paths=[]
            )
            return controller

        monkeypatch.setattr('app.services.pipeline_factory.build_validate_controller', fake_build)
        assert cli.run('validate', '--questions-dir', str(questions), '--topic', '2') == 0
        assert cli.run('validate', '--questions-dir', str(questions), '--standard', str(tmp_path / 'own')) == 0
        assert seen == [(tmp_path / 'standards' / 'topik_2', '2'), (tmp_path / 'own', None)]

    def test_cli_extract_force_recognize_goes_through_crops(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch, standards_root=tmp_path / 'standards')
        cli.pdf('answer.pdf')
        layout = build_run_layout(cli.output_root, 'answer')
        recognized: list[dict] = []
        monkeypatch.setattr(
            'app.commands.flows.recognize_from_crops',
            lambda config, run_layout, pdf_path, **kwargs: recognized.append(
                {'run': run_layout.root, 'pdf': pdf_path.name, **kwargs}
            ),
        )
        extractor = MagicMock()
        extractor.extract_from_dir.return_value = ExtractResult(
            questions=[], output_dir=layout.questions_dir, artifact_paths=[]
        )
        built: list[tuple[Path, str | None]] = []

        def fake_build(config, standard_dir=None, *, topic_id=None, recognize_runner=None):
            built.append((standard_dir, topic_id))
            return ExtractController(extractor=extractor, recognize_runner=recognize_runner)

        monkeypatch.setattr('app.services.pipeline_factory.build_extract_controller', fake_build)
        argv = ('extract', 'answer.pdf', '--force-recognize', '--yes', '--use-existing-crops', '--topic', '2')
        assert cli.run(*argv) == 0
        topic_folder = tmp_path / 'standards' / 'topik_2'
        assert built == [(topic_folder, '2')]
        (call,) = recognized
        assert call['run'] == layout.root
        assert call['pdf'] == 'answer.pdf'
        assert call['recognition_dir'] == layout.recognition_dir
        assert (call['use_existing_crops'], call['force_yes']) == (True, True)
        assert (call['standard_dir'], call['topic_id']) == (topic_folder, '2')

    def test_recognize_from_crops_confirms_crops_then_recognizes_from_them(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        config = AppConfig(
            ollama=OllamaConfig(vision_model='v'),
            grading=GradingConfig(standards_root=tmp_path / 'std'),
        )
        layout = build_run_layout(tmp_path / 'out', 'answer')
        pages = [make_page()]
        render = MagicMock()
        render.render.return_value = RenderResult(
            pages=pages, output_dir=layout.pages_dir, metadata_path=layout.pages_dir / 'pages.json'
        )
        crop = MagicMock()
        recognize = MagicMock()
        recognize.recognize_pages.return_value = RecognizeResult(
            pages=[], output_dir=layout.recognition_dir, artifact_paths=[]
        )
        builder_kwargs: list[dict] = []
        monkeypatch.setattr('app.services.pipeline_factory.build_render_controller', lambda: render)
        monkeypatch.setattr(
            'app.services.pipeline_factory.build_crop_controller',
            lambda _config, _recognition, **kw: builder_kwargs.append(kw) or crop,
        )
        monkeypatch.setattr(
            'app.services.pipeline_factory.build_recognize_controller',
            lambda _config, _recognition, **kw: builder_kwargs.append(kw) or recognize,
        )
        stale = layout.recognition_dir / 'old.json'
        stale.parent.mkdir(parents=True)
        stale.write_text('{}', encoding='utf-8')
        flows.recognize_from_crops(
            config,
            layout,
            tmp_path / 'a.pdf',
            pages_dir=layout.pages_dir,
            recognition_dir=layout.recognition_dir,
            dpi=150,
            use_existing_crops=True,
            force_yes=True,
            topic_id='2',
        )
        crop.ensure_crops_confirmed.assert_called_once_with(
            pages, layout.pages_dir, use_existing=True, force_yes=True
        )
        recognize.recognize_pages.assert_called_once_with(
            pages, layout.pages_dir, layout.recognition_dir, from_crops=True
        )
        assert not stale.exists()
        assert [kw['topic_id'] for kw in builder_kwargs] == ['2', '2']

    def test_cli_process_writes_under_pdf_named_folder(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        cli.pdf('tugas 1 matsi.pdf')
        other = build_run_layout(cli.output_root, 'other')
        other.questions_dir.mkdir(parents=True)
        (other.root / 'report.json').write_text('{}', encoding='utf-8')
        stale = build_run_layout(cli.output_root, 'tugas 1 matsi')
        stale.questions_dir.mkdir(parents=True)
        (stale.questions_dir / 'old.json').write_text('{}', encoding='utf-8')
        cli.controller()
        assert cli.run('process', 'tugas 1 matsi.pdf') == 0
        (builder,) = cli.builder_kwargs
        ((_method, _pdf, run),) = cli.calls
        layout = build_run_layout(cli.output_root, 'tugas 1 matsi')
        assert builder['recognition_dir'] == layout.recognition_dir
        assert builder['crops_dir'] == layout.crops_dir
        assert run['pages_dir'] == layout.pages_dir
        assert run['questions_dir'] == layout.questions_dir
        assert run['output_dir'] == layout.root
        assert run['workspace_root'] == layout.root
        assert run['crops_dir'] == layout.crops_dir
        assert not (stale.questions_dir / 'old.json').exists()
        assert (other.root / 'report.json').is_file()

    def test_cli_report_uses_run_arg(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        for name in ('alpha', 'beta'):
            build_run_layout(cli.output_root, name).questions_dir.mkdir(parents=True)
        calls: list[tuple] = []

        class FakeReportController:

            def report(self, questions_dir, output_dir, *, student_id, crops_dir=None):
                calls.append((questions_dir, output_dir, crops_dir))
                raise GradingNotFoundError(questions_dir)
        monkeypatch.setattr('app.services.pipeline_factory.build_report_controller', lambda config, standard_dir: FakeReportController())
        assert cli.run('report', '--run', 'beta.pdf') == 1
        beta = build_run_layout(cli.output_root, 'beta')
        assert calls == [(beta.questions_dir, beta.root, beta.crops_dir)]

    def test_cli_report_questions_dir_without_run_uses_its_parent(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        for name in ('alpha', 'beta'):
            build_run_layout(cli.output_root, name).questions_dir.mkdir(parents=True)
        cli.tty(False)
        calls: list[tuple] = []

        class FakeReportController:

            def report(self, questions_dir, output_dir, *, student_id, crops_dir=None):
                calls.append((Path(questions_dir), Path(output_dir), crops_dir))
                raise GradingNotFoundError(questions_dir)
        monkeypatch.setattr('app.services.pipeline_factory.build_report_controller', lambda config, standard_dir: FakeReportController())
        beta = build_run_layout(cli.output_root, 'beta')
        assert cli.run('report', '--questions-dir', str(beta.questions_dir)) == 1
        assert calls == [(beta.questions_dir, beta.root, beta.crops_dir)]

    def test_cli_process_use_existing_crops_keeps_regions(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        cli.pdf('answer.pdf')
        layout = build_run_layout(cli.output_root, 'answer')
        regions = write_crop_workspace(layout.pages_dir, layout.crops_dir)
        cli.controller()
        assert cli.run('process', 'answer.pdf', '--use-existing-crops', '--yes') == 0
        ((_method, _pdf, run),) = cli.calls
        assert run['use_existing_crops'] is True
        assert regions.is_file()
        assert not (layout.pages_dir / 'pages.json').exists()

    def test_cli_process_loop_resets_path_overrides(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        alpha = cli.pdf('alpha.pdf')
        cli.pdf('beta.pdf')
        custom = tmp_path / 'custom_questions'
        cli.controller()
        cli.tty()
        cli.inputs('1', '2', '2')
        assert cli.run('process', str(alpha), '--questions-dir', str(custom)) == 0
        first, second = (run for _method, _pdf, run in cli.calls)
        assert first['questions_dir'] == custom
        assert second['questions_dir'] == build_run_layout(cli.output_root, 'beta').questions_dir

    @pytest.mark.parametrize(
        ('argv', 'expected'),
        [(('menu',), None), (('menu', '--topic', '2'), '2')],
        ids=['follows_schema', 'explicit_topic'],
    )
    def test_cli_menu_finish_topic(self, tmp_path: Path, monkeypatch, argv: tuple[str, ...], expected) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        layout = build_run_layout(cli.output_root, 'answer')
        write_crop_workspace(layout.pages_dir, layout.crops_dir)
        cli.controller()
        cli.tty()
        cli.inputs('7', '9')
        assert cli.run(*argv) == 0
        assert cli.builder_kwargs[0]['topic_id'] == expected

    def test_cli_ingest_kunci_resolves_bare_filename(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        kunci_dir = tmp_path / 'kunci'
        kunci_dir.mkdir()
        (kunci_dir / 'kunci_q1.tex').write_text(Q1_KUNCI, encoding='utf-8')
        standard = tmp_path / 'standards' / 'exam_001'
        assert cli.run(
            'ingest-kunci', 'kunci_q1.tex', '--kunci-dir', str(kunci_dir), '--standard', str(standard)
        ) == 0
        assert exam_schema_path(standard).is_file()

    def test_build_validate_controller_sets_active_pack(self) -> None:
        config = AppConfig(ollama=OllamaConfig(vision_model='v'), recognition=RecognitionConfig())
        with using_pack(get_pack('1.5')):
            build_validate_controller(config, topic_id='2')
            assert get_active_pack().id == '2'

    def test_cli_grade_requires_run_when_ambiguous(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        for name in ('alpha', 'beta'):
            build_run_layout(cli.output_root, name).questions_dir.mkdir(parents=True)
        cli.tty(False)
        assert cli.run('grade') == 1
        assert_contains(capsys.readouterr().err, '--run', 'alpha', 'beta')

    def test_cli_latex_picks_single_run(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        only = build_run_layout(cli.output_root, 'only')
        only.questions_dir.mkdir(parents=True)
        seen: list[Path] = []

        class FakeLatexController:

            def build(self, questions_dir):
                seen.append(questions_dir)
                raise QuestionsNotFoundError(questions_dir)
        monkeypatch.setattr('app.services.pipeline_factory.build_latex_controller', FakeLatexController)
        assert cli.run('latex') == 1
        assert seen == [only.questions_dir]

    def test_cli_latex_drops_sidecar_of_edited_question(self, tmp_path: Path, monkeypatch) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        layout = build_run_layout(cli.output_root, 'only')
        path = write_question_dir(layout.questions_dir, make_question('x < 4'), latex_source='y > 9')
        sidecar = path.parent / 'latex_source.tex'
        base = sidecar.stat().st_mtime
        os.utime(path, (base + 10, base + 10))
        assert cli.run('latex', '--run', 'only') == 0
        student = (path.parent / 'student.tex').read_text(encoding='utf-8')
        assert 'x &< 4' in student
        assert 'y > 9' not in student
        assert not sidecar.exists()

    def test_cli_menu_requires_terminal(self, tmp_path: Path, monkeypatch, capsys) -> None:
        cli = CliHarness(tmp_path, monkeypatch)
        cli.tty(False)
        assert cli.run('menu') == 1
        assert 'requires a terminal' in capsys.readouterr().err

class TestCliCommands:
    EXPECTED_NAMES = (
        'render',
        'recognize',
        'propose-crops',
        'recrop',
        'label-questions',
        'relabel-questions',
        'extract',
        'latex',
        'validate',
        'grade',
        'report',
        'process',
        'finish-questions',
        'ingest-kunci',
        'menu',
    )

    def test_registry_matches_cli_contract_in_help_order(self) -> None:
        assert tuple(command.name for command in COMMANDS) == self.EXPECTED_NAMES

    def test_every_entry_is_a_command_with_help(self) -> None:
        for command in COMMANDS:
            assert isinstance(command, Command)
            assert command.help.strip()

    def test_parser_registers_every_command(self) -> None:
        assert_contains(build_parser().format_help(), *self.EXPECTED_NAMES)

    @pytest.mark.parametrize(
        ('name', 'mode'),
        [('label-questions', LabelMode.LABEL), ('relabel-questions', LabelMode.RELABEL)],
    )
    def test_label_commands_dispatch_their_mode(
        self, tmp_path: Path, monkeypatch, name: str, mode: LabelMode
    ) -> None:
        (command,) = (c for c in COMMANDS if c.name == name)
        assert isinstance(command, LabelCommand)
        cli = CliHarness(tmp_path, monkeypatch)
        build_run_layout(cli.output_root, 'only').questions_dir.mkdir(parents=True)
        seen: list[tuple[str, LabelMode, bool]] = []
        monkeypatch.setattr(
            'app.commands.flows.label',
            lambda config, layout, mode, *, force_yes, topic_id: seen.append(
                (layout.root.name, mode, force_yes, topic_id)
            ),
        )
        assert cli.run(name, '--yes', '--topic', '2') == 0
        assert seen == [('only', mode, True, '2')]

    def test_main_configures_console_streams(self, tmp_path: Path, monkeypatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr('app.cli.configure_console_streams', lambda: calls.append(1))
        main(['--config', str(tmp_path / 'typo.yaml'), 'grade'])
        assert calls == [1]

class TestMenuController:

    @staticmethod
    def _menu(
        tmp_path: Path,
        *,
        vision_model: str = 'vision-test',
        topic_id: str | None = None,
        answers: tuple[str, ...] = (),
        **actions,
    ):
        output = tmp_path / 'output'
        recorder = RecordingMenuActions(run_root=output / 'picked', **actions)
        config = AppConfig(
            ollama=OllamaConfig(vision_model=vision_model),
            output=OutputConfig(root_dir=output),
        )
        remaining = iter(answers)

        def input_fn(_prompt: str = '') -> str:
            try:
                return next(remaining)
            except StopIteration:
                raise EOFError from None
        return MenuController(recorder, config, topic_id=topic_id, input_fn=input_fn), recorder

    def test_actions_satisfy_protocol(self, tmp_path: Path) -> None:
        assert isinstance(RecordingMenuActions(run_root=tmp_path), MenuActions)
        assert isinstance(CliMenuActions(), MenuActions)

    def test_ensure_layout_picks_run_once(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path)
        session = menu.start_session()
        for choice in (MenuChoice.RECROP, MenuChoice.LABEL_QUESTIONS, MenuChoice.RELABEL_QUESTIONS):
            assert menu.dispatch(session, choice) == 0
        assert recorder.names == ['pick_run', 'recrop', 'label', 'label']
        assert [args[1] for name, args in recorder.calls if name == 'label'] == [
            LabelMode.LABEL,
            LabelMode.RELABEL,
        ]
        assert session.layout == RunLayout(root=recorder.run_root)

    def test_propose_crops_sets_layout_for_pdf(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, errors={'propose_crops': NoRegionsJsonError(Path('c'))})
        session = menu.start_session()
        assert menu.dispatch(session, MenuChoice.PROPOSE_CROPS) == 1
        expected = layout_for_pdf(tmp_path / 'output', recorder.pdf)
        assert session.layout == expected
        menu.dispatch(session, MenuChoice.RECROP)
        assert 'pick_run' not in recorder.names

    @pytest.mark.parametrize(
        ('error', 'code'),
        [(NoRegionsJsonError(Path('crops')), 1), (RuntimeError('boom'), 2)],
        ids=['domain', 'unexpected'],
    )
    def test_dispatch_maps_errors_to_exit_codes(self, tmp_path: Path, capsys, error, code: int) -> None:
        menu, _recorder = self._menu(tmp_path, errors={'recrop': error})
        assert menu.dispatch(menu.start_session(), MenuChoice.RECROP) == code
        assert str(error) in capsys.readouterr().err

    @pytest.mark.parametrize(
        ('error', 'code'),
        [(RegionsArtifactMissingError(Path('x.json')), 1), (ValueError('bad'), 2), (KeyError('k'), 2)],
    )
    def test_exit_code_for(self, error: Exception, code: int) -> None:
        assert exit_code_for(error) == code

    def test_finish_requires_vision_model_before_run(self, tmp_path: Path, capsys) -> None:
        menu, recorder = self._menu(tmp_path, vision_model='')
        assert menu.dispatch(menu.start_session(), MenuChoice.FINISH) == 1
        assert recorder.names == []
        assert 'Vision model is not configured' in capsys.readouterr().err

    def test_finish_questions_needs_no_vision_model(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, vision_model='', topic_id='2')
        assert menu.dispatch(menu.start_session(), MenuChoice.FINISH_QUESTIONS) == 0
        assert recorder.calls == [
            ('pick_run', ()),
            ('finish_questions', (RunLayout(root=recorder.run_root), '2')),
        ]

    def test_select_topic_updates_session_config_and_finish(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, topic_id=None)
        session = menu.start_session()
        assert session.explicit_topic_id is None
        menu.dispatch(session, MenuChoice.FINISH)
        menu.dispatch(session, MenuChoice.SELECT_TOPIC)
        menu.dispatch(session, MenuChoice.FINISH)
        assert session.topic_id == session.explicit_topic_id == '2'
        assert menu.config.grading.topic_id == '2'
        finishes = [args[1] for name, args in recorder.calls if name == 'finish']
        assert finishes == [None, '2']

    def test_cancelled_topic_selection_keeps_schema_topic(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, topic_id=None)
        recorder.topic_id = None
        session = menu.start_session()
        before = (session.topic_id, menu.config.grading.topic_id)
        assert menu.dispatch(session, MenuChoice.SELECT_TOPIC) == 0
        menu.dispatch(session, MenuChoice.FINISH)
        assert session.explicit_topic_id is None
        assert (session.topic_id, menu.config.grading.topic_id) == before
        assert [args[1] for name, args in recorder.calls if name == 'finish'] == [None]

    def test_ingest_uses_session_topic(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, topic_id='2')
        session = menu.start_session()
        assert session.explicit_topic_id == '2'
        menu.dispatch(session, MenuChoice.INGEST)
        assert recorder.calls == [('ingest', ('2',))]

    def test_start_session_topic_syncs_config_standards_folder(self, tmp_path: Path) -> None:
        menu, _recorder = self._menu(tmp_path, topic_id='2')
        menu.start_session()
        assert menu.config.grading.topic_id == '2'
        assert resolve_standard_dir(menu.config).name == 'topik_2'

    def test_menu_header_shows_topic_standards_folder(self, tmp_path: Path, capsys) -> None:
        menu, _recorder = self._menu(tmp_path, topic_id='2', answers=('9',))
        try:
            assert menu.run() == 0
        finally:
            reset_interactive_session_flag()
        assert 'topik_2' in capsys.readouterr().out

    def test_cli_menu_pick_run_without_runs_points_to_menu(self, tmp_path: Path) -> None:
        config = AppConfig(output=OutputConfig(root_dir=tmp_path / 'out'))
        with pytest.raises(RunNotSpecifiedError) as info:
            CliMenuActions().pick_run(config)
        assert 'menu 3' in str(info.value)
        assert '--run' not in str(info.value)

    def test_start_session_rejects_unknown_topic(self, tmp_path: Path) -> None:
        menu, _recorder = self._menu(tmp_path, topic_id='99.9')
        with pytest.raises(UnknownTopicError):
            menu.start_session()

    def test_run_keeps_last_code_until_eof(self, tmp_path: Path, capsys) -> None:
        menu, recorder = self._menu(
            tmp_path, answers=('99', '4'), errors={'recrop': NoRegionsJsonError(Path('c'))}
        )
        try:
            assert menu.run() == 1
        finally:
            reset_interactive_session_flag()
        assert recorder.names == ['pick_run', 'recrop']
        assert_contains(capsys.readouterr().err, 'Invalid menu selection', 'No regions JSON')

    def test_run_exit_choice_returns_zero(self, tmp_path: Path) -> None:
        menu, recorder = self._menu(tmp_path, answers=('2', '9'))
        try:
            assert menu.run() == 0
        finally:
            reset_interactive_session_flag()
        assert recorder.names == ['ingest']

class TestTopicRegistry:

    def test_default_and_list_packs(self) -> None:
        ids = known_topic_ids()
        assert '1.5' in ids
        assert '2' in ids
        packs = list_packs()
        assert {p.id for p in packs} == set(ids)
        pack = get_pack('1.5')
        assert pack.label
        assert 'interval' in pack.capability_ids

    def test_unknown_topic_raises(self) -> None:
        with pytest.raises(UnknownTopicError):
            get_pack('99.9')

    def test_resolve_pack_priority(self) -> None:
        schema = ExamSchema(topic_id='2', questions=[])
        assert resolve_pack(schema=schema).id == '2'
        assert resolve_pack(topic_id='1.5', schema=schema).id == '1.5'

    def test_parse_topic_choice(self) -> None:
        known = known_topic_ids()
        assert parse_topic_choice('1', known) == known[0]
        assert parse_topic_choice('1.5', known) == '1.5'
        assert parse_topic_choice('2', known) == '2'
        assert parse_topic_choice('TOPIK_1', known) == '1.5'
        assert parse_topic_choice('topik_2', known) == '2'
        for bad in ('nope', 'topik_9'):
            with pytest.raises(ValueError):
                parse_topic_choice(bad, known)

    def test_parse_topic_choice_rejects_id_index_collision(self) -> None:
        with pytest.raises(ValueError, match='ambiguous'):
            parse_topic_choice('2', ['2', '3'])
        assert parse_topic_choice('1', ['2', '3']) == '2'
        assert parse_topic_choice('topik_3', ['2', '3']) == '3'

    @pytest.mark.parametrize(
        ('topic_id', 'folder'), [('1.5', 'topik_1'), ('2', 'topik_2'), (' 11.2 ', 'topik_11')]
    )
    def test_standards_folder_name_uses_chapter(self, topic_id: str, folder: str) -> None:
        assert standards_folder_name(topic_id) == folder

    def test_registered_packs_have_distinct_standards_folders(self) -> None:
        folders = [standards_folder_name(topic_id) for topic_id in known_topic_ids()]
        assert len(folders) == len(set(folders))
        with pytest.raises(ValueError, match='topik_1'):
            assert_unique_standards_folders(['1.3', '1.5'])
        with pytest.raises(ValueError):
            standards_folder_name('.5')

class TestTopicPackBehavior:

    def test_inequality_rubric_and_roles(self) -> None:
        pack = get_pack('1.5')
        parts = [
            ExamPart(kind='algebra', order=1),
            ExamPart(kind='hp', order=2),
        ]
        rubric = pack.rubric_from_parts(1, parts)
        assert rubric.maximum_score == 10.0
        assert pack.coalesce_step_role('HP = (1, oo)', None, None) == 'hp'

    def test_abs_pack_reuses_roles(self) -> None:
        pack = get_pack('2')
        role = pack.coalesce_step_role(
            '|x|<1',
            SymbolicPayload(kind='relation', repr='Abs(x)<1'),
            'algebra',
        )
        assert role == 'algebra'

    def test_step_checks_cover_every_role(self) -> None:
        pack = get_pack('1.5')
        assert set(pack.step_checks) == set(pack.roles)
        assert pack.step_checks['critical_points'] == StepCheck.ZERO_MAKERS
        assert pack.step_checks['sign_chart'] == StepCheck.NUMERIC_EVAL
        assert pack.step_checks['hp'] == StepCheck.SOLUTION_SET
        assert dict(get_pack('2').step_checks) == dict(pack.step_checks)

class TestCapabilityDispatch:

    def test_full_chain_matches_legacy_abs(self) -> None:
        full = normalize_math_text(r'|x| \leq 2', capability_ids=ALL_CAPABILITY_IDS)
        assert full == 'Abs(x) <= 2'

    def test_ascii_union_joins_intervals(self) -> None:
        assert normalize_math_text('(-4, 0) U (2, oo)') == '-4 < x < 0 or 2 < x < oo'
        assert normalize_math_text('(-4,0)U(0,2)') == '-4 < x < 0 or 0 < x < 2'
        assert ' or ' not in normalize_math_text('(-4, 0) u (2, oo)')

    def test_inactive_interval_skips_hp_rewrite(self) -> None:
        text = 'HP = (1, 3)'
        assert normalize_math_text(text, capability_ids=('abs',)) == 'HP = (1, 3)'
        assert normalize_math_text(text, capability_ids=('interval',)) == '1 < x < 3'

    def test_active_pack_context(self) -> None:
        with using_pack(get_pack('1.5')):
            assert normalize_math_text(r'x \in (0,1)') == '0 < x < 1'

    def test_apply_capabilities_skips_unknown(self) -> None:
        assert apply_capabilities('x+1', ('nope', 'abs')) == 'x+1'
