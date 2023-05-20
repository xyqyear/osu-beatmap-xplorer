FROM python:3.11-alpine as python-base

ENV POETRY_VERSION=1.5.0
ENV POETRY_HOME=/opt/poetry
ENV POETRY_VENV=/opt/poetry-venv
ENV OSU_WORKING_DIR=/data
ENV OSU_HOST=0.0.0.0

ENV POETRY_CACHE_DIR=/opt/.cache

FROM python-base as poetry-base

RUN python3 -m venv $POETRY_VENV \
    && $POETRY_VENV/bin/pip install -U pip setuptools \
    && $POETRY_VENV/bin/pip install poetry==${POETRY_VERSION}

FROM python-base as app

COPY --from=poetry-base ${POETRY_VENV} ${POETRY_VENV}

ENV PATH="${PATH}:${POETRY_VENV}/bin"

WORKDIR /app

COPY poetry.lock pyproject.toml /app/

RUN poetry install --no-interaction --no-cache --no-root --without dev

COPY . /app

EXPOSE 80
CMD [ "poetry", "run", "python", "osu_beatmap_xplorer/__main__.py"]
