# 1. Use the exact, high-performance slim Python image mirroring your Fedora environment
FROM python:3.14-slim

# 2. Recommended environment variables for Python in containers
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Native optimizations for 'uv' inside Docker
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# 4. Install minimal system build dependencies for Polars/DuckDB if compilation is triggered
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 5. Copy the pure 'uv' binary directly from Astral's official Docker image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 6. Copy ONLY dependency files first to exploit Docker layer caching.
# This prevents downloading packages again unless pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./

# 7. Strictly sync dependencies using the lockfile (--frozen)
# We mount a cache to make subsequent builds instantaneous.
# --no-install-project prevents packaging the src/ directory as a Python package.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# 8. Copy the unified entry point and modular source code into the container
COPY main.py ./
COPY src/ ./src/

# NOTE: The 'data' directory and '.env' are NOT copied into the image.
# They are dynamically mounted and injected at runtime via Docker Compose.