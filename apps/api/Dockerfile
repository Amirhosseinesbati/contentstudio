FROM python:3.12.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/apps/api/src
WORKDIR /app/apps/api

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN pip install --no-cache-dir uv==0.11.28 && uv sync --locked --no-dev --no-install-project
COPY fixtures /app/fixtures
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/migrations ./migrations

ENV FIXTURES_ROOT=/app/fixtures MEDIA_ROOT=/data/media PATH=/app/apps/api/.venv/bin:$PATH
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m contentstudio.checkpoint_init && exec uvicorn contentstudio.main:app --host 0.0.0.0 --port 8000"]
