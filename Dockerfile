# 1. Use a stable, production-grade slim Python base image
FROM python:3.11-slim

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
    curl \
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

# 8. Copy the application entry points and modular source code into the container
COPY app.py main.py ./
COPY src/ ./src/

# 9. Expose the Streamlit default port for the analytical dashboard
EXPOSE 8501

# 10. Healthcheck for AWS App Runner and container orchestration
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 11. Default entrypoint: serve the Streamlit executive dashboard
CMD ["uv", "run", "streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]

# NOTE: The 'data' directory and '.env' are NOT copied into the image.
# They are dynamically mounted and injected at runtime via Docker Compose.