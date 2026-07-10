import asyncio

from google.cloud import vision

from src.services.ocr.base import OCRProvider


class GoogleVisionOCR(OCRProvider):
    """Использует Vision API document_text_detection — лучше подходит для
    плотных структурированных документов (бланков), чем обычный text_detection.

    Требует GOOGLE_APPLICATION_CREDENTIALS (путь к service account JSON) в окружении —
    SDK подхватывает его автоматически, отдельно передавать не нужно.
    """

    def __init__(self) -> None:
        self._client = vision.ImageAnnotatorClient()

    async def extract_text(self, image_bytes: bytes) -> str:
        return await asyncio.to_thread(self._extract_text_sync, image_bytes)

    def _extract_text_sync(self, image_bytes: bytes) -> str:
        image = vision.Image(content=image_bytes)
        response = self._client.document_text_detection(image=image)
        if response.error.message:
            raise RuntimeError(f"Google Vision error: {response.error.message}")
        return str(response.full_text_annotation.text)
