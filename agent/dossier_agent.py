"""Phase 4 — the value-capture worker: RAG + Claude → enforcement dossiers.

For each flagged farmland parcel the agent:
  1. retrieves the most relevant statute chunks from pgvector (RAG),
  2. drafts a structured, fully-grounded dossier with Claude
     (``messages.parse`` → typed schema),
  3. runs an adversarial critic pass; if the critic finds an ungrounded or
     fabricated claim, it revises once.

Every factual claim must trace to a detection fact or a retrieved statute chunk
(see ``agent/prompts/``). Without an ``ANTHROPIC_API_KEY`` the agent emits a
clearly-labelled rule-based template dossier so the pipeline still completes.

Run: ``uv run python -m agent.dossier_agent``.
"""

from __future__ import annotations

import json
import os

from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from agrisentinel.config import get_aoi, get_settings, repo_root
from agrisentinel.db import get_conn
from agrisentinel.embeddings import load_fitted_embedder, to_vector_literal
from agrisentinel.logging import get_logger
from agrisentinel.runs import resolve_run_id

log = get_logger(__name__)

PROMPT_DIR = repo_root() / "agent" / "prompts"
DRAFTER_SYS = (PROMPT_DIR / "system_drafter.md").read_text(encoding="utf-8")
CRITIC_SYS = (PROMPT_DIR / "system_critic.md").read_text(encoding="utf-8")


# ── Typed dossier schema (drives messages.parse) ──────────────────────────────
class ViolatedStatute(BaseModel):
    law_title: str = Field(description="法規名稱 exactly as in the excerpts")
    article_no: str = Field(description="條號 exactly as in the excerpts")
    why: str = Field(description="One sentence: how the facts engage this provision")


class Dossier(BaseModel):
    summary: str = Field(description="2-3 sentence situation summary for an inspector")
    zoning_status: str = Field(description="Land/zoning status of the parcel")
    evidence: list[str] = Field(description="Grounded bullet facts (imagery, indices, corroboration)")
    violated_statutes: list[ViolatedStatute]
    recommended_action: str
    confidence_label: str = Field(description="one of: high / medium / low")
    caveats: str


class Critic(BaseModel):
    ok: bool
    issues: list[str]


