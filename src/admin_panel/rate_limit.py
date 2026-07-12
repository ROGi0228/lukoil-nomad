from redis.asyncio import Redis

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300


async def register_login_attempt(redis: Redis, identifier: str) -> bool:
    """Увеличивает счётчик попыток логина для identifier (обычно IP-адрес) и
    возвращает True, если лимит ещё не превышен. Считает все попытки, а не только
    неудачные — та же простая логика, что и throttling-middleware бота."""
    key = f"admin_login_attempts:{identifier}"
    attempts: int = int(await redis.incr(key))
    if attempts == 1:
        await redis.expire(key, LOGIN_LOCKOUT_SECONDS)
    return attempts <= MAX_LOGIN_ATTEMPTS
