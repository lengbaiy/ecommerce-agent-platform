# syntax=docker/dockerfile:1

FROM python:3.11-slim AS runtime

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=4 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY app/__init__.py ./app/__init__.py

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install .

COPY . .
RUN pip install --no-deps --no-build-isolation -e .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM runtime AS test

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-build-isolation -e ".[dev]"

CMD ["pytest", "-q"]