# ── RAG retrieval ─────────────────────────────────────────────────────────────
def retrieve(conn, embedder, query: str, top_k: int) -> list[dict]:
    qvec = to_vector_literal(embedder.encode([query])[0])
    with conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT pcode, law_title, article_no, content,
                   1 - (embedding <=> %(q)s::vector) AS similarity
            FROM law_chunks
            ORDER BY embedding <=> %(q)s::vector
            LIMIT %(k)s;
            """,
            {"q": qvec, "k": top_k},
        ).fetchall()
    return rows


def _query_text(c: dict, aoi) -> str:
    return (
        f"農地（{aoi.county}{aoi.township} {c.get('sectname') or ''} 地號 {c.get('landcode') or ''}）"
        "疑似新建未登記工廠，土地編定為農牧用地，違反非都市土地使用管制與工廠管理輔導法，"
        "主管機關得依區域計畫法、農業發展條例停止供電供水並拆除。罰則 拆除 恢復原狀。"
    )


def _facts_block(c: dict, aoi, radius_m: float) -> str:
    corrob = "none"
    if c.get("distance_to_label_m") is not None and c["distance_to_label_m"] <= radius_m:
        corrob = (
            f"corroborated by Disfactory report {c.get('matched_label_id')} "
            f"at {c['distance_to_label_m']:.0f} m"
        )
    return "\n".join(
        [
            f"- AOI / region: {aoi.display_name}",
            f"- Parcel (地號 landcode): {c.get('landcode')}  Section (段): {c.get('sectname')}",
            "- Parcel zoning: agricultural farmland (is_farmland=TRUE)",
            f"- New-structure footprint area: {c.get('area_m2', 0):.0f} m² (overlap on farmland "
            f"{c.get('overlap_area_m2', 0):.0f} m²)",
            f"- Imagery dates: before {c.get('t0_date')} → after {c.get('t1_date')} (Sentinel-2 L2A)",
            f"- Built-up index rise (ΔNDBI): {c.get('ndbi_delta', 0):.3f}; "
            f"vegetation drop (ΔNDVI): {c.get('ndvi_drop', 0):.3f}",
            f"- Detector: {c.get('detector')}; model confidence: {c.get('confidence', 0):.2f}",
            f"- Centroid (lat, lon): {c.get('lat'):.5f}, {c.get('lon'):.5f}",
            f"- Ground-truth corroboration: {corrob}",
        ]
    )


def _statutes_block(citations: list[dict]) -> str:
    if not citations:
        return "(no statute excerpts retrieved)"
    return "\n\n".join(
        f"[{i + 1}] {c['law_title']} {c.get('article_no') or ''}\n{c['content']}"
        for i, c in enumerate(citations)
    )


# ── Claude draft + critic ─────────────────────────────────────────────────────
def _client(settings):
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _draft_with_claude(client, model, facts: str, statutes: str, feedback: str | None) -> Dossier:
    user = (
        f"DETECTION FACTS\n{facts}\n\nSTATUTE EXCERPTS\n{statutes}\n\n"
        "Draft the enforcement dossier as the schema. Ground every claim in the "
        "facts or statute excerpts above; cite only statutes shown."
    )
    if feedback:
        user += f"\n\nREVISION — fix these reviewer issues without inventing new facts:\n{feedback}"
    resp = client.messages.parse(
        model=model,
        max_tokens=3000,
        system=DRAFTER_SYS,
        messages=[{"role": "user", "content": user}],
        output_format=Dossier,
    )
    if resp.parsed_output is None:
        raise RuntimeError(f"drafter returned no structured output (stop={resp.stop_reason})")
    return resp.parsed_output


def _critique_with_claude(client, model, facts: str, statutes: str, draft: Dossier) -> Critic:
    user = (
        f"DETECTION FACTS\n{facts}\n\nSTATUTE EXCERPTS\n{statutes}\n\n"
        f"DRAFT DOSSIER (JSON)\n{draft.model_dump_json(indent=2)}"
    )
    resp = client.messages.parse(
        model=model,
        max_tokens=1500,
        system=CRITIC_SYS,
        messages=[{"role": "user", "content": user}],
        output_format=Critic,
    )
    return resp.parsed_output or Critic(ok=True, issues=[])


def _template_dossier(c: dict, aoi, citations: list[dict], radius_m: float) -> Dossier:
    """Deterministic, grounded fallback when no ANTHROPIC_API_KEY is set."""
    conf = c.get("confidence", 0) or 0
    label = "high" if conf >= 0.66 else "medium" if conf >= 0.4 else "low"
    corroborated = (
        c.get("distance_to_label_m") is not None and c["distance_to_label_m"] <= radius_m
    )
    statutes = [
        ViolatedStatute(
            law_title=ci["law_title"],
            article_no=ci.get("article_no") or "",
            why="Retrieved as most relevant to a new factory structure on agricultural land.",
        )
        for ci in citations[:3]
    ]
    evidence = [
        f"New built structure of ~{c.get('area_m2', 0):.0f} m² appeared on agricultural parcel "
        f"{c.get('landcode')} between {c.get('t0_date')} and {c.get('t1_date')} (Sentinel-2).",
        f"Built-up index rose by {c.get('ndbi_delta', 0):.3f} while vegetation index fell by "
        f"{c.get('ndvi_drop', 0):.3f}, consistent with construction replacing crops.",
    ]
    if corroborated:
        evidence.append(
            f"Corroborated by Disfactory report {c.get('matched_label_id')} "
            f"~{c['distance_to_label_m']:.0f} m away."
        )
    return Dossier(
        summary=(
            f"A suspected new structure was detected on agricultural farmland parcel "
            f"{c.get('landcode')} in {aoi.county}{aoi.township}. This is a candidate "
            "violation pending field verification."
        ),
        zoning_status="Agricultural farmland (農牧用地); factory use is not a permitted use.",
        evidence=evidence,
        violated_statutes=statutes,
        recommended_action=(
            "Dispatch a field inspection to verify the structure and its use; if confirmed as an "
            "unregistered factory built after 2016-05-20, proceed under 工廠管理輔導法 第28-1條 "
            "(stop water/electricity and demolish) and 區域計畫法 第21條 (penalty + restoration)."
        ),
        confidence_label=label,
        caveats=(
            "Generated WITHOUT an LLM (no ANTHROPIC_API_KEY). Sentinel-2 (10 m) is coarse for small "
            "buildings; confirm with high-resolution NLSC orthophotos and a site visit. Disfactory "
            "labels are incomplete."
        ),
    )


# ── Rendering & persistence ───────────────────────────────────────────────────
def render_md(c: dict, aoi, d: Dossier, citations: list[dict], model: str) -> str:
    lines = [
        f"# Enforcement Dossier — Parcel {c.get('landcode')} ({aoi.county}{aoi.township})",
        "",
        f"*Decision-support artifact generated by AgriSentinel ({model}). "
        "Not a legal determination — for inspector review before filing.*",
        "",
        "## Summary",
        d.summary,
        "",
        f"**Zoning status:** {d.zoning_status}",
        f"**Confidence:** {d.confidence_label}",
        "",
        "## Evidence",
        *[f"- {e}" for e in d.evidence],
        "",
        "## Statutes implicated",
        *[f"- **{v.law_title} {v.article_no}** — {v.why}" for v in d.violated_statutes],
        "",
        "## Recommended action",
        d.recommended_action,
        "",
        "## Caveats",
        d.caveats,
        "",
        "## Retrieved statute excerpts (RAG sources)",
        *[
            f"- [{i + 1}] {ci['law_title']} {ci.get('article_no') or ''} "
            f"(sim {ci.get('similarity', 0):.2f})"
            for i, ci in enumerate(citations)
        ],
    ]
    return "\n".join(lines)


def persist(c: dict, run_id: str, model: str, d: Dossier, md: str, citations: list[dict]) -> None:
    violated = "; ".join(f"{v.law_title} {v.article_no}".strip() for v in d.violated_statutes)
    payload = {
        "facts": {k: c[k] for k in c if k != "geom"},
        "dossier": d.model_dump(),
        "citations": [
            {"law_title": ci["law_title"], "article_no": ci.get("article_no"),
             "similarity": ci.get("similarity")} for ci in citations
        ],
        "model": model,
    }
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO dossiers (flagged_id, run_id, parcel_id, landcode, model, confidence,
                                  violated_law, recommended_action, dossier_md, dossier_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (flagged_id) DO UPDATE SET
                model=EXCLUDED.model, confidence=EXCLUDED.confidence,
                violated_law=EXCLUDED.violated_law, recommended_action=EXCLUDED.recommended_action,
                dossier_md=EXCLUDED.dossier_md, dossier_json=EXCLUDED.dossier_json;
            """,
            (c["flagged_id"], run_id, c["parcel_id"], c.get("landcode"), model,
             float(c.get("confidence") or 0), violated, d.recommended_action, md,
             json.dumps(payload, ensure_ascii=False)),
        )


