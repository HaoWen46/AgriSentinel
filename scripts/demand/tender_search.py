"""Demand evidence (Component 2): government willingness-to-pay from public
procurement records.

Government WTP is *public record*. This searches Taiwan's e-procurement
(政府電子採購網) via the g0v community API (pcc.g0v.ronny.tw) for monitoring /
remote-sensing / illegal-use keywords, and exports matches to CSV. Award amounts
live on each tender's detail page; this captures the *volume and recency* of
relevant procurement as the demand signal, with the commercial comparable noted
for the price anchor. Falls back to a documented template if the API is down.

Run: ``uv run --extra demand python scripts/demand/tender_search.py``
"""

from __future__ import annotations

import csv
import json

import httpx

from agrisentinel.config import ensure_dir, repo_root

PCC_API = "https://pcc-api.openfun.app/api/searchbytitle"

KEYWORDS = [
    "違章工廠", "農地違規", "航遙測", "遙測影像", "衛星影像",
    "變更偵測", "國土監測", "土地利用監測", "違規使用查報", "無人機 監測",
]

# Commercial comparable for the price anchor (cite at report time).
COMPARABLE = {
    "service": "Japanese municipal satellite+AI farmland monitoring service",
    "price_per_municipality": "~¥2,000,000 (~NT$430,000)",
    "claimed_agreement_with_patrols": "~80%",
    "deploy_time": "~3 weeks",
}


def search(keyword: str, pages: int = 1) -> list[dict]:
    rows: list[dict] = []
    with httpx.Client(
        timeout=40.0, follow_redirects=True, headers={"User-Agent": "agrisentinel-demand/0.1"}
    ) as c:
        for page in range(1, pages + 1):
            resp = c.get(PCC_API, params={"query": keyword, "page": page})
            resp.raise_for_status()
            data = resp.json()
            for rec in data.get("records", []):
                brief = rec.get("brief", {}) or {}
                rows.append(
                    {
                        "keyword": keyword,
                        "date": rec.get("date"),
                        "unit_name": rec.get("unit_name"),
                        "title": brief.get("title"),
                        "type": brief.get("type"),
                        "job_number": rec.get("job_number"),
                        "url": f"https://pcc.g0v.ronny.tw/tender?q={keyword}",
                    }
                )
            if page >= data.get("total_pages", 1):
                break
    return rows


def _write_template(out) -> None:
    path = out / "tenders_template.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["keyword", "date", "unit_name", "title", "type", "award_amount_ntd", "url"])
        for kw in KEYWORDS:
            w.writerow([kw, "", "", "(export from web.pcc.gov.tw search)", "", "", ""])
    print(f"API unavailable — wrote collection template → {path}")
    print("Manual step: search each keyword at https://web.pcc.gov.tw and export awards.")


def main() -> int:
    out = ensure_dir(repo_root() / "outputs" / "demand")
    all_rows: list[dict] = []
    per_keyword: dict[str, int] = {}
    api_ok = True
    for kw in KEYWORDS:
        try:
            rows = search(kw, pages=1)
        except Exception as exc:
            print(f"  query '{kw}' failed: {exc}")
            api_ok = False
            break
        per_keyword[kw] = len(rows)
        all_rows.extend(rows)
        print(f"  '{kw}': {len(rows)} matching tenders")

    if not api_ok and not all_rows:
        _write_template(out)
        return 0

    path = out / "tenders.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["keyword", "date", "unit_name", "title", "type", "job_number", "url"]
        )
        w.writeheader()
        w.writerows(all_rows)

    summary = {
        "total_matching_tenders": len(all_rows),
        "by_keyword": per_keyword,
        "commercial_comparable": COMPARABLE,
        "method": "g0v PCC API searchbytitle; award amounts via each tender detail page.",
    }
    (out / "tenders_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nTotal matching tenders: {len(all_rows)}  → {path}")
    print("Commercial comparable (price anchor):", json.dumps(COMPARABLE, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
