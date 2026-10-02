"""CLI prompts for selecting inputs (main menu, kunci, PDFs, runs, topics)."""

from __future__ import annotations

from pathlib import Path

from app.functions.menu_choices import MAIN_MENU, MAIN_MENU_PROMPT
from app.functions.standards_layout import standards_folder_name
from app.interfaces.topic_pack import TopicPack
from app.views.prompt_view import InputFn, read_line
from app.views.style import bold, box, cyan, dim, green, yellow


def _print_menu_box(lines: list[str]) -> None:
    print(cyan(box(lines)))
    print()


def _print_path_menu(title: str, folder: Path, paths: list[Path], hint: str) -> None:
    lines = [bold(title), dim(str(folder)), ""]
    lines.extend(f"  {index}. {path.name}" for index, path in enumerate(paths, start=1))
    lines.extend(["", dim(hint)])
    _print_menu_box(lines)


def _print_selected(headline: str, detail: str) -> None:
    print(green(bold(headline)))
    print(dim(f"  {detail}"))
    print()


def print_main_menu(
    *,
    active_topic_label: str = "",
    active_topic_id: str = "",
    standard_dir: Path | None = None,
) -> None:
    lines = [bold("Math Grader"), ""]
    if active_topic_id or active_topic_label:
        shown = active_topic_label or active_topic_id
        lines.append(dim(f"Topik aktif: {shown} [{active_topic_id}]"))
        if standard_dir is not None:
            lines.append(dim(f"Standar: {standard_dir}"))
        lines.append("")
    lines.extend(
        f"  {index}. {entry.label}" for index, entry in enumerate(MAIN_MENU, start=1)
    )
    lines.extend(["", dim("Pilih nomor, lalu Enter.")])
    _print_menu_box(lines)


def prompt_main_menu_choice(*, input_fn: InputFn | None = None) -> str | None:
    """Raw main-menu answer, or ``None`` on EOF / Ctrl+C."""
    return read_line(MAIN_MENU_PROMPT, input_fn=input_fn)


def prompt_topic_choice(*, input_fn: InputFn | None = None) -> str | None:
    return read_line("Pilihan topik: ", input_fn=input_fn)


def print_topic_menu(packs: list[TopicPack], *, active_topic_id: str = "") -> None:
    lines = [bold("Topik grader"), ""]
    for index, pack in enumerate(packs, start=1):
        marker = " *" if pack.id == active_topic_id else ""
        folder = standards_folder_name(pack.id)
        lines.append(f"  {index}. {pack.label} [{pack.id}] → {folder}{marker}")
    lines.extend(["", dim("Pilih nomor, id pack, atau topik_<bab>, lalu Enter.")])
    _print_menu_box(lines)


def print_selected_topic(pack: TopicPack) -> None:
    _print_selected(f"Topik aktif: {pack.label}", f"id={pack.id}")


def print_kunci_menu(tex_files: list[Path], kunci_dir: Path) -> None:
    _print_path_menu(
        "Kunci tersedia", kunci_dir, tex_files, "Pilih nomor (atau nama file), lalu Enter."
    )


def print_selected_kunci(path: Path) -> None:
    _print_selected(f"Ingest kunci: {path.name}", str(path))


def print_jawaban_menu(pdfs: list[Path], jawaban_dir: Path) -> None:
    _print_path_menu(
        "PDF tersedia", jawaban_dir, pdfs, "Pilih nomor (atau nama file), lalu Enter."
    )


def print_selected_pdf(pdf: Path) -> None:
    _print_selected(f"Memproses: {pdf.name}", str(pdf))


def print_run_menu(run_dirs: list[Path], output_root: Path) -> None:
    _print_path_menu(
        "Folder hasil (per PDF)",
        output_root,
        run_dirs,
        "Pilih nomor (atau nama folder), lalu Enter.",
    )


def print_selected_run(run_root: Path) -> None:
    _print_selected(f"Folder hasil: {run_root.name}", str(run_root))


def print_output_cleared(run_root: Path, removed_names: list[str]) -> None:
    print(yellow(bold("Membersihkan workspace")))
    print(dim(f"  {run_root}"))
    if not removed_names:
        print(dim("  (sudah kosong)"))
    else:
        for name in removed_names:
            print(f"  - removed {name}")
    print()
