FROM python:3.12.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home /app app
COPY requirements.txt ./
RUN pip install --requirement requirements.txt
COPY alembic ./alembic
COPY alembic.ini ./
COPY app ./app
COPY skills ./skills
RUN chown -R app:app /app
USER app

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
