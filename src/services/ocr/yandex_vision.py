from src.services.ocr.base import OCRProvider


class YandexVisionOCR(OCRProvider):
    """Фолбэк-провайдер (раздел 8 PROJECT_PLAN.md). НЕ реализован: чтобы не рисковать
    рассинхроном с актуальным Yandex Cloud Vision REST API без возможности живой проверки
    (нет ключа), реализация отложена до момента, когда появится доступ и можно будет
    свериться с актуальной документацией и протестировать вживую — см. PROJECT_PLAN.md.
    """

    async def extract_text(self, image_bytes: bytes) -> str:
        raise NotImplementedError(
            "YandexVisionOCR ещё не реализован — используйте GoogleVisionOCR (основной провайдер)"
        )
