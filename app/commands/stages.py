"""Single-stage subcommands: render, recognize, extract, latex, validate, grade, report."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.commands import flows
from app.commands.base import (
    PAGES_HELP,
    Command,
    add_dpi_arg,
    add_output_arg,
    add_pages_dir_arg,
    add_pdf_arg,
    add_questions_dir_arg,
    add_run_arg,
    add_standard_arg,
    add_student_id_arg,
    add_topic_arg,
    add_use_existing_crops_arg,
    add_yes_arg,
)
from app.config import load_config, require_vision_model
from app.functions.run_layout import RunLayout
from app.functions.workspace_reset import ensure_resettable_dir
from app.models.recognition import RecognizeResult
from app.services import pipeline_factory
from app.views.result_view import (
    print_extract_result,
    print_grade_result,
    print_latex_result,
    print_recognize_result,
    print_render_result,
    print_report_result,
    print_validate_result,
)


class RenderCommand(Command):
    name = "render"
    help = "Render a PDF to per-page PNG images"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_pdf_arg(parser)
        add_output_arg(parser, PAGES_HELP)
        add_dpi_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        pdf_path = flows.resolve_pdf(args, config)
        output_dir = args.output or flows.layout_for(config, pdf_path).pages_dir
        result = pipeline_factory.build_render_controller().render(
            pdf_path, output_dir, flows.dpi(args, config)
        )
        print_render_result(result)
        return 0


class RecognizeCommand(Command):
    name = "recognize"
    help = "Render a PDF and run Ollama vision recognition"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_pdf_arg(parser)
        add_output_arg(
            parser,
            "Directory for recognition JSON (default: <output.root_dir>/<nama_pdf>/recognition)",
        )
        add_pages_dir_arg(parser)
        add_dpi_arg(parser)
        add_yes_arg(parser)
        add_use_existing_crops_arg(
            parser, "Reuse existing page_*_regions.json instead of re-running ink propose"
        )
        add_standard_arg(parser)
        add_topic_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        require_vision_model(config)

        pdf_path = flows.resolve_pdf(args, config)
        layout = flows.layout_for(config, pdf_path)
        result = flows.recognize_from_crops(
            config,
            layout,
            pdf_path,
            pages_dir=args.pages_dir or layout.pages_dir,
            recognition_dir=args.output or layout.recognition_dir,
            dpi=flows.dpi(args, config),
            use_existing_crops=bool(args.use_existing_crops),
            force_yes=bool(args.yes),
            standard_dir=flows.standard_dir(args, config),
            topic_id=args.topic,
        )
        print_recognize_result(result)
        return 0


class ExtractCommand(Command):
    name = "extract"
    help = "Merge recognition JSON into per-question artifacts"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_pdf_arg(parser)
        add_output_arg(
            parser,
            "Directory for question artifacts (default: <output.root_dir>/<nama_pdf>/questions)",
        )
        parser.add_argument(
            "--recognition-dir",
            type=Path,
            default=None,
            help=(
                "Directory with page_*_recognition.json "
                "(default: <output.root_dir>/<nama_pdf>/recognition)"
            ),
        )
        add_pages_dir_arg(parser, "Directory for page PNGs if recognition must run first")
        add_dpi_arg(parser, "Render DPI if recognition must run first")
        parser.add_argument(
            "--force-recognize",
            action="store_true",
            help="Always run recognition before extract, even if JSON exists",
        )
        add_yes_arg(parser, "Skip interactive crop confirmation if recognition runs")
        add_use_existing_crops_arg(
            parser, "Reuse existing page_*_regions.json if recognition runs"
        )
        add_standard_arg(parser)
        add_topic_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        pdf_path = flows.resolve_pdf(args, config)
        layout = flows.layout_for(config, pdf_path)
        recognition_dir = args.recognition_dir or layout.recognition_dir
        output_dir = args.output or layout.questions_dir
        standard = flows.standard_dir(args, config)

        def recognize_runner() -> RecognizeResult:
            return flows.recognize_from_crops(
                config,
                layout,
                pdf_path,
                pages_dir=args.pages_dir or layout.pages_dir,
                recognition_dir=recognition_dir,
                dpi=flows.dpi(args, config),
                use_existing_crops=bool(args.use_existing_crops),
                force_yes=bool(args.yes),
                standard_dir=standard,
                topic_id=args.topic,
            )

        controller = pipeline_factory.build_extract_controller(
            config, standard, topic_id=args.topic, recognize_runner=recognize_runner
        )
        clear_output = ensure_resettable_dir(output_dir, run_root=layout.root, label="questions")
        result = controller.extract(
            recognition_dir=recognition_dir,
            output_dir=output_dir,
            force_recognize=bool(args.force_recognize),
            clear_output=clear_output,
        )
        print_extract_result(result)
        return 0


class LatexCommand(Command):
    name = "latex"
    help = "Build student.tex from extracted question.json files"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_questions_dir_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        questions_dir = flows.questions_dir_for_run(config, args)
        pipeline_factory.build_question_review_controller(config).prune_stale_latex_sources(
            questions_dir
        )
        result = pipeline_factory.build_latex_controller().build(questions_dir)
        print_latex_result(result)
        return 0


class ValidateCommand(Command):
    name = "validate"
    help = "Validate student steps with SymPy (writes validation.json)"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_questions_dir_arg(parser)
        add_standard_arg(parser)
        add_topic_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        questions_dir = flows.questions_dir_for_run(config, args)
        controller = pipeline_factory.build_validate_controller(
            config, flows.standard_dir(args, config), topic_id=args.topic
        )
        print_validate_result(controller.validate(questions_dir))
        return 0


class GradeCommand(Command):
    name = "grade"
    help = "Grade validated questions against a rubric standard"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_questions_dir_arg(
            parser, "Directory with question_*/ (default: <output.root_dir>/<nama_pdf>/questions)"
        )
        add_standard_arg(parser)
        add_topic_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        questions_dir = flows.questions_dir_for_run(config, args)
        controller = pipeline_factory.build_grade_controller(
            config, flows.standard_dir(args, config), topic_id=args.topic
        )
        print_grade_result(controller.grade(questions_dir))
        return 0


class ReportCommand(Command):
    name = "report"
    help = "Build JSON/CSV/HTML/LaTeX report from grading.json artifacts"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        add_questions_dir_arg(
            parser,
            "Directory with question_*/grading.json "
            "(default: <output.root_dir>/<nama_pdf>/questions)",
        )
        add_output_arg(
            parser, "Output directory for report files (default: <output.root_dir>/<nama_pdf>)"
        )
        add_student_id_arg(parser, "Student identifier for summary CSV")
        add_standard_arg(
            parser,
            "Standards directory recorded in metadata "
            "(default: <grading.standards_root>/topik_<bab> of the topic)",
        )
        add_topic_arg(parser)
        add_run_arg(parser)

    def run(self, args: argparse.Namespace) -> int:
        config = load_config(args.config)
        has_run = bool((args.run or "").strip())
        if args.questions_dir is not None and not has_run:
            # questions/ sits directly under its run root next to crops/.
            layout = RunLayout(root=Path(args.questions_dir).parent)
        else:
            layout = flows.layout_for_run(config, args)
        controller = pipeline_factory.build_report_controller(
            config, flows.standard_dir(args, config)
        )
        result = controller.report(
            args.questions_dir or layout.questions_dir,
            args.output or layout.report_dir,
            student_id=args.student_id,
            crops_dir=layout.crops_dir,
        )
        print_report_result(result)
        return 0
