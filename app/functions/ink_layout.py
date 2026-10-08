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
    long_line_ratio: float = 0.1
    paper_offset: int = 40


def binarize_ink(gray: bytes, *, threshold: int) -> bytes:
    """Return mask bytes: 1 = ink (darker than threshold), 0 = paper."""
    thr = max(0, min(255, int(threshold)))
    return gray.translate(bytes(1 if value < thr else 0 for value in range(256)))


_PAPER_SAMPLE_STRIDE = 97


def ink_threshold(gray: bytes, *, threshold: int, paper_offset: int) -> int:
    """``threshold``, lowered to sit ``paper_offset`` below the paper level.

    A phone photo leaves the paper grey (~185); a fixed cut-off of 200 would
    read the whole sheet as ink. The median grey is the paper on any page
    that is mostly blank.
    """
    if paper_offset <= 0 or not gray:
        return threshold
    sample = sorted(gray[::_PAPER_SAMPLE_STRIDE])
    paper = sample[len(sample) // 2]
    return max(1, min(threshold, paper - paper_offset))


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


def remove_long_vertical_runs(
    mask: bytes, *, width: int, height: int, min_run: int
) -> bytes:
    """Clear vertical ink runs of ``min_run`` rows or more.

    Handwriting strokes are short; page borders, scan edges and dark photo
    backgrounds run most of the page height and would otherwise read as ink.
    """
    if min_run <= 0 or width <= 0 or height <= 0:
        return mask
    mask = mask[: width * height]
    out = bytearray(mask)
    for x in range(width):
        y = 0
        for piece in mask[x::width].split(b"\x00"):
            run = len(piece)
            if run >= min_run:
                start = y * width + x
                out[start : start + run * width : width] = bytes(run)
            y += run + 1
    return bytes(out)


def _smooth(values: list[int], radius: int) -> list[float]:
    prefix = [0]
    for value in values:
        prefix.append(prefix[-1] + value)
    size = len(values)
    smoothed: list[float] = []
    for x in range(size):
        lo, hi = max(0, x - radius), min(size, x + radius + 1)
        smoothed.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return smoothed


def _plateau_middle(values: list[float], start: int, end: int) -> int:
    low = min(values[start:end])
    lows = [x for x in range(start, end) if values[x] == low]
    return lows[len(lows) // 2]


# A column carries a real share of the page's ink, not one overhanging line.
_MIN_COLUMN_INK_SHARE = 0.1


def detect_columns(
    mask: bytes,
    *,
    width: int,
    height: int,
    valley_ratio: float,
    y_min: int = 0,
    min_column_ratio: float = 0.15,
) -> list[tuple[int, int]]:
    """Contiguous column spans ``(x0, x1)`` split at every ink gutter.

    A gutter is a stretch whose ink is at most ``valley_ratio`` of the weaker
    neighbouring column peak (each side looked at over ``min_column_ratio`` of
    the width), so an empty margin or a sparse part of one column is not a
    gutter. Rows above ``y_min`` (a header written across columns) are ignored.
    """
    if width <= 0 or height <= 0 or not mask:
        return []
    body = mask[max(0, y_min) * width : height * width]
    counts = [body[x::width].count(1) for x in range(width)]
    if max(counts, default=0) <= 0:
        return [(0, width)]

    smoothed = _smooth(counts, max(1, width // 200))
    window = max(1, int(width * min_column_ratio))
    is_gutter = []
    for x in range(width):
        left = max(smoothed[max(0, x - window) : x], default=0.0)
        right = max(smoothed[x + 1 : x + 1 + window], default=0.0)
        weaker = min(left, right)
        is_gutter.append(weaker > 0 and smoothed[x] <= valley_ratio * weaker)

    prefix = [0]
    for count in counts:
        prefix.append(prefix[-1] + count)
    min_ink = prefix[-1] * _MIN_COLUMN_INK_SHARE

    cuts: list[int] = []
    previous = 0
    x = 0
    while x < width:
        if not is_gutter[x]:
            x += 1
            continue
        end = x
        while end < width and is_gutter[end]:
            end += 1
        cut = _plateau_middle(smoothed, x, end)
        wide_enough = cut - previous >= window and width - cut >= window
        inked = (
            prefix[cut] - prefix[previous] >= min_ink
            and prefix[-1] - prefix[cut] >= min_ink
        )
        if wide_enough and inked:
            cuts.append(cut)
            previous = cut
        x = end

    edges = [0, *cuts, width]
    return list(zip(edges[:-1], edges[1:]))


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


_SHORT_BLOCK_REACH = 3


def _absorb_short_blocks(
    blocks: list[tuple[int, int]],
    *,
    min_block_height: int,
    max_gap: int,
) -> list[tuple[int, int]]:
    """Fold each short block into its nearer neighbour within ``max_gap``.

    A short block is usually the last line of a solution (``HP = ...``) or a
    separator written a little apart; dropping it loses work. Short blocks
    with no neighbour in reach (a scanner footer, a stray mark) are dropped.
    """
    result = list(blocks)
    while True:
        short = next(
            (i for i, (y0, y1) in enumerate(result) if y1 - y0 < min_block_height),
            None,
        )
        if short is None:
            return result
        y0, y1 = result[short]
        gaps = []
        if short > 0:
            gaps.append((y0 - result[short - 1][1], short - 1))
        if short + 1 < len(result):
            gaps.append((result[short + 1][0] - y1, short + 1))
        reachable = [(gap, i) for gap, i in gaps if gap <= max_gap]
        if not reachable:
            del result[short]
            continue
        _gap, neighbour = min(reachable)
        lo, hi = sorted((short, neighbour))
        result[lo : hi + 1] = [(result[lo][0], result[hi][1])]


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

    clipped = [(max(y0, y_min), y1) for y0, y1 in merged if y1 > y_min]
    blocks = _absorb_short_blocks(
        clipped,
        min_block_height=min_block_height,
        max_gap=_SHORT_BLOCK_REACH * merge_gap,
    )

    regions: list[Region] = []
    for y0, y1 in blocks:
        block_height = y1 - y0
        tight_x0, tight_x1 = _horizontal_bounds(mask, width, x0, x1, y0, y1)
        # A sliver this thin is a paper edge or shadow, never a written answer.
        if tight_x1 - tight_x0 < min_block_height:
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

    gray = gray[: width * height]
    threshold = ink_threshold(
        gray, threshold=cfg.threshold, paper_offset=cfg.paper_offset
    )
    mask = remove_long_vertical_runs(
        binarize_ink(gray, threshold=threshold),
        width=width,
        height=height,
        min_run=int(round(height * cfg.long_line_ratio)),
    )
    y_min = int(round(height * cfg.header_fraction))
    columns = detect_columns(
        mask,
        width=width,
        height=height,
        valley_ratio=cfg.column_valley_ratio,
        y_min=y_min,
    )
    if not columns:
        columns = [(0, width)]

    merge_gap = max(4, int(round(height * cfg.merge_gap_ratio)))
    min_block_height = max(12, int(round(height * cfg.min_block_height_ratio)))
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

