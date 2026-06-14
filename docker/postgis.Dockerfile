# PostGIS + pgvector in one image. The official postgis/postgis image is
# Debian-based with the PGDG apt source already configured, so pgvector installs
# cleanly as a package — giving us spatial joins and vector search in one store.
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*
