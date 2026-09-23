"""Deterministic ink projection layout → solution region proposals (pure FP).

Uses flat byte buffers (not nested lists) for grayscale/mask projections.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.recognition import Region


@dataclass(frozen=True)
class InkLayoutParams:
    threshold: int = 200
    merge_gap_ratio: float = 0.018
    min_block_height_ratio: float = 0.03
    header_fraction: float = 0.08
    column_valley_ratio: float = 0.15
    margin_ratio: float = 0.02
    min_row_ink_ratio: float = 0.002


def binarize_ink(gray: bytes, *, threshold: int) -> bytes:
    """Return mask bytes: 1 = ink (darker than threshold), 0 = paper."""
    thr = max(0, min(255, int(threshold)))
    return bytes(1 if value < thr else 0 for value in gray)


def _column_ink_counts(mask: bytes, *, width: int, height: int) -> list[int]:
    counts = [0] * width
    for y in range(height):
        row = y * width
        for x in range(width):
            if mask[row + x]:
                counts[x] += 1
    return counts


def _row_ink_counts(
    mask: bytes,
    *,
    width: int,
    height: int,
    x0: int,
    x1: int,
) -> list[int]:
    counts = [0] * height
    for y in range(height):
        row = y * width
        total = 0
        for x in range(x0, x1):
            if mask[row + x]:
                total += 1
        counts[y] = total
    return counts


def detect_columns(
    mask: bytes,
    *,
    width: int,
    height: int,
    valley_ratio: float,
) -> list[tuple[int, int]]:
    """Return column spans (x0, x1). One span if no clear middle valley."""
    if width <= 0 or height <= 0 or not mask:
        return []
    counts = _column_ink_counts(mask, width=width, height=height)
    max_count = max(counts) if counts else 0
    if max_count <= 0:
        return [(0, width)]

    mid_lo = width // 3
    mid_hi = (2 * width) // 3
    valley_x = min(range(mid_lo, mid_hi), key=lambda x: counts[x])
    valley = counts[valley_x]
    if valley > max_count * valley_ratio:
        return [(0, width)]

    threshold = max_count * valley_ratio
    left = valley_x
    while left > mid_lo and counts[left] <= threshold:
        left -= 1
    right = valley_x
    while right < mid_hi - 1 and counts[right] <= threshold:
        right += 1

    left_span = (0, max(left, 1))
    right_span = (min(right + 1, width - 1), width)
    if left_span[1] - left_span[0] < width * 0.15:
        return [(0, width)]
    if right_span[1] - right_span[0] < width * 0.15:
        return [(0, width)]
    return [left_span, right_span]


def _ink_runs(
    counts: list[int],
    *,
    min_count: int,
) -> list[tuple[int, int]]:
    """Inclusive-exclusive index runs where count >= min_count."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(counts):
        if value >= min_count:
            if start is None:
                start = index
        elif start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(counts)))
    return runs


def cluster_vertical_blocks(
    mask: bytes,
    *,
    width: int,
    height: int,
    x0: int,
    x1: int,
    merge_gap: int,
    min_block_height: int,
    min_row_ink: int,
    y_min: int,
) -> list[Region]:
    """Cluster ink rows in [x0,x1) into vertical solution blocks."""
    del height  # bounds come from mask length / width
    counts = _row_ink_counts(mask, width=width, height=len(mask) // width, x0=x0, x1=x1)
    runs = _ink_runs(counts, min_count=min_row_ink)
    if not runs:
        return []

    merged: list[tuple[int, int]] = [runs[0]]
    for start, end in runs[1:]:
        prev_start, prev_end = merged[-1]
        gap = start - prev_end
        if gap <= merge_gap:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))

    regions: list[Region] = []
    for y0, y1 in merged:
        if y1 <= y_min:
            continue
        y0 = max(y0, y_min)
        block_height = y1 - y0
        if block_height < min_block_height:
            continue
        tight_x0, tight_x1 = _horizontal_bounds(mask, width, x0, x1, y0, y1)
        if tight_x1 <= tight_x0:
            continue
        regions.append(
            Region(
                x=tight_x0,
                y=y0,
                width=tight_x1 - tight_x0,
                height=block_height,
            )
        )
    return regions


def _horizontal_bounds(
    mask: bytes,
    width: int,
    x0: int,
    x1: int,
    y0: int,
    y1: int,
) -> tuple[int, int]:
    left = x1
    right = x0
    for y in range(y0, y1):
        row = y * width
        for x in range(x0, x1):
            if mask[row + x]:
                if x < left:
                    left = x
                if x + 1 > right:
                    right = x + 1
    if right <= left:
        return x0, x1
    return left, right


def grayscale_bytes(image: object) -> tuple[bytes, int, int]:
    """Convert a PIL image to flat grayscale bytes."""
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise TypeError("expected PIL Image")
    gray = image.convert("L")
    width, height = gray.size
    if hasattr(gray, "tobytes"):
        data = gray.tobytes()
    else:
        data = bytes(gray.getdata())
    return data, width, height


def propose_solution_regions(
    gray: bytes,
    *,
    width: int,
    height: int,
    params: InkLayoutParams | None = None,
) -> list[Region]:
    """Propose axis-aligned solution boxes from ink geometry (reading order)."""
    cfg = params or InkLayoutParams()
    if width <= 0 or height <= 0 or not gray:
        return []
    if len(gray) < width * height:
        return []

    mask = binarize_ink(gray, threshold=cfg.threshold)
    columns = detect_columns(
        mask, width=width, height=height, valley_ratio=cfg.column_valley_ratio
    )
    if not columns:
        columns = [(0, width)]

    merge_gap = max(4, int(round(height * cfg.merge_gap_ratio)))
    min_block_height = max(12, int(round(height * cfg.min_block_height_ratio)))
    y_min = int(round(height * cfg.header_fraction))
    margin = int(round(width * cfg.margin_ratio))
    col_width_ref = max(columns[0][1] - columns[0][0], 1)
    min_row_ink = max(2, int(round(col_width_ref * cfg.min_row_ink_ratio)))

    regions: list[Region] = []
    for x0, x1 in columns:
        x0c = max(0, x0 + margin // 2)
        x1c = min(width, x1 - margin // 2)
        if x1c <= x0c:
            x0c, x1c = x0, x1
        regions.extend(
            cluster_vertical_blocks(
                mask,
                width=width,
                height=height,
                x0=x0c,
                x1=x1c,
                merge_gap=merge_gap,
                min_block_height=min_block_height,
                min_row_ink=min_row_ink,
                y_min=y_min,
            )
        )

    return regions


def propose_solution_regions_from_image(
    image: object,
    *,
    params: InkLayoutParams | None = None,
) -> list[Region]:
    gray, width, height = grayscale_bytes(image)
    return propose_solution_regions(
        gray, width=width, height=height, params=params
    )

