"""CLI prompts for selecting inputs (main menu, kunci, PDFs)."""

from __future__ import annotations

from pathlib import Path

from app.views.style import bold, box, cyan, dim, green, yellow


def print_main_menu() -> None:
    lines = [
        bold("Math Grader"),
        "",
        "  1. Ingest kunci jawaban (.tex)",
        "  2. Pilih PDF → render halaman → crop ink (konfirmasi)",
        "  3. Crop ulang dari page_*_regions.json",
        "  4. Lanjutkan grading (recognize → report) dari crops",
        "  5. Keluar",
        "",
        dim("Pilih nomor, lalu Enter."),
    ]
    print(cyan(box(lines)))
    print()


def print_kunci_menu(tex_files: list[Path], kunci_dir: Path) -> None:
    lines = [bold("Kunci tersedia"), dim(str(kunci_dir)), ""]
    for index, path in enumerate(tex_files, start=1):
        lines.append(f"  {index}. {path.name}")
    lines.append("")
    lines.append(dim("Pilih nomor (atau nama file), lalu Enter."))
    print(cyan(box(lines)))
    print()


def print_selected_kunci(path: Path) -> None:
    print(green(bold(f"Ingest kunci: {path.name}")))
    print(dim(f"  {path}"))
    print()


def print_jawaban_menu(pdfs: list[Path], jawaban_dir: Path) -> None:
    lines = [bold("PDF tersedia"), dim(str(jawaban_dir)), ""]
    for index, pdf in enumerate(pdfs, start=1):
        lines.append(f"  {index}. {pdf.name}")
    lines.append("")
    lines.append(dim("Pilih nomor (atau nama file), lalu Enter."))
    print(cyan(box(lines)))
    print()


def print_output_cleared(output_root: Path, removed_names: list[str]) -> None:
    print(yellow(bold("Membersihkan workspace")))
    print(dim(f"  {output_root} (kecuali standards/)"))
    if not removed_names:
        print(dim("  (sudah kosong)"))
    else:
        for name in removed_names:
            print(f"  - removed {name}")
    print()


def print_selected_pdf(pdf: Path) -> None:
    print(green(bold(f"Memproses: {pdf.name}")))
    print(dim(f"  {pdf}"))
    print()
