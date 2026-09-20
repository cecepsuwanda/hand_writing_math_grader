"""CLI prompts for selecting input PDFs."""

from __future__ import annotations

from pathlib import Path


def print_jawaban_menu(pdfs: list[Path], jawaban_dir: Path) -> None:
    print(f"PDF tersedia di {jawaban_dir}:")
    for index, pdf in enumerate(pdfs, start=1):
        print(f"  {index}. {pdf.name}")
    print()
    print("Pilih nomor (atau nama file), lalu Enter.")


def print_output_cleared(output_root: Path, removed_names: list[str]) -> None:
    print(f"Membersihkan {output_root} (kecuali standards/)...")
    if not removed_names:
        print("  (sudah kosong)")
    else:
        for name in removed_names:
            print(f"  - removed {name}")
    print()


def print_selected_pdf(pdf: Path) -> None:
    print(f"Memproses: {pdf}")
    print()
