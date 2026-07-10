from abc import ABC, abstractmethod


class FileStorage(ABC):
    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        """Загружает файл и возвращает его ключ в хранилище."""

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Скачивает файл по ключу."""
