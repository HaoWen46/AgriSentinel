# AgriSentinel application image (API, worker, and pipeline stages).
# Self-contained: rasterio/shapely/pyproj/psycopg ship manylinux wheels with
# GDAL/GEOS/PROJ/libpq bundled, so no system geo libraries are needed.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Runtime libs the manylinux wheels load dynamically on Debian slim:
#   libexpat1 → GDAL (rasterio), libgomp1 → OpenMP (scikit-learn), CA certs → HTTPS.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# uv is the package manager (per project convention).
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . /app

# Editable install so the package's __file__ stays under /app — this keeps
# repo_root() (and thus config/, data/laws_seed/, scripts/, dashboard/) resolvable
# whether code is invoked via `python -m ...` or the `agrisentinel` console script.
RUN uv pip install --system -e .

EXPOSE 8000
CMD ["python", "-m", "agrisentinel.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