def _candidates(run_id: str, limit: int) -> list[dict]:
    with get_conn() as conn, conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            """
            SELECT DISTINCT ON (f.detection_id)
                f.id AS flagged_id, f.detection_id, f.parcel_id, f.landcode, f.sectname,
                f.overlap_area_m2, f.confidence, f.matched_label_id, f.distance_to_label_m,
                ST_Y(ST_Centroid(f.geom)) AS lat, ST_X(ST_Centroid(f.geom)) AS lon,
                d.ndbi_delta, d.ndvi_drop, d.area_m2, d.t0_date, d.t1_date, d.detector
            FROM flagged_parcels f JOIN detections d ON d.id = f.detection_id
            WHERE f.run_id = %s
            ORDER BY f.detection_id, f.overlap_area_m2 DESC;
            """,
            (run_id,),
        ).fetchall()
    rows.sort(key=lambda r: r.get("confidence") or 0, reverse=True)
    return rows[:limit]


def main() -> int:
    aoi = get_aoi()
    settings = get_settings()
    run_id = resolve_run_id()
    if not run_id:
        raise RuntimeError("No run found. Run detect → join first.")
    radius_m = aoi.detection.match_radius_m
    limit = int(os.environ.get("AGRISENTINEL_MAX_DOSSIERS", "12"))
    candidates = _candidates(run_id, limit)
    if not candidates:
        log.warning("No flagged parcels for run '%s'; nothing to draft.", run_id)
        return 0

    have_key = bool(settings.anthropic_api_key)
    model = settings.anthropic_model if have_key else "template (no ANTHROPIC_API_KEY)"
    if not have_key:
        log.warning("ANTHROPIC_API_KEY not set → emitting rule-based template dossiers.")
    client = _client(settings) if have_key else None

    embedder = load_fitted_embedder(settings)
    n_ok = 0
    with get_conn() as conn:
        for c in candidates:
            citations = retrieve(conn, embedder, _query_text(c, aoi), aoi.laws.top_k)
            facts = _facts_block(c, aoi, radius_m)
            statutes = _statutes_block(citations)
            try:
                if have_key:
                    draft = _draft_with_claude(client, settings.anthropic_model, facts, statutes, None)
                    critic = _critique_with_claude(client, settings.anthropic_model, facts, statutes, draft)
                    if not critic.ok and critic.issues:
                        log.info("Parcel %s: critic flagged %d issue(s); revising.",
                                 c.get("landcode"), len(critic.issues))
                        draft = _draft_with_claude(
                            client, settings.anthropic_model, facts, statutes,
                            "\n".join(f"- {i}" for i in critic.issues),
                        )
                else:
                    draft = _template_dossier(c, aoi, citations, radius_m)
            except Exception as exc:  # API error / refusal → template fallback for this parcel
                log.warning("Claude draft failed for parcel %s (%s) → template.",
                            c.get("landcode"), exc)
                draft = _template_dossier(c, aoi, citations, radius_m)
            md = render_md(c, aoi, draft, citations, model)
            persist(c, run_id, model, draft, md, citations)
            n_ok += 1
            log.info("Dossier %d/%d done for parcel %s.", n_ok, len(candidates), c.get("landcode"))

    log.info("Generated %d dossiers for run '%s' (model=%s).", n_ok, run_id, model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
