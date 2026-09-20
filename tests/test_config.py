"""Tests for app.config package defaults."""

from pathlib import Path

from app.config import DEFAULT_CONFIG_PATH, load_config


def test_default_config_path_points_at_package_yaml() -> None:
    assert DEFAULT_CONFIG_PATH.name == "config.yaml"
    assert DEFAULT_CONFIG_PATH.parent.name == "config"
    assert DEFAULT_CONFIG_PATH.is_file()


def test_load_config_default_reads_package_yaml() -> None:
    config = load_config()
    assert config.pdf.dpi == 200
    assert config.pdf.output_dir == Path("data/output/pages")
    assert config.input.jawaban_dir == Path("data/input/jawaban")
    assert config.input.kunci_jawaban_dir == Path("data/input/kunci_jawaban")
    assert config.recognition.output_dir == Path("data/output/recognition")
    assert config.questions.output_dir == Path("data/output/questions")
    assert config.grading.standard_dir == Path("data/output/standards/exam_001")
    assert config.report.output_dir == Path("data/output")
    assert config.ollama.base_url == "http://localhost:11434"
    assert isinstance(config.recognition.output_dir, Path)
