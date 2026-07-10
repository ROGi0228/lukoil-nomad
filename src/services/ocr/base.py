from abc import ABC, abstractmethod


class OCRProvider(ABC):
    @abstractmethod
    async def extract_text(self, image_bytes: bytes) -> str:
        """Возвращает сырой распознанный текст документа."""
