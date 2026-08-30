# Backend image. Used by docker-compose (profile "full") and by deployment.
#
# The build context is the REPOSITORY ROOT, not `backend/`, because the
# application reads `config/*.yaml` - the role definitions, intelligence
# scores, similarity features and the provider mapping - and those live beside
# `backend/` rather than inside it. Docker cannot reach outside its context, so
# a context of `backend/` cannot copy them at any price.
#
# The image mirrors the repository layout for the same reason: the code locates
# the configuration by walking up until it finds a `config/` directory, and a
# flattened image would leave it walking past the top.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

# Dependencies are installed from the manifest alone so the layer caches across
# source edits.
COPY backend/pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

# The analytical definitions. Without these the engines load nothing, and the
# failure reads as "no roles are configured" rather than as a missing directory.
COPY config /app/config

# Run as an unprivileged user: a container compromise should not be root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
