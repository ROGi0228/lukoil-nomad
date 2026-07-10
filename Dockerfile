FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt requirements/prod.txt requirements/
RUN pip install -r requirements/prod.txt

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

CMD ["python", "-m", "src.bot.main"]
