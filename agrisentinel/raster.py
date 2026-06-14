"""Raster <-> MinIO helpers.

A "window" is the AOI clipped to a common grid (one date = ``t0`` or ``t1``):
several single-band GeoTIFFs plus a JSON manifest recording the grid (CRS,
affine transform, shape) and provenance (STAC item id, date, cloud %). The
change-detection stage reads windows back via :func:`load_window`.
"""

from __future__ import annotations

import json

import numpy as np
from affine import Affine
from rasterio.io import MemoryFile

from agrisentinel.logging import get_logger
from agrisentinel.storage import get_bytes, object_exists, put_bytes

log = get_logger(__name__)


def _window_prefix(aoi_name: str, t_label: str) -> str:
    return f"s2/{aoi_name}/{t_label}"


def write_geotiff_to_s3(key: str, array: np.ndarray, transform: Affine, crs: str) -> str:
    """Write a single-band float32 GeoTIFF (deflate-compressed) to MinIO."""
    arr = np.asarray(array, dtype="float32")
    h, w = arr.shape
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
            compress="deflate",
            predictor=2,
            tiled=True,
        ) as ds:
            ds.write(arr, 1)
        data = mem.read()
    return put_bytes(key, data, content_type="image/tiff")


def read_geotiff_from_s3(key: str) -> tuple[np.ndarray, Affine, str]:
    with MemoryFile(get_bytes(key)) as mem:
        with mem.open() as ds:
            return ds.read(1).astype("float32"), ds.transform, ds.crs.to_string()


def save_window(
    aoi_name: str,
    t_label: str,
    bands: dict[str, np.ndarray],
    transform: Affine,
    crs: str,
    meta: dict,
) -> dict:
    prefix = _window_prefix(aoi_name, t_label)
    band_keys: dict[str, str] = {}
    for band, arr in bands.items():
        key = f"{prefix}/{band}.tif"
        write_geotiff_to_s3(key, arr, transform, crs)
        band_keys[band] = key
    h, w = next(iter(bands.values())).shape
    manifest = {
        "aoi": aoi_name,
        "t_label": t_label,
        "crs": crs,
        "transform": list(transform)[:6],
        "height": int(h),
        "width": int(w),
        "bands": band_keys,
        **meta,
    }
    put_bytes(
        f"{prefix}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        content_type="application/json",
    )
    log.info("Saved window %s/%s (%dx%d, %d bands)", aoi_name, t_label, h, w, len(bands))
    return manifest


def load_manifest(aoi_name: str, t_label: str) -> dict:
    key = f"{_window_prefix(aoi_name, t_label)}/manifest.json"
    return json.loads(get_bytes(key).decode("utf-8"))


def load_window(aoi_name: str, t_label: str) -> tuple[dict[str, np.ndarray], Affine, str, dict]:
    manifest = load_manifest(aoi_name, t_label)
    transform = Affine(*manifest["transform"])
    crs = manifest["crs"]
    bands: dict[str, np.ndarray] = {}
    for band, key in manifest["bands"].items():
        arr, _, _ = read_geotiff_from_s3(key)
        bands[band] = arr
    return bands, transform, crs, manifest


def window_exists(aoi_name: str, t_label: str) -> bool:
    return object_exists(f"{_window_prefix(aoi_name, t_label)}/manifest.json")
