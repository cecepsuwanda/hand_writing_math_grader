from pathlib import Path

from app.cli import main
from tests.helpers import write_pdf


def test_cli_render_writes_png_and_exits_zero(tmp_path: Path, capsys) -> None:
    pdf_path = write_pdf(tmp_path / "answer.pdf", 2)
    output_dir = tmp_path / "pages"

    exit_code = main(
        [
            "render",
            str(pdf_path),
            "--output",
            str(output_dir),
            "--dpi",
            "72",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "page_001.png").is_file()
    assert (output_dir / "page_002.png").is_file()
    assert (output_dir / "pages.json").is_file()
    captured = capsys.readouterr()
    assert "Rendered 2 page(s)" in captured.out


def test_cli_render_invalid_pdf_exits_nonzero(tmp_path: Path) -> None:
    pdf_path = tmp_path / "broken.pdf"
    pdf_path.write_bytes(b"not a pdf")

    exit_code = main(
        [
            "render",
            str(pdf_path),
            "--output",
            str(tmp_path / "pages"),
        ]
    )

    assert exit_code == 1
