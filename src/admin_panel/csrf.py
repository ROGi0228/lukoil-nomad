import secrets

from fastapi import Form, HTTPException, Request
from starlette import status

CSRF_SESSION_KEY = "csrf_token"


def get_csrf_token(request: Request) -> str:
    """Возвращает CSRF-токен текущей сессии, создавая его при первом обращении.
    Работает и для ещё не залогиненного посетителя — SessionMiddleware выдаёт
    сессионную куку независимо от того, аутентифицирован пользователь или нет.
    """
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


async def csrf_protect(request: Request, csrf_token: str = Form(...)) -> None:
    session_token = request.session.get(CSRF_SESSION_KEY)
    if not session_token or not secrets.compare_digest(session_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Неверный CSRF-токен")
