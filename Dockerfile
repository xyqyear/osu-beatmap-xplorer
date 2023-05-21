ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-alpine as poetry-base

ARG POETRY_VERSION=1.5.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apk add --no-cache \
        rust \
        cargo \
        curl \
        gcc \
        libressl-dev \
        musl-dev \
        libffi-dev && \
    pip install --no-cache-dir poetry==${POETRY_VERSION} && \
    apk del \
        rust \
        cargo \
        curl \
        gcc \
        libressl-dev \
        musl-dev \
        libffi-dev

FROM poetry-base as app-env

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_NO_INTERACTION=1

WORKDIR /app

COPY poetry.lock pyproject.toml /app/

RUN apk add --no-cache \
        gcc \
        musl-dev && \
    poetry install --no-interaction --no-cache --no-root --without dev && \
    apk del \
        gcc \
        musl-dev

FROM python:${PYTHON_VERSION}-alpine as app

ENV PATH="/app/.venv/bin:$PATH" \
    OSU_WORKING_DIR=/data \
    OSU_HOST=0.0.0.0 \
    OSU_PORT=80

WORKDIR /app

COPY --from=app-env /app/.venv /app/.venv

COPY . /app

RUN mkdir -p /data

EXPOSE 80

CMD ["python3", "-m", "osu_beatmap_xplorer"]
