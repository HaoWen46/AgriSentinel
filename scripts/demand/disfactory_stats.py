"""Demand evidence (Component 2): quantify the problem from Disfactory data.

Reproducible: pulls real reported-factory records around the pilot AOI from the
Disfactory public API, buckets them by report year (the new-per-year trend), and
cross-checks against the public island-wide figures. Writes JSON + CSV (+ a PNG
chart if matplotlib is available).

Run: ``uv run --extra demand python scripts/demand/disfactory_stats.py``
"""

from __future__ import annotations

import csv
import json
from collections import Counter

import httpx

from agrisentinel.config import ensure_dir, get_aoi, repo_root

DISFACTORY_API = "https://api.disfactory.tw/api/factories"
STATS_API = "https://api.disfactory.tw/api/statistics/factories"

# Public island-wide figures to cross-check against (cite at report time).
PUBLIC_FIGURES = {
    "total_illegal_factories_estimate": "~50,000",
    "new_per_year_estimate": "3,000–6,000",
    "farmland_lost_ha_per_year": "~1,500",
    "sources": [
        "地球公民基金會 (CET) reporting",
        "Disfactory project (disfactory.tw)",
        "Ministry of Economic Affairs unregistered-factory statistics",
    ],
}


def fetch_factories(lon: float, lat: float, range_km: float) -> list[dict]:
    with httpx.Client(timeout=60.0) as c:
        r = c.get(DISFACTORY_API, params={"range": range_km, "lng": lon, "lat": lat})
        r.raise_for_status()
        return r.json()


def fetch_stats() -> dict | None:
    try:
        with httpx.Client(timeout=40.0) as c:
            r = c.get(STATS_API)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


def main() -> int:
    aoi = get_aoi()
    out = ensure_dir(repo_root() / "outputs" / "demand")

    records = fetch_factories(aoi.center.lon, aoi.center.lat, max(aoi.disfactory_range_km, 12))
    years = Counter()
    for r in records:
        ts = r.get("reported_at") or ""
        if len(ts) >= 4 and ts[:4].isdigit():
            years[ts[:4]] += 1
    year_series = dict(sorted(years.items()))

    summary = {
        "aoi": aoi.display_name,
        "query": {"center": [aoi.center.lon, aoi.center.lat],
                  "range_km": max(aoi.disfactory_range_km, 12)},
        "n_reports_near_aoi": len(records),
        "reports_by_year": year_series,
        "national_statistics_raw": fetch_stats(),
        "public_figures_to_crosscheck": PUBLIC_FIGURES,
    }
    (out / "disfactory_stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out / "disfactory_reports_by_year.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "n_reports"])
        for y, n in year_series.items():
            w.writerow([y, n])

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        if year_series:
            fig, ax = plt.subplots(figsize=(7, 4))
            ax.bar(list(year_series.keys()), list(year_series.values()), color="#2f6b3c")
            # ASCII labels only — the default matplotlib font lacks CJK glyphs.
            ax.set_title(f"Disfactory reports per year near {aoi.name} (Changhua pilot)")
            ax.set_xlabel("Report year")
            ax.set_ylabel("# reported suspected factories")
            fig.tight_layout()
            fig.savefig(out / "disfactory_reports_by_year.png", dpi=130)
            print(f"Chart → {out / 'disfactory_reports_by_year.png'}")
    except Exception as exc:
        print(f"(matplotlib unavailable, skipping chart: {exc})")

    print(f"\n{len(records)} Disfactory reports within "
          f"{summary['query']['range_km']}km of {aoi.township}.")
    print("Reports by year:", year_series)
    print("Cross-check vs public figures:", json.dumps(PUBLIC_FIGURES, ensure_ascii=False))
    print(f"Wrote {out}/disfactory_stats.json (+ CSV).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
