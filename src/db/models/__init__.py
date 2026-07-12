# Импортировать здесь ВСЕ модели обязательно: relationship() между Application/User
# резолвится SQLAlchemy по имени класса в общем реестре в момент первого использования
# ORM, а не только в момент объявления модели. Если какой-то процесс (например,
# admin-panel) импортирует только Application, но не User, конфигурация мапперов
# падает с "failed to locate a name" — ошибку не видно до первого реального запроса.
from src.db.models.admin_user import AdminUser
from src.db.models.application import Application
from src.db.models.base import Base
from src.db.models.moderation_log import ModerationLog
from src.db.models.user import User

__all__ = ["AdminUser", "Application", "Base", "ModerationLog", "User"]
