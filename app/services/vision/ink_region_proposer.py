"""OOP wrapper: page image → DetectedRegion proposals via ink layout FP."""

from __future__ import annotations

from pathlib import Path

from app.functions.ink_layout import InkLayoutParams, propose_solution_regions_from_image
from app.models.recognition import DetectedRegion


class InkRegionProposer:
    """Propose per-question solution boxes from ink clustering (no LLM)."""

    def __init__(self, params: InkLayoutParams | None = None) -> None:
        self._params = params or InkLayoutParams()

    @property
    def params(self) -> InkLayoutParams:
        return self._params

    def propose(self, image_path: Path, page_number: int = 1) -> list[DetectedRegion]:
        from PIL import Image

        del page_number  # reserved for future page-aware heuristics
        image_path = Path(image_path)
        with Image.open(image_path) as image:
            regions = propose_solution_regions_from_image(image, params=self._params)

        detected: list[DetectedRegion] = []
        for index, region in enumerate(regions):
            # question_number stays 0: page-local index must not become a real
            # exam number (multi-page merge would collide). LLM + exam stems assign numbers.
            detected.append(
                DetectedRegion(
                    type="solution",
                    region=region,
                    question_number=0,
                    order=index,
                )
            )
        return detected
