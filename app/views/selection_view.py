"""CLI prompts for selecting inputs (main menu, kunci, PDFs, topics)."""

from __future__ import annotations

from pathlib import Path

from app.interfaces.topic_pack import TopicPack
from app.views.style import bold, box, cyan, dim, green, yellow


def print_main_menu(*, active_topic_label: str = "", active_topic_id: str = "") -> None:
    topic_line = ""
    if active_topic_id or active_topic_label:
        shown = active_topic_label or active_topic_id
        topic_line = dim(f"Topik aktif: {shown} [{active_topic_id}]")
    lines = [
        bold("Math Grader"),
        "",
    ]
    if topic_line:
        lines.extend([topic_line, ""])
    lines.extend(
        [
            "  1. Pilih topik grader",
            "  2. Ingest kunci jawaban (.tex)",
            "  3. Pilih PDF → render halaman → crop ink (konfirmasi)",
            "  4. Crop ulang dari page_*_regions.json",
            "  5. Lanjutkan grading (recognize → report) dari crops",
            "  6. Keluar",
            "",
            dim("Pilih nomor, lalu Enter."),
        ]
    )
    print(cyan(box(lines)))
    print()


def print_topic_menu(packs: list[TopicPack], *, active_topic_id: str = "") -> None:
    lines = [bold("Topik grader"), ""]
    for index, pack in enumerate(packs, start=1):
        marker = " *" if pack.id == active_topic_id else ""
        lines.append(f"  {index}. {pack.label} [{pack.id}]{marker}")
    lines.append("")
    lines.append(dim("Pilih nomor atau id pack, lalu Enter."))
    print(cyan(box(lines)))
    print()


def print_selected_topic(pack: TopicPack) -> None:
    print(green(bold(f"Topik aktif: {pack.label}")))
    print(dim(f"  id={pack.id}"))
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
