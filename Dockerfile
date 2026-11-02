# ClimateAdapt Lab backend: FastAPI + deterministic pipelines.
#
# Python 3.11 slim. rasterio/scipy/netCDF4 install from manylinux wheels with
# bundled GDAL/HDF5 (verified: rasterio 1.4.4 cp311 manylinux_x86_64 on PyPI),
# so no compilers or system GIS libraries are needed. CPU-only; the `dense`
# extra (torch) is deliberately NOT installed here.
# Pattern: uv Docker guide (COPY --from ghcr.io/astral-sh/uv, uv sync --locked).
FROM python:3.11-slim-bookworm AS base

# Install system libraries required by rasterio / GDAL wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    libexpat1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

FROM base AS deps
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

COPY src ./src
COPY corpus ./corpus
COPY demo ./demo
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENV PATH="/app/.venv/bin:$PATH" \
    CLIMATEADAPT_DATA_DIR=/app/data

EXPOSE 8000
CMD ["uvicorn", "climateadapt.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
