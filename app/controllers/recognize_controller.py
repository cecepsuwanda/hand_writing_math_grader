from pathlib import Path

from app.functions.page_names import page_recognition_filename
from app.interfaces.recognizer import VisionRecognizer
from app.interfaces.renderer import PdfRenderer
from app.models.page import Page
from app.models.recognition import PageRecognition, RecognizeResult


class RecognizeController:
    def __init__(
        self,
        renderer: PdfRenderer,
        recognizer: VisionRecognizer,
    ) -> None:
        self._renderer = renderer
        self._recognizer = recognizer

    def recognize(
        self,
        pdf_path: Path,
        pages_dir: Path,
        recognition_dir: Path,
        dpi: int,
    ) -> RecognizeResult:
        pages = self._renderer.render(pdf_path, pages_dir, dpi)
        return self.recognize_pages(pages, pages_dir, recognition_dir)

    def recognize_pages(
        self,
        pages: list[Page],
        pages_dir: Path,
        recognition_dir: Path,
    ) -> RecognizeResult:
        recognitions: list[PageRecognition] = []
        artifact_paths: list[Path] = []
        for page in pages:
            image_path = pages_dir / page.image
            recognition = self._recognizer.recognize_page(image_path, page.page_number)
            recognitions.append(recognition)
            artifact_paths.append(
                recognition_dir / page_recognition_filename(page.page_number)
            )
        return RecognizeResult(
            pages=recognitions,
            output_dir=recognition_dir,
            artifact_paths=artifact_paths,
        )
