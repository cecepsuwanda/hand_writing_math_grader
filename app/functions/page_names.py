"""Deterministic page artifact names."""

PAGES_METADATA_FILENAME = "pages.json"


def page_image_filename(page_number: int) -> str:
    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")
    return f"page_{page_number:03d}.png"


def page_recognition_filename(page_number: int) -> str:
    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")
    return f"page_{page_number:03d}_recognition.json"
