# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# Install deps first (better layer caching)
COPY pyproject.toml ./
RUN uv sync --no-install-project

COPY . .
RUN uv sync

EXPOSE 8000
# Dev default; compose overrides command for the worker.
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
