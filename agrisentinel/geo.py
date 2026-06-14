"""Geometry helpers. Convention: **store** geometries as EPSG:4326 (lon/lat),
**measure** them in the AOI ``working_crs`` (EPSG:3826, metres). All CRS
conversions are funnelled through here so the lon/lat ↔ metres boundary lives in
one place."""

from __future__ import annotations

import functools

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import transform as shp_transform

WGS84 = "EPSG:4326"


@functools.lru_cache(maxsize=32)
def _transformer(src: str, dst: str) -> Transformer:
    return Transformer.from_crs(src, dst, always_xy=True)


def reproject_geom(geom, src: str, dst: str):
    if src == dst:
        return geom
    return shp_transform(_transformer(src, dst).transform, geom)


def bbox_polygon(bbox: tuple[float, float, float, float]) -> Polygon:
    """Polygon for [min_lon, min_lat, max_lon, max_lat] in EPSG:4326."""
    return box(*bbox)


def area_m2(geom_wgs84, working_crs: str) -> float:
    """Area in m² of a EPSG:4326 geometry, measured in ``working_crs``."""
    return float(reproject_geom(geom_wgs84, WGS84, working_crs).area)


def to_geojson(geom) -> dict:
    return mapping(geom)


def geom_from_geojson(obj: dict):
    return shape(obj)


def mask_to_polygons(
    mask: np.ndarray,
    transform,
    raster_crs: str,
    *,
    working_crs: str,
    min_area_m2: float = 0.0,
):
    """Vectorise a boolean change mask into EPSG:4326 polygons.

    Returns a list of ``(polygon_wgs84, area_m2)`` for connected ``True``
    regions whose area (measured in ``working_crs``) is ≥ ``min_area_m2``.
    """
    from rasterio import features

    out: list[tuple[Polygon, float]] = []
    binary = mask.astype("uint8")
    for geom, val in features.shapes(binary, mask=mask.astype(bool), transform=transform):
        if int(val) != 1:
            continue
        poly_raster = shape(geom)
        if not poly_raster.is_valid:
            poly_raster = poly_raster.buffer(0)
        poly_wgs84 = reproject_geom(poly_raster, str(raster_crs), WGS84)
        a = area_m2(poly_wgs84, working_crs)
        if a >= min_area_m2:
            out.append((poly_wgs84, a))
    return out


def wkt(geom) -> str:
    return shapely.to_wkt(geom, rounding_precision=7)
